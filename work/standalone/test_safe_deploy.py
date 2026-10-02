"""Exercise deployment against isolated real files; never touch the game."""
import tempfile
import unittest
import json
from pathlib import Path

import safe_deploy as deployer

ARCHIVE = '9ba626afa44a3aa3.patch_'
DECL = 'mods/codex/custom_armor'
PAYLOAD = b'-- HD2-Addon: mods/codex/custom_armor\nreturn {}\n'
LOADER = b'loader envelope fixture without an addon declaration'


class DeployTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.game = self.root / 'game'
        self.lib = self.root / 'mods'
        self.game.mkdir()
        loader = self.lib / 'Bingus-Shared-Loader-v18' / 'data'
        loader.mkdir(parents=True)
        (loader / (ARCHIVE + '0')).write_bytes(LOADER)
        (loader.parent / 'manifest.json').write_text(json.dumps({'Guid':
            '612eaf70-d682-43c7-9efd-16dcc695f977'}), encoding='utf8')
        (self.game / (ARCHIVE + '309')).write_bytes(LOADER)
        self.old_game, self.old_lib = deployer.GAME, deployer.LIB
        deployer.GAME, deployer.LIB = str(self.game), str(self.lib)

    def tearDown(self):
        deployer.GAME, deployer.LIB = self.old_game, self.old_lib
        self.temp.cleanup()

    def snapshot(self):
        return {p.name: p.read_bytes() for p in self.game.iterdir()}

    def test_foreign_slot_refused_without_writes(self):
        before = self.snapshot()
        with self.assertRaises(deployer.DeployRefused):
            deployer.deploy(DECL, PAYLOAD, slot=309)
        self.assertEqual(self.snapshot(), before)

    def test_new_slot_and_sidecars_preserve_loader(self):
        slot = deployer.deploy(DECL, PAYLOAD, sidecars={'.stream': b'stream'})
        self.assertEqual(slot, 310)
        self.assertEqual((self.game / (ARCHIVE + '309')).read_bytes(), LOADER)
        self.assertEqual((self.game / (ARCHIVE + '310')).read_bytes(), PAYLOAD)
        self.assertEqual((self.game / (ARCHIVE + '310.stream')).read_bytes(), b'stream')

    def test_owned_slot_reused(self):
        (self.game / (ARCHIVE + '305')).write_bytes(PAYLOAD)
        newer = PAYLOAD + b'-- changed\n'
        self.assertEqual(deployer.deploy(DECL, newer), 305)
        self.assertEqual((self.game / (ARCHIVE + '305')).read_bytes(), newer)
        self.assertFalse((self.game / (ARCHIVE + '310')).exists())

    def test_foreign_payload_cannot_spoof_declaration_with_comment(self):
        before = self.snapshot()
        foreign = b'-- HD2-Addon: mods/another/entry\n-- mentions mods/codex/custom_armor\n'
        with self.assertRaises(deployer.DeployRefused):
            deployer.deploy(DECL, foreign)
        self.assertEqual(self.snapshot(), before)

    def test_absent_loader_refused_without_writes(self):
        (self.game / (ARCHIVE + '309')).write_bytes(b'unknown foreign resource')
        before = self.snapshot()
        with self.assertRaises(deployer.DeployRefused):
            deployer.deploy(DECL, PAYLOAD)
        self.assertEqual(self.snapshot(), before)

    def test_unknown_loader_identity_refused(self):
        (self.game / (ARCHIVE + '309')).write_bytes(b'MDL archive')
        mdl = self.lib / 'MDL-Mod-Dynamic-Loader' / 'data'
        mdl.mkdir(parents=True)
        (mdl / (ARCHIVE + '0')).write_bytes(b'MDL archive')
        (mdl.parent / 'manifest.json').write_text(json.dumps({'Guid':
            '11111111-1111-1111-1111-111111111111'}), encoding='utf8')
        before = self.snapshot()
        with self.assertRaises(deployer.DeployRefused):
            deployer.deploy(DECL, PAYLOAD)
        self.assertEqual(self.snapshot(), before)

    def test_mdl_only_deployment_preserves_loader(self):
        mdl = self.lib / 'MDL-Mod-Dynamic-Loader-1.4.4' / 'data'
        mdl.mkdir(parents=True)
        (mdl / (ARCHIVE + '0')).write_bytes(b'MDL archive')
        (mdl.parent / 'manifest.json').write_text(json.dumps({'Guid':
            '761188b2-c45b-4607-9241-f89ca221c47b'}), encoding='utf8')
        (self.game / (ARCHIVE + '309')).write_bytes(b'MDL archive')
        self.assertEqual(deployer.loader_slots(), [309])
        self.assertEqual(deployer.deploy(DECL, PAYLOAD), 310)
        self.assertEqual((self.game / (ARCHIVE + '309')).read_bytes(), b'MDL archive')

    def test_both_loader_envelopes_protected(self):
        mdl = self.lib / 'MDL-Mod-Dynamic-Loader-1.4.4' / 'data'
        mdl.mkdir(parents=True)
        (mdl / (ARCHIVE + '0')).write_bytes(b'MDL archive')
        (mdl.parent / 'manifest.json').write_text(json.dumps({'Guid':
            '761188b2-c45b-4607-9241-f89ca221c47b'}), encoding='utf8')
        (self.game / (ARCHIVE + '308')).write_bytes(b'MDL archive')
        self.assertEqual(deployer.loader_slots(), [308, 309])
        self.assertEqual(deployer.deploy(DECL, PAYLOAD), 310)
        self.assertEqual((self.game / (ARCHIVE + '308')).read_bytes(), b'MDL archive')
        self.assertEqual((self.game / (ARCHIVE + '309')).read_bytes(), LOADER)

    def test_duplicate_own_slots_refused_without_partial_update(self):
        for n in [305, 310]:
            (self.game / (ARCHIVE + str(n))).write_bytes(PAYLOAD)
        before = self.snapshot()
        with self.assertRaises(deployer.DeployRefused):
            deployer.deploy(DECL, PAYLOAD + b'-- update\n')
        self.assertEqual(self.snapshot(), before)

    def test_dry_run_writes_nothing(self):
        before = self.snapshot()
        self.assertEqual(deployer.deploy(DECL, PAYLOAD, dry_run=True), 310)
        self.assertEqual(self.snapshot(), before)


if __name__ == '__main__':
    unittest.main(verbosity=2)
