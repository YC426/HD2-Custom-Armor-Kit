"""World-scope coverage for the ship gate.

The live 2026-10-01 11:13 run proved that Application.main_world() is not
necessarily the ship world on this build: with a real session and
GameSession.in_session() == true, the main world carried 0 of the 3 ship marker
resources for more than 18,000 frames, so the 2.5.7 gate hid the panel for the
whole run. These tests pin both behaviours:

* world_scope='main' keeps the old single-world assumption (and still fails
  closed on a non-ship main world),
* world_scope='any' finds the world that actually carries the markers, prefers
  a world that already proved to be the ship, and still refuses a scene with no
  qualifying world.
"""
from pathlib import Path
import unittest
from lupa import LuaRuntime


class WorldScopeTest(unittest.TestCase):
    def build(self, world_scope='any', in_session='true'):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        source = Path(__file__).with_name('ship_visibility.lua').read_text(encoding='utf-8')
        self.lua.globals().module = self.lua.execute(source)
        self.lua.execute(r'''
        function p32(n)
            return string.char(n%256,math.floor(n/256)%256,math.floor(n/65536)%256,math.floor(n/16777216)%256)
        end
        SESSION_FLAG=__IN_SESSION__
        native_state=string.rep('\0',0x90)
        SCANS=0
        -- 'ui' is main but carries no markers; 'ship' carries all three.
        MAIN='ui'
        SHIP={'ship','ship2','ship3'}
        MARKERS={'be0be6b1875a4a66','ce2566805c9e893a','3b9bcf29e38da0a6'}
        function marker_world(hashes, wanted)
            for _,h in ipairs(hashes) do if h==wanted then return true end end
            return false
        end
        HAVE={ui={}, ship=MARKERS, ship2={MARKERS[3]}, ship3=MARKERS}
        engine={
            Application={main_world=function() return MAIN end,
                worlds=function() return {'ui','ship','ship2','ship3'} end},
            World={units_by_resource=function(w,id)
                SCANS=SCANS+1
                if marker_world(HAVE[w] or {}, id) then return {id..'1'} end
                return {}
            end},
            Unit={alive=function() return true end},
            IdString64={from_hex=function(h) return h end},
            Network={game_session=function() return 'session' end},
            GameSession={in_session=function() return SESSION_FLAG end},
        }
        bridge={base=0x100000, game_sha256=module.game_sha256,exe_sha256=module.exe_sha256,
            verify=function() return true end,
            read=function(at,n)
                if n==8 then return p32(0x200000)..p32(0) end
                return native_state
            end,
        }
        -- Native screen stack: five ids at state+8..+0x1b, depth at state+0x1c.
        -- 1-based u32 slots: 1=current, 2=pending, 3..7=stack[1..5], 8=depth.
        function set_screen(depth,...)
            local ids={...}
            local slots={}
            for i=1,36 do slots[i]=0 end
            slots[8]=depth
            for i=1,math.min(5,#ids) do slots[2+i]=ids[i] end
            native_state=''
            for i=1,36 do native_state=native_state..p32(slots[i]) end
        end
        '''.replace('__IN_SESSION__', in_session))
        self.world_scope = world_scope

    def sample(self, ui_allow=None):
        self.lua.globals().SCOPE = self.world_scope
        if ui_allow is None:
            self.lua.execute('gate=module.new(engine,bridge,{session_required=true,world_scope=SCOPE})')
        else:
            self.lua.globals().ALLOW = self.lua.table(*ui_allow)
            self.lua.execute('gate=module.new(engine,bridge,{session_required=true,'
                             'world_scope=SCOPE,ui_allow=ALLOW})')
        result = self.lua.eval(
            '(function() local ok,why,world,info=gate.sample() '
            'return {ok=ok,why=why,world=world,info=info,'
            'markerless=info and info.markers_all_absent or false,'
            'fallback=info and info.fallback or false,'
            'in_session=info and info.in_session or false} end)()')
        return result

    def test_main_scope_fails_on_this_builds_layout(self):
        # documents the live failure: the main world is not the ship world
        self.build(world_scope='main')
        result = self.sample()
        self.assertFalse(result['ok'])
        self.assertEqual(result['why'], 'ship_marker_absent')

    def test_any_scope_finds_the_world_that_carries_the_markers(self):
        self.build(world_scope='any')
        result = self.sample()
        self.assertTrue(result['ok'], result['why'])
        self.assertEqual(result['why'], 'ship_idle')
        self.assertEqual(result['world'], 'ship')
        info = result['info']
        self.assertEqual(info['main_matches'], False)
        self.assertEqual(info['markers'][1], 1)
        self.assertGreaterEqual(info['worlds_scanned'], 2)

    def test_any_scope_remembers_the_ship_world_and_rescans_it_first(self):
        self.build(world_scope='any')
        self.sample()
        self.lua.globals().SCANS = 0
        self.lua.globals().SCOPE = 'any'
        result = self.lua.eval('(function() local ok,why,world=gate.sample() '
                               'return {ok=ok,why=why,world=world} end)()')
        self.assertTrue(result['ok'], result['why'])
        self.assertEqual(result['world'], 'ship')
        # Cached path: 3 probes for the scene, 3 for the closing confirmation
        # and 3 more in the second-identity check - 9 total, versus a full scan
        # which would be 12 plus the confirmation.
        self.assertLessEqual(self.lua.globals().SCANS, 9)
        self.assertGreater(self.lua.globals().SCANS, 0)

    def test_any_scope_prefers_the_world_that_already_proved_to_be_the_ship(self):
        self.build(world_scope='any')
        self.sample()                                     # latches on 'ship'
        self.lua.execute("HAVE.ship3=MARKERS")            # a decoy appears earlier in the list
        result = self.lua.eval('(function() local ok,why,world=gate.sample() '
                               'return {ok=ok,why=why,world=world} end)()')
        self.assertEqual(result['world'], 'ship', 'the cached ship world must win')

    def test_any_scope_still_refuses_a_scene_with_no_qualifying_world(self):
        self.build(world_scope='any')
        self.lua.execute('HAVE={ui={}, ship={}, ship2={}, ship3={}}')
        result = self.sample()
        self.assertFalse(result['ok'])
        self.assertEqual(result['why'], 'ship_marker_absent')

    def test_any_scope_does_not_accept_a_partial_marker_set(self):
        self.build(world_scope='any')
        self.lua.execute("HAVE={ui={}, ship={MARKERS[1],MARKERS[2]}, ship2={MARKERS[3]}, ship3={}}")
        result = self.sample()
        self.assertFalse(result['ok'])
        self.assertEqual(result['why'], 'ship_marker_absent')

    def test_any_scope_still_requires_a_session_object(self):
        self.build(world_scope='any')
        self.lua.execute('engine.Network={game_session=function() return nil end}')
        result = self.sample()
        self.assertFalse(result['ok'])
        self.assertEqual(result['why'], 'not_in_session')

    def test_any_scope_still_respects_native_ui_state(self):
        self.build(world_scope='any')
        self.lua.execute('native_state=native_state:sub(1,0)..p32(15)..native_state:sub(5)')
        result = self.sample()
        self.assertFalse(result['ok'])
        self.assertEqual(result['why'], 'native_ui_busy')

    # --- world_scope='count': the signal the WORKING 2.5.5 build used ---
    # "the ship runs 9+ worlds; the title screen only a couple"

    def build_count(self, world_count, in_session='true'):
        self.build(world_scope='count', in_session=in_session)
        names = ['ui', 'ship'] + ['w%d' % i for i in range(2, world_count)]
        self.lua.globals().NAMES = self.lua.table(*names[:world_count])
        self.lua.execute('engine.Application.worlds=function() return NAMES end')

    def test_count_scope_authorizes_the_ship_world_list(self):
        self.build_count(9)
        result = self.sample()
        self.assertTrue(result['ok'], result['why'])
        self.assertEqual(result['why'], 'ship_idle')
        self.assertEqual(result['info']['worlds'], 9)

    def test_count_scope_blocks_the_title_screen_world_list(self):
        self.build_count(3)
        result = self.sample()
        self.assertFalse(result['ok'])
        self.assertEqual(result['why'], 'few_worlds(3)')

    def test_count_scope_boundary_is_eight_worlds(self):
        self.build_count(7)
        self.assertFalse(self.sample()['ok'])
        self.build_count(8)
        self.assertTrue(self.sample()['ok'])

    def test_count_scope_does_not_need_the_ship_markers(self):
        # this build has no resolvable ship markers; the count signal must not
        # depend on them
        self.build_count(9)
        self.lua.execute('HAVE={ui={}, ship={}, ship2={}, ship3={}}')
        result = self.sample()
        self.assertTrue(result['ok'], result['why'])

    def test_count_scope_still_hides_while_the_native_ui_is_busy(self):
        self.build_count(9)
        self.lua.execute('native_state=p32(15)..native_state:sub(5)')
        result = self.sample()
        self.assertFalse(result['ok'])
        self.assertEqual(result['why'], 'native_ui_busy')

    # --- the one allowed native screen: the armory (id 5) ---
    # 'native UI is busy' is raised by the armory, the hellpod loadout and the
    # galactic war map alike, so only the screen id can single the armory out.
    # Screen 5 = armory, 14 = hellpod loadout (both named by two independent
    # published mods reading this same block on this same game build).

    def test_count_scope_keeps_the_panel_in_the_armory_screen(self):
        self.build_count(9)
        self.lua.execute('set_screen(2,7,5)')     # armory on top of another screen
        result = self.sample(ui_allow=[5])
        self.assertTrue(result['ok'], result['why'])
        self.assertEqual(result['why'], 'ship_screen_5')
        self.assertEqual(result['info']['ui_screen'], 5)
        self.assertEqual(result['info']['ui_screen_allowed'], True)

    def test_count_scope_still_hides_the_hellpod_loadout_screen(self):
        self.build_count(9)
        self.lua.execute('set_screen(2,7,14)')
        result = self.sample(ui_allow=[5])
        self.assertFalse(result['ok'])
        self.assertEqual(result['why'], 'native_ui_busy')
        self.assertEqual(result['info']['ui_screen'], 14)

    def test_count_scope_reads_only_the_top_of_the_screen_stack(self):
        # the armory stays under the loadout: the loadout is what is on screen
        self.build_count(9)
        self.lua.execute('set_screen(2,5,14)')
        result = self.sample(ui_allow=[5])
        self.assertFalse(result['ok'])
        self.assertEqual(result['why'], 'native_ui_busy')

    def test_count_scope_hides_the_armory_without_the_allow_list(self):
        # an empty allow list keeps the historical behaviour exactly
        self.build_count(9)
        self.lua.execute('set_screen(1,5)')
        result = self.sample()
        self.assertFalse(result['ok'])
        self.assertEqual(result['why'], 'native_ui_busy')
        self.assertEqual(result['info']['ui_screen'], 5)

    def test_count_scope_still_bounds_a_broken_stack(self):
        # depth outside 1..5 is a changed layout, not an authorization
        self.build_count(9)
        self.lua.execute('set_screen(9,5)')
        result = self.sample(ui_allow=[5])
        self.assertFalse(result['ok'])
        self.assertEqual(result['why'], 'ui_bounds_changed')

    def test_count_scope_still_requires_a_session_object(self):
        self.build_count(9)
        self.lua.execute('engine.Network={game_session=function() return nil end}')
        result = self.sample()
        self.assertFalse(result['ok'])
        self.assertEqual(result['why'], 'not_in_session')

    def test_count_scope_still_requires_a_verified_build(self):
        self.build_count(9)
        self.lua.execute('bridge.game_sha256="unsupported"')
        result = self.sample()
        self.assertFalse(result['ok'])
        self.assertEqual(result['why'], 'native_build_unverified')

    def test_unknown_scope_value_behaves_like_any(self):
        # only the literal 'main' keeps the old single-world behaviour; every
        # other value scans the bounded world list
        self.build(world_scope='nonsense')
        result = self.sample()
        self.assertTrue(result['ok'], result['why'])
        self.assertEqual(result['world'], 'ship')

    def test_reset_forgets_the_cached_ship_world(self):
        self.build(world_scope='any')
        self.sample()
        self.lua.execute('gate.reset() HAVE={ui={}, ship={}, ship2={}, ship3={}}')
        result = self.lua.eval('(function() local ok,why,world=gate.sample() '
                               'return {ok=ok,why=why,world=world} end)()')
        self.assertFalse(result['ok'])
        self.assertEqual(result['why'], 'ship_marker_absent')

    # --- world_scope='session': the marker resources do not resolve anywhere ---

    def test_session_scope_reports_markerless_as_a_recoverable_reason(self):
        self.build(world_scope='session')
        self.lua.execute('HAVE={ui={}, ship={}, ship2={}, ship3={}}')
        result = self.sample()
        self.assertFalse(result['ok'])
        self.assertEqual(result['why'], 'ship_markers_unresolvable')
        self.assertTrue(result['fallback'], 'the host must see it as recoverable')
        self.assertTrue(result['markerless'])
        self.assertEqual(result['in_session'], True)

    def test_session_scope_still_prefers_a_real_marker_world(self):
        self.build(world_scope='session')
        result = self.sample()                      # HAVE.ship carries all three
        self.assertTrue(result['ok'], result['why'])
        self.assertEqual(result['world'], 'ship')
        self.assertFalse(result['markerless'])

    def test_session_scope_still_requires_a_session_object(self):
        self.build(world_scope='session')
        self.lua.execute('engine.Network={game_session=function() return nil end}')
        result = self.sample()
        self.assertFalse(result['ok'])
        self.assertEqual(result['why'], 'not_in_session')
        self.assertFalse(result['markerless'])

    def test_session_scope_still_hides_while_the_native_ui_is_busy(self):
        self.build(world_scope='session')
        self.lua.execute('HAVE={ui={}, ship={}, ship2={}, ship3={}};'
                         'native_state=p32(15)..native_state:sub(5)')
        result = self.sample()
        self.assertFalse(result['ok'])
        self.assertIn(result['why'], ('ship_markers_unresolvable', 'native_ui_busy'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
