"""Exercise actual initialization gates and carrier readiness helpers."""
from pathlib import Path
import lupa
import struct
source=Path(__file__).with_name('multi_perk.lua').read_text(encoding='utf-8')
def cut(a,b):
    i=source.index(a)
    return source[i:source.index(b,i)]
lua=lupa.LuaRuntime(unpack_returned_tuples=True, encoding=None)
state=bytearray(0x90)
owner=0x200000
slot=0x100000+0x347ce28
changed=False
reads=0
def read(at,n):
    global reads
    reads+=1
    if at==slot: return struct.pack('<Q',owner)
    if at==owner+0x4294:
        raw=bytearray(state)
        if changed and reads>=4: struct.pack_into('<I',raw,4,5)
        return bytes(raw)
    return None
def set_state(current=0,pending=0,depth=0,top=0,secondary=0,secondary_pending=0):
    global reads
    reads=0
    state[:]=bytes(0x90)
    for offset,value in ((0,current),(4,pending),(8,top),(0x1c,depth),(0x84,secondary),(0x8c,secondary_pending)):
        struct.pack_into('<I',state,offset,value)
lua.globals().rd=read
lua.globals().u32=lambda raw,offset: struct.unpack_from('<I',raw,offset)[0]
lua.globals().u64=lambda raw,offset: struct.unpack_from('<Q',raw,offset)[0]
set_state()
lua.execute('''
M={gate_info={in_session=true,ui={screen=0}}}
VERIFIED=true
WORLDS=11
VISBRIDGE={base=0x100000,verify=function()return VERIFIED end}
function ui_world_count()return WORLDS end
'''.encode()+cut('local function data_ship_ready()', '\n-- Unattended development driver').encode()+b'''
data_ready=data_ship_ready
assert(data_ship_ready(),'closed ESC ship must initialize armor')
M.ship_ok=false
assert(data_ship_ready(),'render gate must not prevent data initialization')
M.gate_info.ui.screen=5
assert(data_ship_ready(),'stale render diagnostics must not block a fresh idle presenter')
M.gate_info.ui.screen=0
WORLDS=7
assert(not data_ship_ready(),'mission must not scan or rewrite armor')
WORLDS=11
VERIFIED=false
assert(not data_ship_ready(),'unsupported build cannot initialize')
VERIFIED=true
M.gate_info.in_session=false
assert(not data_ship_ready(),'absent session cannot initialize')
M.gate_info.in_session=true
''')
for kwargs in (
    dict(current=5,depth=1,top=5),
    dict(pending=5),dict(secondary=5),dict(secondary_pending=5),
    dict(current=1,depth=2,top=1),dict(current=1,depth=1,top=5),
    dict(current=0,depth=1,top=5),
):
    set_state(**kwargs)
    assert not lua.globals().data_ready(), kwargs
set_state(current=1,depth=1,top=1)
assert lua.globals().data_ready(), 'stable ESC permits initialization'
set_state()
changed=True
assert not lua.globals().data_ready(), 'native transition between reads must reject writes'
changed=False
lua.execute('''
S={kits={[100]={body=100},[200]={body=200}},carriers={[10]={},[31]={}}}
OWNED={[10]=5,[31]=1,[37]=0}
HEADS={[100]={look=100,native=10},[200]={look=200,native=31}}
function rd(at,n)return HEADS[at]end
function u32(h,o)return o==0 and h.look or h.native end
'''.encode()+cut('local function scan_targets_ready(', '\nlocal function scan(').encode()+b'''
local conf={want_items={[100]=true,[200]=true}}
assert(scan_targets_ready(conf),'distinct native carriers must finish scanning')
S.carriers[31]=nil
assert(not scan_targets_ready(conf),'one carrier cannot satisfy two targets')
S.carriers[37]={}
assert(scan_targets_ready(conf),'unowned fallback can supply a second target')
HEADS[200].look=999
assert(not scan_targets_ready(conf),'moved kit must restart discovery')
assert(S.kits[200]==nil,'invalid kit must be discarded')
''')
print('PASS idle/ESC initialization, fresh presenter and transition guards, distinct carrier readiness; scene/gameplay validation remains separate')
