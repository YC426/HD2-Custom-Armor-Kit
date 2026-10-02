"""Behavioral regression checks using the real compose/apply/restore functions.

Only the OS memory boundary is simulated. No game or user config is touched.
"""
from pathlib import Path
import sys

path = Path(__file__).with_name('simtest.py')
text = path.read_text(encoding='utf-8')
namespace = {'__file__': str(path), '__name__': '__test_harness__'}
exec(compile(text[:text.index('L.execute(MOCK)')], str(path), 'exec'), namespace)

regressions = r'''
T('oxygenator_retains_native_hidden_running_row',function()
    local data,why=compose({38},11)
    assert(data and data.nmod==#PERKS[38].m,why or 'hidden running row was discarded')
    assert(data.mods==unhex(table.concat(PERKS[38].m)),'all native oxygenator bytes must survive')
end)
T('dynamic_reload_retains_native_stat_array',function()
    M.statrows=false -- legacy config cannot disable actual gameplay data
    local data,why=compose({16},11)
    assert(data and data.nstat==#PERKS[16].s,why or 'dynamic reload/ammo array was discarded')
    assert(data.stats==unhex(table.concat(PERKS[16].s)),'native reload/ammo values and types must survive')
end)
T('hidden_row_token_is_a_real_effect',function()
    local data,why=compose({'38.2'},11)
    assert(data and data.nmod==1 and data.mods==unhex(PERKS[38].m[2]),why or 'hidden row became empty')
end)
T('native_passive_carrier_preserves_identity',function()
    restore_all()
    local en=u32(rd(kit_body,32),28)
    local p=PERKS[en]
    assert(p,'native passive fixture exists')
    local body=mem_alloc(56+16*16,4)
    wr_raw(body,p32(en)..p32(p.n)..string.rep('\0',8)..p64(body+56)..p64(#p.m)..string.rep('\0',16)..unhex(table.concat(p.m)))
    S.carriers[en]={body=body,enum=en,head=rd(body,56)}
    assert(apply_card(mkcard({7}),CONF))
    assert(u32(rd(kit_body,32),28)==en,'keep the armor native passive reference')
    assert(u32(rd(body,56),4)==p.n,'keep native display metadata')
    restore_all()
    S.carriers[en]=nil
end)
T('two_native_cards_have_separate_effects_and_restore',function()
    restore_all()
    local kits,carriers={},{}
    local first
    for en=3,7,4 do
        local p=PERKS[en]
        local body=mem_alloc(56+16*16,4)
        wr_raw(body,p32(en)..p32(p.n)..string.rep('\0',8)..p64(body+56)..p64(#p.m)..string.rep('\0',16)..unhex(table.concat(p.m)))
        carriers[en]={body=body,enum=en,head=rd(body,56)}
        S.carriers[en]=carriers[en]
    end
    local look2
    for id in pairs(PIECES) do if id~=LOOK then look2=id break end end
    local body2=mem_alloc(0x98+0x60*(#PIECES[look2]+1)+64,4)
    wr_raw(body2,p32(look2)..string.rep('\0',24)..p32(7))
    local old=S.kits[look2]
    S.kits[look2]={body=body2,head=rd(body2,32)}
    assert(apply_card({label='NATIVE A',look=LOOK,perks={3,5}},CONF))
    first=rd(carriers[3].body,56)
    local bytes=rd(u64(first,16),u64(first,24)*16)
    assert(apply_card({label='NATIVE B',look=look2,perks={7,20}},CONF))
    assert(u32(rd(kit_body,32),28)==3 and u32(rd(body2,32),28)==7,'both native passive references retained')
    assert(rd(carriers[3].body,56)==first and rd(u64(first,16),#bytes)==bytes,'second card cannot rewrite the first')
    assert(u32(first,4)==PERKS[3].n and u32(rd(carriers[7].body,56),4)==PERKS[7].n,'both native display identities retained')
    restore_all()
    for en,record in pairs(carriers) do
        assert(u64(rd(record.body,56),16)==record.body+56,'each original inline pointer restored')
        S.carriers[en]=nil
    end
    S.kits[look2]=old
end)
T('empty_stat_array_restores_zero_header',function()
    M.statrows=false
    assert(apply_card(mkcard({7}),CONF))
    local head=rd(carrier_body,56)
    assert(u64(head,40)==0,'stat rows stay disabled')
    assert(u64(head,32)==0,'zero-row array retains the baseline zero header')
    restore_all()
end)
T('disabled_writes_never_report_applied',function()
    local before=rd(kit_body,32)
    local ok,why=apply_card(mkcard({7}),{write=false})
    assert(not ok and why:find('write=no',1,true),'disabled writes must not report success')
    assert(rd(kit_body,32)==before,'disabled writes leave the record unchanged')
end)
T('runtime_unknown_passive_applies_and_existing_runtime_wins',function()
    local row='12345678'..string.rep('f',16)..'01000000'
    RT[99]={n=123,m={row}}
    local d,why=compose({99},16)
    assert(d and d.nmod==1 and d.mods==unhex(row) and d.name==123,why)
    RT[7]={m={row}}
    local changed,reason=compose({7},16)
    assert(changed and changed.mods==unhex(row) and changed.name==PERKS[7].n,reason)
    RT[7],RT[99]=nil,nil
end)
T('two_cards_keep_independent_effect_bytes',function()
    restore_all()
    local owned34=OWNED[34]
    OWNED[34]=0 -- explicit fixture: a second UNUSED passive exists
    local h34=mem_alloc(56+16*16,4)
    wr_raw(h34,p32(34)..p32(PERKS[34].n)..string.rep('\0',8)
        ..p64(h34+56)..p64(#PERKS[34].m)..string.rep('\0',16)
        ..unhex(table.concat(PERKS[34].m)))
    S.carriers[34]={body=h34,enum=34,head=rd(h34,56)}
    S.carriers[37]=S.carrier
    local look2
    for id in pairs(PIECES) do if id~=LOOK then look2=id break end end
    local body2=mem_alloc(0x98+0x60*(#PIECES[look2]+1)+64,4)
    wr_raw(body2,p32(look2)..string.rep('\0',24)..p32(3))
    S.kits[look2]={body=body2,head=rd(body2,32)}
    local a={label='MULTI A',look=LOOK,perks={7}}
    local b={label='MULTI B',look=look2,perks={5}}
    assert(apply_card(a,CONF))
    local enum_a=u32(rd(kit_body,32),28)
    local head_a=rd(S.carriers[enum_a].body,56)
    local ptr_a=u64(head_a,16)
    local bytes_a=rd(ptr_a,u64(head_a,24)*16)
    assert(apply_card(b,CONF))
    local enum_b=u32(rd(body2,32),28)
    assert(enum_a~=enum_b,'both cards point at shared enum '..enum_a..'; second card overwrites the first')
    assert(rd(ptr_a,#bytes_a)==bytes_a,'first card effect buffer stays intact')
    assert(u64(rd(S.carriers[enum_a].body,56),16)==ptr_a,'first card carrier pointer stays intact')
    restore_all()
    assert(u32(rd(kit_body,32),28)==3 and u32(rd(body2,32),28)==3,'both original passive references restored')
    assert(u64(rd(h34,56),16)==h34+56,'second carrier original pointer restored')
    OWNED[34]=owned34
end)
T('owned_carrier_refused_without_overwriting_first_card',function()
    restore_all()
    assert(OWNED[34]>0,'fixture must use the actual account owned count')
    assert(apply_card(mkcard({7}),CONF))
    local before=rd(carrier_body,56)
    local look2
    for id in pairs(S.kits) do if id~=LOOK then look2=id break end end
    assert(look2,'second card look remains from previous fixture')
    local kit2=S.kits[look2]
    local vanilla=rd(kit2.body,32)
    local ok,why=apply_card({label='OWNED REFUSAL',look=look2,perks={5}},CONF)
    assert(not ok and why:find('unused independent carrier',1,true),why)
    assert(rd(carrier_body,56)==before,'first card header remains intact')
    assert(rd(kit2.body,32)==vanilla,'refused look remains vanilla')
    restore_all()
end)
T('compose_budget_11_boundary_and_dedup',function()
    local rows={}
    for i=1,12 do rows[i]=string.format('%08x',i)..string.rep('0',16)..'01000000' end
    local sixteen={}
    for i=1,11 do sixteen[i]=rows[i] end
    local d,why=compose(sixteen,16)
    assert(d and d.nmod==11 and #d.mods==176,why)
    local excess,reason=compose(rows,16)
    assert(excess==nil and reason:find('budget',1,true),'12th unique row must refuse the entire merge')
    sixteen[12]=rows[1]
    local repeatset=compose(sixteen,16)
    assert(repeatset and repeatset.nmod==11,'duplicate row consumes no extra budget')
    local second=rows[1]:sub(1,8)..string.rep('f',16)..'02000000'
    local dedup=compose({rows[1],second},16)
    assert(dedup and dedup.nmod==1 and dedup.mods==unhex(rows[1]),'same effect id deduplicates with first row retained')
end)
T('restore_guard_failure_keeps_snapshot_for_retry',function()
    restore_all()
    assert(apply_card(mkcard({7}),CONF))
    mem_find(kit_body).prot=0x104
    restore_all()
    assert(M.snaps and M.snaps[LOOK],'failed restore must retain original snapshot for safe retry')
    mem_find(kit_body).prot=4
    restore_all()
    assert(u32(rd(kit_body,32),28)==3,'retry restores the original passive')
end)
T('blocked_look_write_rolls_back_carrier_and_claim',function()
    restore_all()
    local before=rd(carrier_body,56)
    mem_find(kit_body).prot=0x104
    local ok,why=apply_card(mkcard({7}),CONF)
    mem_find(kit_body).prot=4
    assert(not ok and why:find('passive field write',1,true),why)
    assert(rd(carrier_body,56)==before,'carrier restored when look write fails')
    assert(not (M.actives and M.actives[LOOK]),'failed card never becomes active')
    assert(not (M.claims and M.claims[37]),'failed card never claims a carrier')
    assert(S.carriers[37].name_now==nil,'rollback cannot leave stale ownership state')
    restore_all()
end)
'''
mock = namespace['MOCK'].replace('RESULTS=R', regressions + '\nRESULTS=R')
runtime = namespace['L']
runtime.execute(mock)
fails = 0
for i in range(1, int(runtime.eval('#RESULTS')) + 1):
    item = runtime.eval(f'RESULTS[{i}]')
    print(('PASS  ' if item['ok'] else 'FAIL  ') + item['name'] +
          ('' if item['ok'] else ' -> ' + str(item['err'])))
    fails += not bool(item['ok'])
print(f'{runtime.eval("#RESULTS") - fails}/{runtime.eval("#RESULTS")} passed')
sys.exit(1 if fails else 0)
