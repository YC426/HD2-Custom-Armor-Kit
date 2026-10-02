"""Coverage for the 2.5.7 session semantics: optional in_session, fallback
mode, latch-blocking reasons, and the diagnostics the panel depends on."""
from pathlib import Path
import unittest
from lupa import LuaRuntime


class ShipVisibilitySessionTest(unittest.TestCase):
    def build(self, session_required=True, in_session='true'):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        source = Path(__file__).with_name('ship_visibility.lua').read_text(encoding='utf-8')
        self.lua.globals().module = self.lua.execute(source)
        body = r'''
        function p32(n)
            return string.char(n%256,math.floor(n/256)%256,math.floor(n/65536)%256,math.floor(n/16777216)%256)
        end
        function patch_state(offset,value)
            native_state=native_state:sub(1,offset)..p32(value)..native_state:sub(offset+5)
        end
        active=true; main='ship'; marker_alive=true; scene_markers=true
        SESSION_FLAG=__IN_SESSION__
        native_state=string.rep('\0',0x90)
        engine={
            Application={main_world=function() return main end,
                worlds=function() return {'ship','ui','mission'} end},
            World={units_by_resource=function(w,id)
                if scene_markers and w=='ship' then return {id..'1'} end
                return {}
            end},
            Unit={alive=function() return marker_alive end},
            IdString64={from_hex=function(hash) return hash end},
            Network={game_session=function() return active and 'session' or nil end},
            GameSession={in_session=function() return SESSION_FLAG end},
        }
        bridge={base=0x100000, game_sha256=module.game_sha256,exe_sha256=module.exe_sha256,
            verify=function() return true end,
            read=function(at,n)
                if n==8 then return p32(0x200000)..p32(0) end
                return native_state
            end,
        }
        '''.replace('__IN_SESSION__', in_session)
        self.lua.execute(body)
        self.session_required = session_required

    def gate(self):
        self.lua.globals().REQUIRED = self.session_required
        self.lua.execute('gate=module.new(engine,bridge,{session_required=REQUIRED})')
        result = self.lua.eval('(function() local ok,why,world,info=gate.sample() '
                               'return {ok=ok,why=why,world=world,info=info} end)()')
        return (result['ok'], result['why'], result['world'], result['info'])

    def test_in_session_true_is_a_plain_ship_sample(self):
        self.build(in_session='true')
        ok, reason, world, info = self.gate()
        self.assertTrue(ok, (ok, reason))
        self.assertEqual(reason, 'ship_idle')
        self.assertFalse(info['fallback'])

    def test_in_session_false_blocks_when_the_host_requires_it(self):
        self.build(in_session='false', session_required=True)
        ok, reason, world, info = self.gate()
        self.assertFalse(ok)
        self.assertEqual(reason, 'not_in_session')
        self.assertFalse(info['fallback'])
        self.assertEqual(info['in_session'], False)

    def test_in_session_false_is_marked_fallback_when_the_host_allows_it(self):
        self.build(in_session='false', session_required=False)
        ok, reason, world, info = self.gate()
        self.assertTrue(ok, (ok, reason))
        self.assertTrue(info['fallback'])
        self.assertEqual(info['markers'][1], 1)

    def test_in_session_raising_is_unavailable_not_blocking(self):
        self.build(in_session='error', session_required=True)
        ok, reason, world, info = self.gate()
        self.assertTrue(ok, (ok, reason))
        self.assertIsNone(info['in_session'])
        self.assertTrue(info['fallback'])

    def test_in_session_api_absent_is_unavailable_not_blocking(self):
        self.build(session_required=True)
        self.lua.execute('engine.GameSession={}')
        ok, reason, world, info = self.gate()
        self.assertTrue(ok, (ok, reason))
        self.assertIsNone(info['in_session'])

    def test_missing_session_object_still_blocks_in_both_modes(self):
        for required in (True, False):
            self.build(session_required=required)
            self.lua.execute('active=false')
            ok, reason, world, info = self.gate()
            self.assertFalse(ok)
            self.assertEqual(reason, 'not_in_session')

    def test_world_facts_are_still_authoritative_in_fallback_mode(self):
        self.build(in_session='false', session_required=False)
        self.lua.execute('main="mission"; scene_markers=false')
        ok, reason, world, info = self.gate()
        self.assertFalse(ok)
        self.assertEqual(reason, 'ship_marker_absent')
        self.assertEqual(info['world'], 'mission')

    def test_native_ui_busy_blocks_in_fallback_mode(self):
        self.build(in_session='false', session_required=False)
        self.lua.execute('patch_state(0,15)')
        ok, reason, world, info = self.gate()
        self.assertFalse(ok)
        self.assertEqual(reason, 'native_ui_busy')
        self.assertFalse(info['ui_idle'])
        self.assertEqual(info['ui']['current'], 15)

    def test_unverified_build_blocks_after_the_scene_facts(self):
        self.build(in_session='false', session_required=False)
        self.lua.execute('bridge.game_sha256="other"')
        ok, reason, world, info = self.gate()
        self.assertFalse(ok)
        self.assertEqual(reason, 'native_build_unverified')
        self.assertEqual(info['marker_counts'][1], 1)

    def test_info_reports_every_signal_for_live_diagnosis(self):
        self.build(in_session='false', session_required=False)
        ok, reason, world, info = self.gate()
        self.assertTrue('session' in info, list(info.keys()))
        self.assertTrue('ui' in info, list(info.keys()))
        self.assertTrue('ui_idle' in info, list(info.keys()))
        self.assertTrue('markers' in info, list(info.keys()))
        self.assertEqual(info['main'], 'ship')
        self.assertEqual(info['markers'][1], 1)
        self.assertFalse(info['fallback'] is None)

    def test_reset_forgets_cached_ui_pointer_and_marker_ids(self):
        self.build(in_session='true')
        self.gate()
        self.lua.execute('gate.reset()')
        ok, reason, world, info = self.gate()
        self.assertTrue(ok, (ok, reason))


if __name__ == '__main__':
    unittest.main(verbosity=2)
