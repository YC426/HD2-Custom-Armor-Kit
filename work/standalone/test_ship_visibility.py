"""Execute the actual read-only Lua visibility gate with scene/API fixtures."""
from pathlib import Path
import unittest
from lupa import LuaRuntime


class ShipVisibilityTest(unittest.TestCase):
    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        source = Path(__file__).with_name('ship_visibility.lua').read_text(encoding='utf-8')
        self.lua.globals().module = self.lua.execute(source)
        self.lua.execute(r'''
        function p32(n)
            return string.char(n%256,math.floor(n/256)%256,math.floor(n/65536)%256,math.floor(n/16777216)%256)
        end
        function patch_state(offset,value)
            native_state=native_state:sub(1,offset)..p32(value)..native_state:sub(offset+5)
        end
        active=true; main='ship'; main_calls=0; native_reads=0; corrupt_second=false
        scene_markers=true; marker_alive=true; marker_count=1; secondary_markers=false
        engine={
            Application={main_world=function() main_calls=main_calls+1;return main end,worlds=function() return {'ship','ui','mission'} end},
            World={units_by_resource=function(w,id)
                if (scene_markers and w=='ship') or (secondary_markers and w=='ui') then
                    local units={};for i=1,marker_count do units[i]=id..i end;return units
                end
                return {}
            end},
            Unit={alive=function() return marker_alive end},
            IdString64={from_hex=function(hash) return hash end},
            Network={game_session=function() return active and 'session' or nil end},
            GameSession={in_session=function() return active end},
        }
        native_state=string.rep('\0',0x90)
        bridge={base=0x100000, game_sha256=module.game_sha256,exe_sha256=module.exe_sha256,
            verify=function() return true end,
            read=function(at,n)
                if n==8 then return p32(0x200000)..p32(0) end
                native_reads=native_reads+1
                if corrupt_second and native_reads>1 then return string.rep('\1',n) end
                return native_state
            end,
        }
        gate=module.new(engine,bridge)
        ''')

    def sample(self):
        return self.lua.eval('gate.sample()')

    def blocked(self, setup, reason):
        self.lua.execute(setup)
        result = self.sample()
        self.assertFalse(result[0], result)
        self.assertIn(reason, result[1])

    def test_ship_first_sample_is_visible_without_delay(self):
        result = self.sample()
        self.assertTrue(result[0], result)
        self.assertEqual(result[1], 'ship_idle')
        self.assertEqual(result[2], 'ship')
        self.assertTrue(result[3]['ui_idle'])

    def test_title_many_worlds_still_hidden(self):
        self.blocked("active=false; engine.Application.worlds=function() return {'ship','a','b','c','d','e','f','g','h'} end", 'not_in_session')

    def test_title_even_with_session_but_no_scene_markers(self):
        self.blocked('scene_markers=false', 'ship_marker_absent')

    def test_mission_with_ship_retained_in_other_world(self):
        self.blocked("main='mission';secondary_markers=true", 'ship_marker_absent')

    def test_unlisted_world(self):
        self.blocked("main='stale'", 'main_world_unlisted')

    def test_dead_marker_during_unload(self):
        self.blocked('marker_alive=false', 'ship_marker_dead')

    def test_marker_bounds(self):
        self.blocked('marker_count=17', 'ship_marker_absent')

    def test_tab_galactic_map(self):
        self.blocked('patch_state(0,15);patch_state(0x1c,1)', 'native_ui_busy')

    def test_f8_briefing(self):
        self.blocked('patch_state(0,14);patch_state(0x1c,1)', 'native_ui_busy')

    def test_pending_menu_hides_before_presenter_opens(self):
        self.blocked('patch_state(4,14)', 'native_ui_busy')

    def test_modal_or_stack_without_current_presenter(self):
        self.blocked('patch_state(0x1c,1)', 'native_ui_busy')

    def test_secondary_ui_pending(self):
        self.blocked('patch_state(0x8c,1)', 'native_ui_busy')

    def test_secondary_ui_active(self):
        self.blocked('patch_state(0x84,1)', 'native_ui_busy')

    def test_snapshot_changed_in_read(self):
        self.blocked('corrupt_second=true', 'ui_transitioning')

    def test_scene_changed_between_reads(self):
        # The closing identity check re-runs the marker scene: if the ship
        # unloads mid-read the sample must fail closed rather than authorize on
        # a scene that no longer exists.
        self.blocked('scene_reads=0;'
                     'engine.World.units_by_resource=function(w,id)'
                     '  if (scene_markers and w=="ship") or (secondary_markers and w=="ui") then'
                     '    scene_reads=scene_reads+1'
                     '    if scene_reads>3 then return {} end'
                     '    local units={};for i=1,marker_count do units[i]=id..i end;return units'
                     '  end'
                     '  return {}'
                     'end', 'ship_marker_absent')

    def test_menu_closure_restores_immediately(self):
        self.lua.execute('patch_state(0,15)')
        self.assertFalse(self.sample()[0])
        self.lua.execute('patch_state(0,0)')
        self.assertTrue(self.sample()[0])

    def test_build_unknown(self):
        self.blocked("bridge.game_sha256='unsupported'", 'native_build_unverified')

    def test_missing_network_provider_is_a_hard_failure(self):
        self.blocked('engine.Network={}', 'session_api_unavailable')

    def test_missing_session_provider_does_not_block_the_ship(self):
        self.lua.execute('engine.GameSession={}')
        self.assertTrue(self.sample()[0])

    def test_native_unreadable(self):
        self.blocked('bridge.read=function() return nil end', 'ui_unavailable')

    def test_failed_id_conversion_cannot_cache_an_incomplete_guard(self):
        self.lua.execute('engine.IdString64.from_hex=function() return nil end')
        self.assertFalse(self.sample()[0])
        self.assertFalse(self.sample()[0])
        self.lua.execute('engine.IdString64.from_hex=function(hash) return hash end;scene_markers=false')
        self.assertFalse(self.sample()[0])


if __name__ == '__main__':
    unittest.main(verbosity=2)
