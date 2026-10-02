"""ESC host integration never revives a hidden menu through the old ship latch."""
from pathlib import Path
import lupa
source=Path(__file__).with_name('multi_perk.lua').read_text(encoding='utf-8')
a=source.index('local VISIBILITY')
b=source.index('\nPANEL={',a)
lua=lupa.LuaRuntime(unpack_returned_tuples=True)
lua.execute(r'''
M={conf_fallback=true,gate_latched=true}
LOGS={}
function log(s)LOGS[#LOGS+1]=s end
VISBRIDGE={}
stingray={}
ShipVisibility={new=function(engine,bridge,options)
    OPTIONS=options
    return {sample=function()return SAMPLES()end}
end}
SAMPLES=function()return false,'escape_closed','menu',{ui_idle=true}end
'''+source[a:b]+r'''
local ok,why=MP_GATE.visible()
assert(not ok and why=='escape_closed','old latch revived a closed ESC menu')
assert(OPTIONS.escape_only and #OPTIONS.ui_allow==1 and OPTIONS.ui_allow[1]==1,
    'host must request only ESC/GAME')
SAMPLES=function()return true,'ship_screen_1','menu',{ui_idle=false,ui_screen_allowed=true}end
ok,why=MP_GATE.visible()
assert(ok,'host rejected the native menu gate')
MP_GATE.heartbeat(10,ok,why,'menu')
assert(#LOGS==1 and LOGS[1]:find('ship_screen_1',1,true),'menu reason missing from heartbeat')
SAMPLES=function()return false,'escape_other_tab','menu',{ui_idle=false}end
ok,why=MP_GATE.visible()
assert(not ok,'OPTIONS tab was revived by the old latch')
''')
print('PASS ESC host authorization, immediate hiding and heartbeat reason')
