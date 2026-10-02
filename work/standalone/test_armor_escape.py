"""Real native-menu gate: ESC/GAME only, using the menu render world."""
from pathlib import Path
from lupa import LuaRuntime
lua=LuaRuntime(unpack_returned_tuples=True)
lua.globals().module=lua.execute(Path(__file__).with_name('ship_visibility.lua').read_text(encoding='utf-8'))
lua.execute(r'''
function p32(n)return string.char(n%256,math.floor(n/256)%256,math.floor(n/65536)%256,math.floor(n/16777216)%256)end
function ptr(n)return p32(n)..p32(0)end
screen,tab=0,0
worlds={'main','menu','w3','w4','w5','w6','w7','w8','w9'}
function state()
    return p32(screen)..p32(0)..p32(screen)..string.rep('\0',16)..p32(screen==0 and 0 or 1)..string.rep('\0',0x70)
end
engine={Application={main_world=function()return 'main'end,worlds=function()return worlds end},
    World={units_by_resource=function()return {}end},Unit={alive=function()return true end},
    IdString64={from_hex=function(x)return x end},Network={game_session=function()return 'session'end},
    GameSession={in_session=function()return true end}}
bridge={base=0x100000,game_sha256=module.game_sha256,exe_sha256=module.exe_sha256,
verify=function()return true end,read=function(at,n)
    if at==0x100000+0x347ce28 then return ptr(0x200000)end
    if at==0x200000+0x4294 then return state()end
    if at==0x100000+0x347ce38 then return ptr(0x300000)end
    if at==0x300000+200 then return ptr(0x400000)end
    if at==0x400000+58700 then return p32(tab)end
    return nil
end}
gate=module.new(engine,bridge,{session_required=false,world_scope='count',ui_allow={1},escape_only=true})
local ok=gate.sample()
assert(not ok,'ESC-only gate authorized an idle ship/title scene')
screen=5
assert(not gate.sample(),'Armory must hide the ESC panel')
screen=1;tab=2
assert(not gate.sample(),'OPTIONS tab must hide the ESC panel')
tab=0
assert(not gate.sample(),'ESC opening must wait for stable samples')
assert(not gate.sample(),'two samples are not a stable menu')
local good,why,world=gate.sample()
assert(good and world=='menu','stable GAME tab must render on the first non-main world: '..tostring(why))
screen=0
assert(not gate.sample(),'closing ESC must hide immediately')
screen=1;worlds={'main','menu','w3','w4','w5','w6','w7'}
assert(not gate.sample(),'mission world list must stay hidden')
''')
print('PASS ESC/GAME-only, three-sample stability, menu render world, close and mission hide')
