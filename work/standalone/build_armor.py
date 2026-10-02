"""Portable Custom Armor Kit build; deployment is explicitly opt-in.

Reuse the established assembler/validation/packaging, with project-relative
inputs. A normal invocation writes only the versioned project artifact.
"""
from pathlib import Path
import argparse
import re
import subprocess
import sys
import zipfile

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--deploy', action='store_true', help='deploy the verified archive through safe_deploy')
parser.add_argument('--validate-only', action='store_true', help='compile and run existing validation without packaging')
parser.add_argument('--with-source', action='store_true',
                    help='also assemble the source bundle (only for a human review handoff; not built by default)')
parser.add_argument('--skip-tests', action='store_true',
                    help='pack without running the validation chain (used by the isolated rebuild check)')
args = parser.parse_args()
ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS = ROOT / 'outputs' / 'validated-2026-10-01'
ARTIFACTS.mkdir(parents=True, exist_ok=True)
template = Path(__file__).with_name('build255.py').read_text(encoding='utf-8')
body = Path(__file__).with_name('multi_perk.lua').read_text(encoding='utf-8')
VERSION = re.search(r"version='([^']+)'", body).group(1)
assert VERSION == '2.5.10', f'expected candidate 2.5.10, got {VERSION}'
# Pre-build gate: these read the SOURCE only. The artifact tests run after
# packaging below, because they compare the freshly written archive against the
# source and against the deployed layer.
for check in (() if args.skip_tests else (
        'test_safe_deploy.py', 'test_armor_regressions.py', 'test_armor_auto_init.py', 'test_armor_controls.py', 'test_armor_ui.py', 'test_armor_escape.py', 'test_armor_armory.py', 'test_ship_visibility.py',
        'test_ship_visibility_session.py', 'test_ship_visibility_worlds.py',
        'test_armor_visibility_diagnostics.py', 'test_armor_gate_latch.py')):
    subprocess.run([sys.executable, str(Path(__file__).with_name(check))], check=True)
start = template.index('W = ')
end = template.index('# ---- 1. assemble')
settings = (
    f'W = {str(ROOT / "work")!r}\n'
    f'OUT = {str(ARTIFACTS)!r}\n'
    'FORK = os.path.join(W, "fork", "foundation.lua")\n'
    'BODY = os.path.join(W, "standalone", "multi_perk.lua")\n'
    'ZHDATA = os.path.join(W, "standalone", "zh_data.lua")\n'
    f'ZIP = os.path.join(OUT, "Custom-Armor-Kit-{VERSION}.zip")\n'
)
text = template[:start] + settings + template[end:]
text = text.replace('lupa.LuaRuntime().compile(source)',
                    'from prepare_public_source import prepare\n'
                    'source = prepare(source)\n'
                    'lupa.LuaRuntime().compile(source)')
text = text.replace('comp_src = slice_src(', 'comp_src = "local RT={}\\n" + slice_src(')
text = text.replace('comp2_src = slice_src(', 'comp2_src = "local RT={}\\n" + slice_src(')
text = text.replace('import build_addon as official',
                    'sys.path.insert(0, str(Path(__file__).with_name("vendor") / "bingus"))\nimport build_addon as official')
text = text.replace('Multiple cards can be active at once. ',
                    'Independent cards require unused passive carriers; unavailable combinations are refused. ')
ship = Path(__file__).with_name('ship_visibility.lua').read_text(encoding='utf-8')
insert = 'local ShipVisibility=(function()\n' + ship + '\nend)()\n'
text = text.replace('assert "@@ZHDATA@@" not in source',
                    'source = source.replace("--@@SHIPVIS@@\\n", ' + repr(insert) + ')\n'
                    'assert "@@SHIPVIS@@" not in source\nassert "@@ZHDATA@@" not in source')
text = text.replace("assert \"version='2.5.5'\" in source", f'assert "version=\'{VERSION}\'" in source')
text = text.replace(r'C:\HD2-Workspace\outputs\7c30c505-701d-45d1-9c41-54244712db9a.png',
                    str(ROOT / 'outputs' / '7c30c505-701d-45d1-9c41-54244712db9a.png'))
if args.validate_only:
    text = text[:text.index('# ---- 12. pack + deploy')]
elif not args.deploy:
    text = text[:text.index('# ---- 12b. deploy through the guard')]
else:
    text = text.replace('libdir = safe_deploy.library_dir_for(GUID)',
                        "MGR_CAND = os.path.join(os.environ['LOCALAPPDATA'], 'hd2arsenal', 'mods')\nlibdir = safe_deploy.library_dir_for(GUID)")
exec(compile(text, str(Path(__file__)), 'exec'), globals())
if not args.validate_only:
    # The source bundle existed only for a human-review handoff (the upload path
    # rejected the companion .bat). That route is abandoned, so it is now opt-in:
    # the default build leaves the workspace as the single source of truth and
    # writes only the release archive.
    if not args.with_source:
        print('source bundle skipped (pass --with-source only for a review handoff)')
    else:
        source_zip = ARTIFACTS / f'Custom-Armor-Kit-source-{VERSION}.zip'
        files = [
            'work/standalone/multi_perk.lua', 'work/standalone/zh_data.lua',
            'work/standalone/ship_visibility.lua', 'work/standalone/build_armor.py',
            'work/standalone/build255.py', 'work/standalone/ffi_audit.py',
            'work/standalone/prepare_public_source.py',
            'work/standalone/safe_deploy.py', 'work/standalone/simtest.py',
            'work/standalone/test_armor_regressions.py', 'work/standalone/test_armor_ui.py',
            'work/standalone/test_ship_visibility.py', 'work/fork/foundation.lua',
            'work/standalone/test_armor_visibility_diagnostics.py',
            'work/standalone/test_ship_visibility_session.py',
            'work/standalone/test_ship_visibility_worlds.py',
            'work/standalone/test_armor_gate_latch.py',
            'work/standalone/test_armor_controls.py', 'work/standalone/test_armor_escape.py',
            'work/standalone/test_armor_armory.py',
            'work/standalone/vendor/bingus/build_addon.py', 'work/standalone/vendor/bingus/archive.py',
            'outputs/7c30c505-701d-45d1-9c41-54244712db9a.png',
        ]
        with zipfile.ZipFile(source_zip, 'w', zipfile.ZIP_DEFLATED) as package:
            for name in files:
                package.write(ROOT / name, name)
            package.writestr('README.txt',
                f'Custom Armor Kit {VERSION} source\nRequires Python 3 + lupa (including LuaJIT 2.1).\n'
                'Build only: python work/standalone/build_armor.py\n'
                'Validate only: python work/standalone/build_armor.py --validate-only\n'
                'No game/library/config files are changed by either command.\n'
                'Live deployment is a separate explicit --deploy option using safe_deploy.\n'
                'This release remains pending real game validation. Simulation is not an in-game proof.\n')
        print(f'source archive ready: {source_zip}')
    # Post-build verification: the freshly written archive must be reproducible
    # from the workspace and must match the layer that is actually deployed.
    for check in (() if args.skip_tests else ('test_build_armor.py',)):
        subprocess.run([sys.executable, str(Path(__file__).with_name(check))], check=True)
print('validation complete' if args.validate_only else f'archive ready: {ARTIFACTS / ("Custom-Armor-Kit-" + VERSION + ".zip")}')
