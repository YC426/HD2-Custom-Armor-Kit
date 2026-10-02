"""Validate the local artifact without inspecting any installed game."""
from pathlib import Path
import re
import zipfile
root = Path(__file__).resolve().parents[2]
src = Path(__file__).with_name('multi_perk.lua').read_text(encoding='utf-8')
ver = re.search(r"version='([^']+)'", src).group(1)
package = root / 'outputs/validated-2026-10-01' / ('Custom-Armor-Kit-' + ver + '.zip')
with zipfile.ZipFile(package) as z:
    assert z.testzip() is None
    names = z.namelist()
    assert 'manifest.json' in names and 'thumbnail.png' in names
    payload = z.read(next(n for n in names if n.startswith('Addon/') and n.endswith('patch_0')))
    assert b'mods/codex/custom_armor' in payload
    assert ("version='" + ver + "'").encode() in payload
print('Local artifact identity and ZIP integrity: OK; no in-game claim.')
