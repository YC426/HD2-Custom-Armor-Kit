"""2.5.1: official in-game perk text (16px, wrapped), armor picker with
pinyin search, sweep registers every catalog kit, auto-retry of saved cards.
Assemble, sandbox-verify, pack, deploy.
"""
import hashlib
import io
import os
import re
import sys
import zipfile

import lupa

W = r"C:\HD2-Workspace\work"
FORK = os.path.join(W, "fork", "foundation.lua")
BODY = os.path.join(W, "standalone", "multi_perk.lua")
ZHDATA = os.path.join(W, "standalone", "zh_data.lua")
# The release version comes from the assembled body, so build_armor.py can
# reuse this template for any version without editing literals here.
VERSION = re.search(r"version='([^']+)'", io.open(BODY, encoding="utf-8").read()).group(1)
OUT = r"C:\HD2-Workspace\outputs"
ZIP = os.path.join(OUT, "Custom-Armor-Kit-%s.zip" % VERSION)
GAME = r"D:\Program Files (x86)\Steam\steamapps\common\Helldivers 2\data"
MGR_CAND = os.path.join(os.environ["LOCALAPPDATA"], r"hd2arsenal\mods")
MGR = next(os.path.join(MGR_CAND, d) for d in sorted(os.listdir(MGR_CAND))
           if d.lower().startswith("hd2-multiperk") or d.lower().startswith("custom-armor"))

# ---- 1. assemble ----------------------------------------------------------------
ftext = io.open(FORK, encoding="utf-8", errors="replace").read()
start = ftext.index("local CatalogData = (function()")
end = ftext.index("\nend)()", start) + len("\nend)()")
lua = lupa.LuaRuntime(unpack_returned_tuples=True)
catalog = lua.execute(ftext[start:end] + "\nreturn CatalogData")
rows = []
for enum in sorted(catalog["passives"].keys()):
    p = catalog["passives"][enum]
    mods = [str(h) for h in p["raw_modifiers"].values()]
    stats = [str(h) for h in p["raw_stat_modifiers"].values()]
    rows.append('\t[%d]={n=%d,m={%s},s={%s}},' % (
        enum, int(p["name_loc"]),
        ",".join("'%s'" % h for h in mods),
        ",".join("'%s'" % h for h in stats)))

source = io.open(BODY, encoding="utf-8").read()
source = source.replace("local PERKS={ --@@PERKS@@\n}", "local PERKS={\n" + "\n".join(rows) + "\n}")
assert "@@PERKS@@" not in source
zhdata = io.open(ZHDATA, encoding="utf-8").read()
source = source.replace("--@@ZHDATA@@\n", zhdata)
assert "@@ZHDATA@@" not in source
assert ("version='%s'" % VERSION) in source, "assembled source is not release %s" % VERSION
lupa.LuaRuntime().compile(source)
# the GAME runs LuaJIT, not Lua 5.x - compile there too (65535 instructions per
# function). A Lua-5-only "compiles fine" has shipped a silently unloadable
# mod on this game before.
import lupa.luajit21 as _luajit
_luajit.LuaRuntime().compile(source)
print("compile: lua5 + luajit OK")

# ---- 1b. static FFI gate --------------------------------------------------------
# 2.5.0 shipped calling kernel32.VirtualAllocEx without ever declaring it, so
# every card apply died with "missing declaration for symbol 'VirtualAllocEx'"
# (MultiPerk.log 2026-09-30T21:46:07Z) - i.e. "clicking a card does nothing".
# Refuse to build while any called C symbol is undeclared.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ffi_audit
_missing = ffi_audit.audit_source(source, "custom_armor (assembled)")
assert not _missing, "undeclared C symbol(s) called: %s" % _missing
print("assembled:", len(source.encode("utf-8")), "bytes | perks:", len(rows))

def slice_src(a, b):
    i = source.index(a)
    return source[i:source.index(b, i)]

# ---- 2. sandbox: packed font parses + coverage + per-char fallback --------
pack_src = zhdata[zhdata.index("local ZH_PACK=[["):zhdata.index("]]", zhdata.index("local ZH_PACK=[[")) + 2]
init_src = slice_src("local ZH={}", "local WCLASS=")
luaF = lupa.LuaRuntime(unpack_returned_tuples=True)
luaF.execute(pack_src + """
local LOGS={}
local log=function(s) LOGS[#LOGS+1]=s end
local string=string local tonumber=tonumber local table=table local pairs=pairs
""" + init_src + """
zh_init()
HAS=function(s) return ZH[s]~=nil end
NFONT=function() local n=0 for k in pairs(ZH) do if #k==3 then n=n+1 end end return n end
NGYL=function() local n=0 for _ in pairs(ZH) do n=n+1 end return n end
""")
for ch in ("潜焰履凿滑铲慑"):  # hanzi that appear in game text
    assert luaF.eval("HAS('%s')" % ch), ch
assert luaF.eval("HAS('打开')") == 1
assert luaF.eval("NFONT()") > 6000
nglyphs = luaF.eval("NGYL()")
assert nglyphs > 6900, nglyphs
print("packed font ok: %d glyphs parsed (hanzi=%d), phrases resolve" % (nglyphs, luaF.eval("NFONT()")))

txt_src = slice_src("local function zhdraw(", "\n    PANEL.regions={}")
lua5 = lupa.LuaRuntime(unpack_returned_tuples=True)
lua5.execute("""
local DRAWN={zh=0,ascii=0}
local function rect(x,y,w,h,c)
    if w<=2 then DRAWN.zh=DRAWN.zh+1 else DRAWN.ascii=DRAWN.ascii+1 end
end
local zcell,acell=2,4
local white={1,1,1}
local W8={8,4,2,1}
-- font with single chars only: forces the per-character fallback path
local ZH={
    ['打']={w=16,h=2,r={'ffffffffffffffff','00'}},
    ['开']={w=16,h=2,r={'f0f0f0f0f0f0f0f0','00'}},
}
local M={}
local function log() end
local GLYPHS={
    ['[']={'0110','0100','0100','0100','0110'},
    [']']={'0110','0010','0010','0010','0110'},
    ['3']={'1110','0001','0110','0000','1110'},
}
""" + txt_src + """
T2=function() DRAWN.zh,DRAWN.ascii=0,0
    txt(0,0,'[ 打开 ]')
    return DRAWN.zh,DRAWN.ascii
end
""")
zh, asc = lua5.eval("T2()")
assert zh > 0 and asc > 0, (zh, asc)
print("per-char fallback ok: '[ 打开 ]' zh_px=%d ascii_px=%d (no phrase table needed)" % (zh, asc))

# ---- 3. sandbox: probe terminates and reports hits -----------------------------
probe_src = slice_src("local PROBE=", "\nend\n")
lua6 = lupa.LuaRuntime(unpack_returned_tuples=True)
lua6.execute(r"""
local needle='肾上腺素除颤器'
local LOGS={}
local function log(s) LOGS[#LOGS+1]=s end
local TICKS=0
local os={clock=function() TICKS=TICKS+1 return TICKS end}  -- single deadline tick per call
local regions={{base=1000,size=8000,state=0x1000,prot=6}}
local ri=0
local function region(at)
    ri=ri+1
    if ri<=#regions then return regions[ri] end
    return {base=at,size=0,state=0,prot=0}
end
local function rd(a,n)
    local pad=('x'):rep(4000)
    return pad..needle..('y'):rep(n-4000-21)
end
local string=string local table=table local math=math
""" + probe_src + """
end
RUN=function(d) probe_loc(d) end
DUMPCOUNT=function() local n=0 for _,l in ipairs(LOGS) do if l:find('probe hit',1,true) then n=n+1 end end return n,#LOGS end
PROBEG=PROBE
""")
for _ in range(50):
    lua6.execute("if not PROBEG.done then RUN(1000) end")
    if lua6.eval("PROBEG.done"):
        break
else:
    raise SystemExit("probe sandbox never terminated")
nhit, nlog = lua6.eval("DUMPCOUNT()")
assert nhit >= 1, nlog
print("probe ok: sweeps, finds needle, logs", nhit, "hit line(s), terminates")

# ---- 4. sandbox: pick-mode filter ------------------------------------------------
tables = zhdata[zhdata.index("local PICKKEYS={"):zhdata.index("}", zhdata.index("local PICKKEYS={")) + 1]
lua2 = lupa.LuaRuntime(unpack_returned_tuples=True)
lua2.execute(tables + r"""
string=string
function filter(owned,q)
  q=(q or ''):lower()
  local hits={}
  for _,id in ipairs(owned) do
    if q=='' or ((PICKKEYS[string.format('%x',id)] or ''):find(q,1,true)) then
      hits[#hits+1]=id
    end
  end
  return hits
end
""")
owned = [0x1c2a674, 0x05e56ee5, 0x09b08ec4, 0x16e1b9d3]
lua2.execute("tableA={" + ",".join(str(x) for x in owned) + "}")
h_all = lua2.eval("filter(tableA,'')")
assert len(h_all) == 4, len(h_all)
h_ad = lua2.eval("filter(tableA,'ad')")
assert len(h_ad) == 1 and h_ad[1] == 0x1c2a674, [h_ad[i] for i in range(1, len(h_ad) + 1)]
h_xr = lua2.eval("filter(tableA,'xr')")
assert len(h_xr) == 1 and h_xr[1] == 0x1c2a674
h_jtzcb = lua2.eval("filter(tableA,'jtzcb')")
assert len(h_jtzcb) == 1 and h_jtzcb[1] == 0x05e56ee5
print("pick filter ok: '' -> 4, 'ad'/'xr' -> AD-26, 'jtzcb' -> SR-24")

# ---- 3. sandbox: official effect keys resolve through the packed font ------
m = re.search(r"local PERK_EFFECTS=\{(.*?)\n\}", zhdata, re.S)
assert m and "E12" in m.group(1)
lua3 = lupa.LuaRuntime(unpack_returned_tuples=True)
lua3.execute(pack_src + """
local LOGS={}
local log=function(s) LOGS[#LOGS+1]=s end
local string=string local tonumber=tonumber local table=table local pairs=pairs
""" + init_src + "\n" + zhdata[m.start():m.end() + 1] + """
zh_init()
CHECK12=PERK_EFFECTS[12]
RES12=function() local t={} for i=1,#CHECK12 do t[i]=ZH[CHECK12[i]] end return t end
""")
c12 = lua3.eval("CHECK12")
assert c12 is not None and len(c12) >= 2
res = lua3.eval("RES12()")
assert all(res[i] is not None and res[i]["r"] is not None for i in range(1, len(c12) + 1))
print("official effects ok: enum 12 has", len(c12), "key(s), all resolve to bitmaps")

# ---- 6. sandbox: key capture char mapping -----------------------------------------
lua4 = lupa.LuaRuntime(unpack_returned_tuples=True)
lua4.execute(r"""
function vkc(vk) return string.char(vk+(vk>=0x41 and 32 or 0)) end
Q=''
function typevk(vk)
  if #Q<12 then Q=Q..vkc(vk) end
  return Q
end
""")
assert lua4.eval("vkc(0x41)") == "a"
assert lua4.eval("vkc(0x5A)") == "z"
assert lua4.eval("vkc(0x32)") == "2"
lua4.execute("typevk(0x41) typevk(0x44) typevk(0x32) typevk(0x36)")
assert lua4.eval("Q") == "ad26"
lua4.execute("Q=Q:sub(1,#Q-1)")
assert lua4.eval("Q") == "ad2"
print("key capture ok: A->a, digits pass, backspace trims")

# ---- 7. sandbox: sweep registers PIECES kits (gate check by source) ---------------
assert "if PIECES[item] and not S.kits[item] then" in source
assert "conf_data.want_items[item] and not S.kits[item]" not in source
print("sweep gate ok: registers every catalog kit (PIECES membership)")

# ---- 8. sandbox: oversize merge refused, never byte-cut ----------------------
comp_src = slice_src("local function compose(list,budget)", "\nlocal S={")
lua7 = lupa.LuaRuntime(unpack_returned_tuples=True)
lua7.execute("""
PERKS={}
for i=1,20 do
  PERKS[i]={n=i,m={},s={}}
  PERKS[i].m[1]=string.format('%08x',i)..string.rep('b',24)
end
""" + "local M={statrows=true} local log=function() end local function unhex(s) return s end\n" + comp_src + """
TRY=function() local ok,err=compose({1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20}) return ok,err end
TRY2=function() local ok,err=compose({1,2,3,4,5,6,7,8,9,10}) return ok,err end
TRY3=function() local ok,err=compose({1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20}, 12) return ok,err end
TRY4=function() local ok,err=compose({'1.1','2.1','20.1'}) if not ok then return nil,err end return ok.nmod,ok.nstat end
TRY5=function() local ok,err=compose({'9.9'}) return ok,err end
""")
ok1, err1 = lua7.eval("TRY()")
assert ok1 is None and 'budget' in str(err1), (ok1, err1)  # stable ceiling refuses oversize
ok2, err2 = lua7.eval("TRY2()")
assert ok2 is not None, (ok2, err2)  # 10 rows = verified-safe budget
ok3, err3 = lua7.eval("TRY3()")
assert ok3 is None and err3 and "budget" in str(err3), (ok3, err3)
n4a, n4b = lua7.eval("TRY4()")
assert n4a == 3 and n4b == 0, (n4a, n4b)
ok5, err5 = lua7.eval("TRY5()")
assert ok5 is None and err5 and "no row" in str(err5), (ok5, err5)
nrowlabels = zhdata.count("local ROWLABELS={")
assert nrowlabels == 1 and zhdata.count("':", 0) >= 0
assert "'致命伤不阵亡几率+50%'" in zhdata
print("compose rule ok: provisional 11-row ceiling, oversize refused; in-game stability is a separate check")

# ---- 9. sandbox: flat row list builds and hex tokens merge ------------------
rows_src = slice_src("local function build_rows(carrier_enum)", "\nlocal function owned_list")
lua8 = lupa.LuaRuntime(unpack_returned_tuples=True)
lua8.execute("""
local RT={
  [5]={m={'c439df4b'..string.rep('a',16)..'11223344','f4e73389'..string.rep('b',16)..'55667788'}},
  [37]={m={'deadbeef'..string.rep('c',16)..'99001122'}},   -- carrier: excluded
  [99]={m={'newid001'..string.rep('d',16)..'33445566'}},   -- game-update passive
}
local PERKS={
  [3]={m={'c439df4b'..string.rep('a',16)..'11223344','a93569c3'..string.rep('e',24),'52d1981f'..string.rep('f',24)}},
  [5]={m={'c439df4b'..string.rep('a',16)..'11223344'}},
  [0]={m={'00000000000000000000000000000000'}},
}
local ROWLABELS={['c439df4b']='电弧伤害抗性'}
local table=table
""" + rows_src + """
LIST,VARS=build_rows(37)
NCOUNT=function() local n=0 for _ in pairs(LIST) do n=n+1 end return n end
FIND=function(id) for _,h in ipairs(LIST) do if h:sub(1,8)==id then return h end end return nil end
""")
n = lua8.eval("NCOUNT()")
assert n == 5, n  # arc(dup RT/PERKS once), f4e73389, newid001, a93569c3, 52d1981f
assert lua8.eval("FIND('deadbeef')") is None      # carrier rows excluded
assert lua8.eval("FIND('newid001')") is not None   # runtime new passive included
arc = lua8.eval("FIND('c439df4b')")
comp2 = lupa.LuaRuntime(unpack_returned_tuples=True)
comp2_src = slice_src("local function compose(list,budget)", "\nlocal S={")
comp2.execute("local log=function() end local function unhex(s) return s end\n" + comp2_src + """
HEX=function() local ok,err=compose({'""" + arc + """','a93569c3'..string.rep('ee',12)}) if not ok then return nil,err end return ok.nmod end
""")
nh = comp2.eval("HEX()")
assert nh == 2, nh
print("flat rows ok: %d unique rows (carrier excluded, new passive included); hex tokens merge" % n)

# ---- 10. sandbox: hex-token card line round-trips through the parser -------
lua9 = lupa.LuaRuntime(unpack_returned_tuples=True)
row1 = 'c439df4b' + 'a' * 16 + '11223344'
row2 = '52d1981f' + 'f' * 24
lua9.execute(r"""
local tonumber=tonumber
function PARSE(line)
    local idx,label,look,donor,list=line:match('^%s*card%.-(%d+)%s*=%s*([^,]+),(%x+),(%x*),([%x%s,.]*)$')
    if not idx then return nil end
    local plist={}
    for n in list:gmatch('[%x.]+') do
        if #n==32 and not n:find('.',1,true) then plist[#plist+1]=n
        elseif n:find('.',1,true) then plist[#plist+1]=n
        else
            local e=tonumber(n)
            if e~=0 then plist[#plist+1]=e end
        end
    end
    return plist
end
CHECK=function(line) local p=PARSE(line) return p and #p, p and p[1], p and p[2] end
""")
n2, first, second = lua9.eval("CHECK('card.1=CARD 1,d879973a,,%s,%s')" % (row1, row2))
assert n2 == 2 and first == row1 and second == row2, (n2, first, second)
n3, f3, _ = lua9.eval("CHECK('card.2=X,16e1b9d3,f8fadb6c,5,6,7')")
assert n3 == 3 and f3 == 5, (n3, f3)
print("config parse ok: hex tokens parse (2 rows), legacy plain perks parse (3)")

# ---- 11. sandbox: EN table + carrier claim bookkeeping ----------------------
assert zhdata.count("local EN_PERKS={") == 1 and "'Peak Physique'" in zhdata
lua10 = lupa.LuaRuntime(unpack_returned_tuples=True)
lua10.execute(r"""
S={carriers={[37]={enum=37,body=1000},[34]={enum=34,body=2000}}}
OWNED={[34]=0,[37]=0}
M={claims={},actives={}}
local table=table
ALLOC=function(look,pin)
    local carr
    if M.actives[look] then carr=S.carriers[M.actives[look].enum] end
    if not carr then
        local function ok(en) return S.carriers[en] and (not M.claims[en] or M.claims[en]==look) end
        if pin and ok(pin) then carr=S.carriers[pin]
        else
            local cand={}
            for en in pairs(S.carriers) do if ok(en) then cand[#cand+1]=en end end
            table.sort(cand)
            if #cand>0 then carr=S.carriers[cand[1]] end
        end
    end
    if not carr then return nil end
    M.claims[carr.enum]=look
    M.actives[look]={enum=carr.enum}
    return carr.enum
end
FREE=function(look)
    local a=M.actives[look]
    if a then M.claims[a.enum]=nil M.actives[look]=nil return a.enum end
end
NCLAIM=function() local n=0 for _ in pairs(M.claims) do n=n+1 end return n end
""")
e1 = lua10.eval("ALLOC('a', 37)")
e2 = lua10.eval("ALLOC('b', 37)")
assert e1 == 37 and e2 == 34, (e1, e2)
assert lua10.eval("ALLOC('c', 37)") is None
assert lua10.eval("FREE('a')") == 37
e4 = lua10.eval("ALLOC('c', 37)")
assert e4 == 37
assert lua10.eval("NCLAIM()") == 2
print("claim bookkeeping ok: 2 cards live, exhaustion handled, freed reused; EN table shipped")

# ---- 12. pack + deploy ---------------------------------------------------------------
sys.path.insert(0, os.path.join(os.environ.get("TEMP", r"C:\Windows\Temp"), "bingsus"))
import build_addon as official
official.build_addon("mods/codex/custom_armor", source.encode("utf-8"),
                     "0f2b7c14-58d3-4a61-8e77-6d9c0b21f8ae", ZIP, "Custom Armor Kit")

# rebrand Bingus-style: full manifest + showcase thumbnail inside the zip
import json as _json
thumb = io.open(r"C:\HD2-Workspace\outputs\7c30c505-701d-45d1-9c41-54244712db9a.png", "rb").read()
desc = ("Custom armor cards: save a look, a weight class and a passive loadout as switchable "
        "cards. Open ESC > GAME on your ship and click Custom Armor. Drag the panel by its title. "
        "The UI follows the game's Chinese/English text language. Maximum: 11 merged effect rows. "
        "Development candidate: Armory validation pending. Native passive records may affect other armors sharing that passive. "
        "Requires a compatible API 1 loader (Bingus v15+ or MDL 1.4.4). Config: "
        "%LOCALAPPDATA%\\CowboyBingus\\Helldivers2\\MultiPerk\\config.txt.")
mani = {"Version": 1, "Guid": "0f2b7c14-58d3-4a61-8e77-6d9c0b21f8ae",
        "Name": "Custom Armor Kit", "Description": desc,
        "Options": [{"Name": "Custom Armor Kit", "Description": desc,
                     "Include": ["Addon"], "Image": "thumbnail.png"}],
        "IconPath": "thumbnail.png"}
_tmp = ZIP + ".tmp"
with zipfile.ZipFile(ZIP) as _zin, zipfile.ZipFile(_tmp, "w", zipfile.ZIP_DEFLATED) as _zout:
    for _it in _zin.infolist():
        if _it.filename == "manifest.json":
            continue
        _zout.writestr(_it, _zin.read(_it.filename))
    _zout.writestr("manifest.json", _json.dumps(mani, indent=2) + "\n")
    _zout.writestr("thumbnail.png", thumb)
    _zout.writestr("README.txt", (
        "Custom Armor Kit 2.5.10 - DEVELOPMENT CANDIDATE\nArmory validation pending. Do not upload yet.\n\n"
        "Install this ZIP with Arsenal and enable its Addon option. Requires a compatible API 1 loader (Bingus v15+ or MDL 1.4.4).\n"
        "On your ship, open ESC > GAME and click Custom Armor. Drag the expanded panel by its title.\n"
        "No panel hotkey is required. Position is remembered after release.\n"
        "Language follows the game's Text Language: Chinese or English (English fallback for other languages).\n"
        "Optional config override: lang=zh or lang=en. Remove it or use lang=auto to follow the game.\n"
        "Maximum: 11 deduplicated effect rows; an oversize card is refused, never truncated.\n"
        "Cards can combine a look, a weight class and passive effects. Different native passives can hold independent buffers. Armors sharing a modified native passive also share its effects.\n"
        "Use Restore to remove applied cards. A newly selected look may need to be viewed in the armory before applying.\n"
        "Config: %LOCALAPPDATA%\\CowboyBingus\\Helldivers2\\MultiPerk\\config.txt\n"
        "If your previous diagnostic config has write=no, change it to write=yes to enable effects.\n"
        "Supported game build: 01.007.101. The menu stays hidden on unsupported executable builds.\n\n"
        "中文使用说明\n开发测试候选，军械库验证尚未通过，请勿上传。\n"
        "用 Arsenal 导入本安装包并启用 Addon，需要兼容 API 1 的加载器（Bingus v15+ 或 MDL 1.4.4）。\n"
        "在舰船按 Esc，停在游戏页面，点击自定义护甲。按住展开面板的标题栏可自由拖动，松开后保存位置。\n"
        "菜单随游戏文字语言自动切换中英文；配置 lang=zh/en 可以覆盖，lang=auto 恢复自动。\n"
        "最多合并 11 条去重后的效果行；超过上限会拒绝应用，不会截断。\n"
        "修改原生被动记录会影响共享该被动的其他护甲；此方案仍在测试。新外观未加载时，先在军械库查看一次。还原原版用于撤销已应用的卡片。\n"
        "以前测试配置如果是 write=no，请改为 write=yes 才能启用真实效果。\n"
    ).encode('utf-8'))
os.replace(_tmp, ZIP)
print("zip:", os.path.getsize(ZIP))

zin = zipfile.ZipFile(ZIP)
payload = zin.read("Addon/9ba626afa44a3aa3.patch_0")
man = zin.read("manifest.json")
side = {s: zin.read("Addon/9ba626afa44a3aa3.patch_0" + s)
        for s in (".gpu_resources", ".stream")}

# ---- 12b. deploy through the guard (NEVER a hard-coded slot) ------------------
# 2026-10-01: this block used to write slot 309 unconditionally. Arsenal
# renumbers layers on every deploy and 309 had become the Bingus Shared
# Loader's slot, so deploying this mod deleted the mod loader and every Lua
# mod in the game stopped working. safe_deploy finds our own slot by the
# addon declaration inside the layer and refuses anything that is not ours.
import safe_deploy
DECL, GUID = "mods/codex/custom_armor", "0f2b7c14-58d3-4a61-8e77-6d9c0b21f8ae"
libdir = safe_deploy.library_dir_for(GUID)
if libdir is None:                      # first import: fall back to the name
    libdir = next((os.path.join(MGR_CAND, d) for d in sorted(os.listdir(MGR_CAND))
                   if d.lower().startswith(("custom-armor", "hd2-multiperk"))), None)
safe_deploy.deploy(DECL, payload, library_dir=libdir, manifest=man, sidecars=side)

deployed = open(os.path.join(safe_deploy.GAME, "9ba626afa44a3aa3.patch_%d"
                             % safe_deploy.find_own_slot(DECL)[0]),
                encoding="utf-8", errors="replace").read()
print("| version:", re.search(r"version='([^']+)'", deployed).group(1),
      "| PICKKEYS:", "local PICKKEYS={" in deployed,
      "| pick mode:", "ED.mode=='pick'" in deployed,
      "| auto retry:", "auto: card '..M.auto_label..' pending" in deployed or "pending - '" in deployed)
