"""An Armory visibility probe must never allocate GUIs into other worlds."""
from pathlib import Path
import lupa

source = Path(__file__).with_name('multi_perk.lua').read_text(encoding='utf-8')
def cut(a, b):
    start = source.index(a)
    return source[start:source.index(b, start)]

lua = lupa.LuaRuntime(unpack_returned_tuples=True)
lua.execute(r'''
M={conf_armory_worlds=true,gate_info={ui_screen_allowed=true}}
PANEL={world='ship'}
CALLS={}
stingray={World={create_screen_gui=function(world,...)
    CALLS[#CALLS+1]=world; return 'owned-gui'
end},Gui={},IdString64={from_hex=function(x)return x end},
Vector2=function()end,Vector3=function()end,Color=function()end,
Application={worlds=function() return {'ship','native-ui','preview'} end}}
function log() end
function world_serial() return 1 end
''' + cut('local function ladder_step(', '\n-- Read-only menu rendering diagnostic') + r'''
assert(ladder_step(1,{},1920,1080))
assert(#CALLS==1 and CALLS[1]=='ship',
    'Armory probe allocated a GUI into another world: '..#CALLS)
''')
print('PASS Armory probe creates only its own ship-world GUI')
