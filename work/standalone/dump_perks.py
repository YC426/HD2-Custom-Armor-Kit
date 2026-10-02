# -*- coding: utf-8 -*-
"""Dump every passive/perk the armor mod knows about, straight from the game
catalog embedded in foundation.lua, together with the modifier rows that
compose() actually merges.

This is the data behind the in-game card list, so it is the authority for
"which perks exist" and "which modifier rows each one carries".
"""
import io
import os
import sys
from pathlib import Path

import lupa

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

W = Path(r'C:\Users\23825\Desktop\2-apex-x20\mods\custom-armor-kit\work')
FORK = W / 'fork' / 'foundation.lua'

ft = io.open(FORK, encoding='utf-8', errors='replace').read()
s0 = ft.index('local CatalogData = (function()')
e0 = ft.index('\nend)()', s0) + len('\nend)()')
lua = lupa.LuaRuntime(unpack_returned_tuples=True)
catalog = lua.execute(ft[s0:e0] + '\nreturn CatalogData')

passives = catalog['passives']
enums = sorted(int(e) for e in passives.keys())
print('passive/perk count: %d' % len(enums))

rows = []
for enum in enums:
    p = passives[enum]
    mods = [str(h) for h in p['raw_modifiers'].values()]
    stats = [str(h) for h in p['raw_stat_modifiers'].values()]
    rows.append((enum, int(p['name_loc']), mods, stats))

print()
print('=== per-perk modifier rows ===')
multi = 0
for enum, name_loc, mods, stats in rows:
    if len(mods) > 1:
        multi += 1
    print('  enum=%-5d name_loc=%-12d rows=%d stats=%d' % (enum, name_loc, len(mods), len(stats)))
    for i, h in enumerate(mods, 1):
        # a modifier row is 32 hex chars: first 8 = modifier id, 25..32 = location
        print('       row%d id=%s loc=%s' % (i, h[:8], h[24:32]))
    for i, h in enumerate(stats, 1):
        print('       stat%d id=%s loc=%s' % (i, h[:8], h[24:32]))

print()
print('perks carrying more than one modifier row: %d / %d' % (multi, len(rows)))

# duplicate modifier ids -> these are the ones compose() de-duplicates
from collections import Counter
allids = Counter(h[:8] for _, _, mods, _ in rows for h in mods)
dupes = {k: v for k, v in allids.items() if v > 1}
print('modifier ids appearing in more than one perk: %d' % len(dupes))
for k, v in sorted(dupes.items(), key=lambda kv: -kv[1])[:15]:
    owners = [enum for enum, _, mods, _ in rows if any(h[:8] == k for h in mods)]
    print('   id=%s  x%d  perks=%s' % (k, v, owners))
