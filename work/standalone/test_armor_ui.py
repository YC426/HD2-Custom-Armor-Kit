"""Exercise real retained UI lifecycle functions with an engine GUI boundary."""
from pathlib import Path
import lupa

source = Path(__file__).with_name('multi_perk.lua').read_text(encoding='utf-8')
def cut(a,b):
    start=source.index(a)
    return source[start:source.index(b,start)]

runtime=lupa.LuaRuntime(unpack_returned_tuples=True)
runtime.execute(r'''
LIVE={[1]=true}
CREATED=1
stingray={Gui={resolution=function() return 1920,1080 end},World={
    destroy_gui=function(world,gui) LIVE[gui]=nil end}}
M={ship_ok=true,ship_world='ship',ui_font=1,ui_material=1}
PANEL={world='ship',gui=1,sig='old',ladder_done=true,ladder=9,lnext=0,
    lfail=0,regions={},retry=0,keys={},was_down=false}
ED={perks={},mode='cards'}
S={kits={},carriers={},kits_n=1}
LNAMES={'create','bind','skip3','skip4','skip5','draw','skip7','finish'}
function log() end
function sample_input() return nil end
function panel_drag()return false end
function panel_offset()return 0,0 end
function kits_ready() return true end
-- ui_frame's armory diagnostic (temporary instrumentation) is a pure logger
-- defined outside this slice; M.gate_info is nil here so it would no-op anyway.
function ui_diag() end
-- free_cursor touches user32 (ShowCursor/ClipCursor) and lives outside this
-- slice too; the lifecycle under test does not depend on it.
function free_cursor() end
function ladder_step(step)
    if step==1 then CREATED=CREATED+1 LIVE[CREATED]=true PANEL.gui=CREATED end
    return true
end
''' + cut('local function panel_clear()', '\nlocal function save_panel_position') + '\n' +
                cut('local function ui_frame(', '\nlocal function rewrite_config_ui_auto') + r'''
local conf={cards={}}
ui_frame(conf,100)
ui_frame(conf,101)
local count=0 for _ in pairs(LIVE)do count=count+1 end
assert(count==1,'retained rebuild leaked '..count..' live GUI objects')
assert(CREATED==2,'second frame recreated an already rebuilt GUI')
panel_clear()
assert(next(LIVE)==nil,'clearing menu must destroy every displayed GUI')
assert(not PANEL.ladder_done and PANEL.ladder==1,'cleared GUI restarts bring-up on return')
M.ship_ok=false
ui_frame(conf,102)
assert(next(LIVE)==nil,'non-ship state cannot create or draw GUI')
M.ship_ok=true
PANEL.open=false
u={GetAsyncKeyState=function()return -32768 end}
function game_focused()return true end
ui_frame({cards={},vk=0x4c,keyname='L'},103)
assert(PANEL.open==false,'removed panel hotkey still opens the menu')
PANEL.ladder_done=false PANEL.ladder=1 PANEL.lnext=0 PANEL.lfail=0
for frame=1000,1008 do ui_frame(conf,frame) end
assert(PANEL.ladder_done,'verified menu bring-up must finish in eight frames without fixed waits')
''')
print('PASS actual UI retained rebuild, hide, re-arm lifecycle')

# Exercise the real cards branch: two cards with the same look still need
# distinct visible names, otherwise the user cannot select a named probe.
start=source.index("    if ED.mode=='cards' then\n        for i,cd in ipairs(cards)")
end=source.index("    elseif ED.mode=='edit' then",start)
card_ui=lupa.LuaRuntime(unpack_returned_tuples=True)
card_ui.execute("""
local cards={{label='CARD A',look=123,perks={7}},{label='CARD B',look=123,perks={5}}}
local ED={mode='cards'}
local PANEL={regions={}}
local scale,rowh,pw,x,ry,zcell,acell=1,54,560,0,500,1,3
local white,muted,gold={},{},{}
local labels={}
function is_card_active()return false end
function rect()end
function color()return {} end
function armorname()return 'SAME ARMOR' end
function button()end
function L(s)return s end
function txt(x,y,s)labels[s]=true;return x+#s*15 end
"""+source[start:end]+"""
end
assert(labels['CARD A'] and labels['CARD B'],'cards sharing an armor must display their own labels')
assert(labels['SAME ARMOR'],'armor name remains visible alongside the card name')
""")
print('PASS same-armor cards display distinct card labels and armor identity')
