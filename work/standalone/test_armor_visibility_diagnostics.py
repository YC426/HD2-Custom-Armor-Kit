"""Test actual diagnostics: gate heartbeat reasons, rate limiting, and the
bounded read-only scene survey."""
from pathlib import Path
import re
import lupa

source = Path(__file__).with_name('multi_perk.lua').read_text(encoding='utf-8')


def slice_between(start_marker, end_marker):
    start = source.find(start_marker)
    assert start >= 0, start_marker
    end = source.index(end_marker, start)
    return source[start:end]


shipping = slice_between('local VISIBILITY', '\nPANEL={')
# health of the slice: both functions must be present
assert 'gate_heartbeat' in shipping, 'gate_heartbeat missing from gate slice'
assert 'visibility_diagnostics' in shipping, 'visibility_diagnostics missing from gate slice'

runtime = lupa.LuaRuntime(unpack_returned_tuples=True)
runtime.execute(r'''
M={}
LOGS={}
CALLS=0
function log(text) LOGS[#LOGS+1]=text end
VISBRIDGE={verify=function() return false end}
function u32() error('native read before build verification') end
function u64() error('native read before build verification') end
function rd() error('native read before build verification') end
stingray={
    Application={main_world=function() return 'w1' end,worlds=function()
        local worlds={}for i=1,30 do worlds[i]='w'..i end return worlds end},
    Network={game_session=function() return 'session' end},
    GameSession={in_session=function() return true end},
    IdString64={from_hex=function(hash) return hash end},
    Unit={alive=function(unit) return true end},
    World={units_by_resource=function(world,id) CALLS=CALLS+1 return {world..id} end},
}
''' + shipping + r'''
-- 1. a blocked gate always names its reason, immediately and again on change.
M={} LOGS={}
gate_heartbeat(2,false,'not_in_session','w1')
assert(#LOGS==1,'first blocked heartbeat must be logged')
assert(LOGS[1]:find('not_in_session',1,true),'first heartbeat carries the actual reason')
assert(LOGS[1]:find('blocked',1,true),'heartbeat says blocked')
local first=#LOGS
for frame=3,500 do gate_heartbeat(frame,false,'not_in_session','w1') end
assert(#LOGS==first,'an unchanged reason must stay quiet inside the period')
gate_heartbeat(603,false,'not_in_session','w1')
assert(#LOGS==first+1,'a blocked gate must report again after 600 frames')
gate_heartbeat(604,false,'native_ui_busy','w1')
assert(LOGS[#LOGS]:find('native_ui_busy',1,true),'a changed reason is reported at once')
gate_heartbeat(605,true,'ship_idle','w1')
assert(LOGS[#LOGS]:find('visible',1,true),'successful visibility is reported')

-- 2. the heartbeat reports the observed signals the gate handed it
M={} LOGS={}
M.gate_info={session=true,in_session=false,fallback=true,marker_counts={1,1,1},ui_idle=true}
gate_heartbeat(2,false,'confirming_markers(3)','w1')
assert(LOGS[1]:find('in_session=false',1,true),'heartbeat shows the session verdict')
assert(LOGS[1]:find('markers=3',1,true),'heartbeat shows the marker count')
assert(LOGS[1]:find('ui_idle=true',1,true),'heartbeat shows native UI idleness')

-- 3. the scene survey is bounded, runs once, and only after the gate authorizes
M={} LOGS={} CALLS=0
local real_network=stingray.Network.game_session
local real_ids=stingray.IdString64.from_hex
M.ship_ok=false
visibility_diagnostics(2,{})
assert(CALLS==0,'no survey before the gate authorizes a ship scene')
M.ship_ok=true
visibility_diagnostics(3,{session=true,in_session=false,fallback=true})
assert(CALLS==48,'one survey is bounded to 16 worlds x 3 markers, got '..CALLS)
local survey_logs=#LOGS
visibility_diagnostics(4,{session=true,in_session=false,fallback=true})
assert(CALLS==48,'the survey must not repeat')
assert(#LOGS==survey_logs,'the survey must not repeat its logging either')
M={} LOGS={} CALLS=0
stingray.IdString64.from_hex=function() return nil end
M.ship_ok=true
visibility_diagnostics(3,{})
assert(CALLS==0,'nil marker conversion must never call native units_by_resource')
stingray.IdString64.from_hex=real_ids
stingray.Network.game_session=real_network
''')
print('PASS gate heartbeat names every reason, stays quiet inside the period, '
      'reports the observed signals, and the survey is bounded, one-shot and '
      'authorized-only')
