"""Full simulation test for Custom Armor Kit 2.2.3.

Extracts the REAL functions from the assembled payload and runs them against
a mock memory model (pages, protections, decoy records, VirtualAllocEx).
Scenario coverage: decoy rejection, apply/merge byte layout, buffer reuse,
stats-pointer byte length, guard pages, restore, compose budgets, config
parse round-trip, auto-queue skip/retry.
"""
import io
import os
import re
import sys
from pathlib import Path

import lupa

W = str(Path(__file__).resolve().parents[1])
FORK = os.path.join(W, "fork", "foundation.lua")
BODY = os.path.join(W, "standalone", "multi_perk.lua")
ZHDATA = os.path.join(W, "standalone", "zh_data.lua")

# ---- assemble exactly like the real build -------------------------------------
ft = io.open(FORK, encoding="utf-8", errors="replace").read()
s0 = ft.index("local CatalogData = (function()")
e0 = ft.index("\nend)()", s0) + len("\nend)()")
lua = lupa.LuaRuntime(unpack_returned_tuples=True)
catalog = lua.execute(ft[s0:e0] + "\nreturn CatalogData")
rows = []
for enum in sorted(catalog["passives"].keys()):
    p = catalog["passives"][enum]
    mods = [str(h) for h in p["raw_modifiers"].values()]
    stats = [str(h) for h in p["raw_stat_modifiers"].values()]
    rows.append('\t[%d]={n=%d,m={%s},s={%s}},' % (
        enum, int(p["name_loc"]),
        ",".join("'%s'" % h for h in mods),
        ",".join("'%s'" % h for h in stats)))
src = io.open(BODY, encoding="utf-8").read()
src = src.replace("local PERKS={ --@@PERKS@@\n}", "local PERKS={\n" + "\n".join(rows) + "\n}")
assert "@@PERKS@@" not in src
zhdata = io.open(ZHDATA, encoding="utf-8").read()
# strip the giant packed tables - not needed for logic tests; keep small ones
small = re.sub(r"local ZH_PACK=\[\[.*?\]\]", "local ZH_PACK=''", zhdata, flags=re.S)
src = src.replace("--@@ZHDATA@@\n", small)
assert "@@ZHDATA@@" not in src
lupa.LuaRuntime().compile(src)


def cut(a, b):
    i = src.index(a)
    return src[i:src.index(b, i)]


pieces_src = cut("local PIECES={", "\nlocal function compose")
perks_src = cut("local PERKS={", "\nlocal function compose")
compose_src = cut("local function compose(list,budget)", "\nlocal S={")
merge_src = cut("local function merge_carrier(c,list,budget)", "\nlocal ACTIVE=")
apply_src = cut("local function apply_card(c,conf_data)", "\nlocal function restore_all")
restore_src = cut("local function restore_all", "\nlocal function steady_all")
pick_src = cut("                    -- the name id must match the catalog", "                    -- register every known passive record")
queue_src = cut("        if S.carrier and #M.auto_queue>0", "        if ready")
confloop_src = cut("    local target,write,perks", "    if #cards==0 and (target or card) then")

L = lupa.LuaRuntime(unpack_returned_tuples=True)
L.execute(pieces_src + "\nPIECES_G=PIECES")
L.execute(perks_src + "\nPERKS_G=PERKS")
owned_src = cut("local OWNED=", "\nlocal PIECES=")
L.execute(owned_src + "\nOWNED_G=OWNED")

MOCK = r"""
-- ===== mock memory ============================================================
local ALLOCS={}
local NEXT=0x20000000
local function mem_alloc(size,prot,fill)
    local base=NEXT
    NEXT=NEXT+size+0x1000
    ALLOCS[#ALLOCS+1]={base=base,size=size,data=fill or string.rep('\0',size),prot=prot or 4}
    return base
end
local function mem_find(at)
    for _,a in ipairs(ALLOCS) do
        if at>=a.base and at<a.base+a.size then return a end
    end
    return nil
end
local function rd(at,n)
    local a=mem_find(at)
    if not a or at+n>a.base+a.size then return nil end
    return string.sub(a.data,at-a.base+1,at-a.base+n)
end
local VALLOC_N=0
local function valloc(n)
    VALLOC_N=VALLOC_N+1
    return mem_alloc(n,4)
end
local function wr_raw(at,bytes)
    local a=mem_find(at)
    if not a or at+#bytes>a.base+a.size then return false end
    a.data=string.sub(a.data,1,at-a.base)..bytes..string.sub(a.data,at-a.base+#bytes+1)
    return true
end
-- mirrors the shipped wr() policy: guard/noaccess pages are refused outright
local function wr(at,bytes)
    local a=mem_find(at)
    if not a or at+#bytes>a.base+a.size then return false,'range' end
    if a.prot>=0x100 or a.prot==0 then return false,'guarded' end
    wr_raw(at,bytes)
    if rd(at,#bytes)~=bytes then return false,'verify' end
    return true
end
local function protect_rw(at,n)
    local a=mem_find(at)
    if not a then return nil end
    return a.prot
end
local function protect_set(at,n,prot) end
-- ===== shared state and helpers ===============================================
local PERKS=PERKS_G
local PIECES=PIECES_G
local OWNED=OWNED_G
local RT={}
RT_G=RT
local LOGS={}
local function log(s) LOGS[#LOGS+1]=tostring(s) end
local function u32(s,o)
    if not s or #s<o+4 then return nil end
    local a,b,c,d=s:byte(o+1,o+4);return a+256*b+65536*c+16777216*d
end
local function u64(s,o)
    local lo,hi=u32(s,o),u32(s,o+4);if not lo or not hi then return nil end
    return lo+hi*4294967296
end
local function p32(v)
    v=math.floor(v)%4294967296
    local a=v%256;v=(v-a)/256;local b=v%256;v=(v-b)/256
    local c=v%256;v=(v-c)/256;return string.char(a,b,c,v%256)
end
local function p64(v) local lo=math.floor(v)%4294967296;return p32(lo)..p32((v-lo)/4294967296) end
local function unhex(s) return (s:gsub('%x%x',function(x) return string.char(tonumber(x,16)) end)) end
local function drop_carrier(why) S.carrier=nil end
local M={bufs={},statrows=true}
M.ship_ok=true
data_ok=true -- queue slice executes after the real data-readiness gate
local S={carrier=nil,carriers={},kits={}}
_G.S=S
_G.M=M
local function save_active_labels() S.saved=(M.active_card and M.active_card.label) or '' end
-- ===== real code under test ===================================================
COMPOSE_PLACEHOLDER
MERGE_PLACEHOLDER
APPLY_PLACEHOLDER
PICK_PLACEHOLDER
QUEUE_PLACEHOLDER
CONF_PLACEHOLDER
-- ===== world build ============================================================
-- real passive record for enum 37 (pristine: inline rows at body+56)
local ROWS37={}
for i,h in ipairs(PERKS[37].m or {}) do ROWS37[i]=unhex(h) end
local carrier_body=mem_alloc(56+16*8,4)
wr_raw(carrier_body,p32(37)..p32(PERKS[37].n)..string.rep('\0',8)
    ..p64(carrier_body+56)..p64(#ROWS37)..string.rep('\0',16)
    ..table.concat(ROWS37))
-- decoy: enum bytes ok, name wrong, alien layout
local decoy_body=mem_alloc(64,4)
wr_raw(decoy_body,p32(37)..p32(1724458231)..p64(0x90400c4b2c62c1ba)
    ..p32(30081528)..p32(10)..string.rep('\0',32))
-- armor kit for the card look
local LOOK=0xc71dbba4
local tp=PIECES[LOOK]
local kit_body=mem_alloc(0x98+0x60*(#tp+1)+64,4)
wr_raw(kit_body,p32(LOOK)..string.rep('\0',24)..p32(3))
S.kits[LOOK]={body=kit_body,head=rd(kit_body,32)}
S.carrier={body=carrier_body,enum=37,head=rd(carrier_body,56)}
local CONF={write=true,rows=30,carrier=37,statrows=true,cards={},
    want_items={[LOOK]=true}}
local function mkcard(perks,stats)
    return {label='CARD 1',look=LOOK,stats=stats,perks=perks}
end
-- ===== tests ==================================================================
local R={}
local function T(name,f)
    local ok,err=pcall(f)
    R[#R+1]={name=name,ok=ok,err=err}
    if not ok then log('FAIL '..name..': '..tostring(err)..' TB '..tostring(debug and debug.traceback and debug.traceback(err) or '')) end
end
T('decoy_rejected_by_pick',function()
    local head=rd(decoy_body,56)
    local enum=u32(head,0)
    assert(not (PERKS[enum] and u32(head,4)==PERKS[enum].n),'decoy must FAIL the pick predicate (name mismatch)')
    local real=rd(carrier_body,56)
    assert(PERKS[37] and u32(real,4)==PERKS[37].n,'real record passes')
end)
T('apply_writes_full_layout',function()
    M.statrows=false
    local ok,why=apply_card(mkcard({7,15,20,36,38}),CONF)
    assert(ok,why)
    assert(u32(rd(kit_body,32),28)==37,'kit passive points at carrier')
    local h=rd(carrier_body,56)
    assert(u32(h,0)==37,'enum intact')
    assert(u32(h,4)==PERKS[37].n,'native carrier name identity retained')
    local at=u64(h,16)
    assert(at and at>0,'modifier pointer set')
    assert(u64(h,24)==11,'11 native rows, including hidden arc/running effects, got '..tostring(u64(h,24)))
    assert(u64(h,40)==0 and u64(h,32)==0,'empty stat header remains zero')
    local mods_len=at and 0
    -- buffer content equals the compose output for the same list
    local data=compose({7,15,20,36,38},30)
    assert(rd(at,#data.mods)==data.mods,'buffer bytes == unhexed mods')
    assert(mem_find(at)~=nil,'buffer is allocated (valloc)')
    assert(VALLOC_N==1,'exactly one allocation so far')
    G_AT=at
end)
T('reapply_reuses_buffer',function()
    local ok,why=apply_card(mkcard({7,15,20,36,38}),CONF)
    assert(ok,why)
    assert(VALLOC_N==1,'same perk set reuses the same buffer, no new alloc')
    local h=rd(carrier_body,56)
    assert(u64(h,16)==G_AT,'pointer unchanged')
end)
T('new_perkset_reallocates_and_identity_ok',function()
    local ok,why=apply_card(mkcard({5,6,7}),CONF)
    assert(ok,why)
    assert(VALLOC_N==2,'different perk set allocates a new page')
    local h=rd(carrier_body,56)
    assert(u32(h,4)==PERKS[37].n,'changing effects preserves native display metadata')
end)
T('stats_pointer_uses_byte_length',function()
    M.statrows=true
    local ok,why=apply_card(mkcard({16,7}),CONF)  -- 16 = Siege-Ready has stat rows
    assert(ok,why)
    local h=rd(carrier_body,56)
    local nstat=u64(h,40)
    assert(nstat and nstat>0,'stat count > 0 with statrows on')
    local at=u64(h,16)
    local data=compose({16,7},30)
    assert(u64(h,32)==at+#data.mods,'stat pointer = at + BYTE length (hex/2), the fixed bug')
    assert(rd(u64(h,32),#data.stats)==data.stats or data.stats=='','stat rows land in the buffer')
end)
T('compose_budget_refusal',function()
    local ok,err=compose({1,7,15,20,32,36,38,5,6,8,9,21,33},12)
    assert(ok==nil and tostring(err):find('budget',1,true),'oversize refused: '..tostring(err))
end)
T('compose_filters_zero_and_carrier',function()
    local h0=rd(carrier_body,56)
    local ok,err=merge_carrier({body=carrier_body,enum=37,name_now=u32(h0,4),buf_at=u64(h0,16)},{0,37,7},30)
    assert(ok,'merge succeeds after dropping 0 and 37: '..tostring(err))
end)
T('guard_page_apply_fails_clean',function()
    -- restore first so the record is pristine
    restore_all()
    local a=mem_find(carrier_body)
    a.prot=0x104
    local ok,why=apply_card(mkcard({7}),CONF)
    a.prot=4
    assert(ok==nil,'apply must fail on a guarded page')
    assert(tostring(why):find('header',1,true),'failure is a header write: '..tostring(why))
    local h=rd(carrier_body,56)
    assert(u32(h,4)==PERKS[37].n and u64(h,16)==carrier_body+56,'record untouched (pristine)')
    assert(u32(rd(kit_body,32),28)==3,'kit passive untouched')
end)
T('restore_all_vanilla_bytes',function()
    local a=mem_find(carrier_body)
    a.prot=4
    S.carrier={body=carrier_body,enum=37,head=rd(carrier_body,56)}
    local ok,why=apply_card(mkcard({7,15}),CONF)
    assert(ok,why)
    assert(u32(rd(kit_body,32),28)==37,'applied')
    restore_all()
    local h=rd(carrier_body,56)
    assert(u32(h,4)==PERKS[37].n,'name restored')
    assert(u64(h,16)==carrier_body+56,'inline pointer restored')
    assert(u64(h,24)==#ROWS37,'row count restored')
    assert(u32(rd(kit_body,32),28)==3,'kit passive restored')
    assert(M.active_card==nil,'active cleared')
    assert(S.saved=='','active.txt emptied')
end)
T('conf_parse_roundtrip',function()
    local hex1=PERKS[7].m[1]
    local hex2=PERKS[16].m[1]
    local c=CONF_TEXT
    local cards,rowsv,langv,statv,writev=c('card.1=X,'..string.format('%08x',LOOK)..',,'..hex1..','..hex2..'\nrows=25\nlang=en\nstatrows=yes\nwrite=yes\n')
    assert(#cards==1,'one card parsed')
    assert(cards[1].perks[1]==hex1 and cards[1].perks[2]==hex2,'hex row tokens parse verbatim')
    assert(cards[1].look==LOOK,'look id parsed')
    assert(rowsv==11 and langv=='en' and statv==true and writev==true,'stable rows/lang/statrows/write parsed')
    local c2=c('card.2=Y,16e1b9d3,f8fadb6c,5,6,7')
    assert(c2 and c2[1] and c2[1].perks[1]==5 and #c2[1].perks==3,'legacy plain perks parse')
end)
T('autoqueue_skips_active_and_gives_up',function()
    M.auto_queue={'CARD 1'}
    M.auto_retry_after=nil
    M.active_card={label='CARD 1'}
    M.actives={[LOOK]={card=M.active_card,enum=37}}
    M.auto_card_by_label=function(l) return {label=l,look=LOOK,stats=nil,perks={7}} end
    local applied=0
    AQ_APPLY=function(card) applied=applied+1 return true end
    AQ_FRAMES=100
    AQ_RUN()
    assert(applied==0,'active card skipped without apply')
    assert(#M.auto_queue==0,'skipped card removed from queue')
    -- retry path: failing card retries with backoff, gives up after 60
    M.auto_queue={'CARD X'}
    AQ_APPLY=function() return nil,'boom' end
    AQ_FRAMES=100
    AQ_RUN()  -- first failure
    assert(#M.auto_queue==1 and M.auto_retry_after==700,'retry scheduled')
    M.auto_tries=60
    AQ_FRAMES=100000
    AQ_RUN()  -- gives up
    assert(#M.auto_queue==0,'gave-up card dropped')
end)
RESULTS=R
LOGCOUNT=#LOGS
"""
MOCK = MOCK.replace("COMPOSE_PLACEHOLDER", compose_src)
MOCK = MOCK.replace("MERGE_PLACEHOLDER", merge_src)
MOCK = MOCK.replace("APPLY_PLACEHOLDER", apply_src + restore_src)
MOCK = MOCK.replace("PICK_PLACEHOLDER", pick_src.replace("conf_data.carrier", "37"))
MOCK = MOCK.replace("QUEUE_PLACEHOLDER",
                    "AQ_RUN=function() " + queue_src.replace("apply_card(def,conf_data)", "AQ_APPLY(def)")
                    .replace("frames", "AQ_FRAMES").replace("card_by_label(conf_data,lab)", "M.auto_card_by_label(lab)")
                    + " end")
MOCK = MOCK.replace("CONF_PLACEHOLDER",
                    "CONF_TEXT=function(text) " + confloop_src +
                    "\n return cards,rowbudget,langopt,statrows,(write=='yes' or write=='true') end")

L.execute(MOCK)

res = L.eval("RESULTS")
fails = 0
n = L.eval("#RESULTS")
for i in range(1, n + 1):
    name = L.eval("RESULTS[%d].name" % i)
    ok = L.eval("RESULTS[%d].ok" % i)
    err = L.eval("tostring(RESULTS[%d].err)" % i)
    print(("PASS  " if bool(ok) else "FAIL  ") + str(name) + ("" if bool(ok) else "  -> " + str(err)))
    if not bool(ok):
        fails += 1
print("----")
print("%d/%d passed" % (n - fails, n))
sys.exit(1 if fails else 0)
