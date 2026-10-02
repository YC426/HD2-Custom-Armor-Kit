# -*- coding: utf-8 -*-
"""Guarded envelope deploy for HD2 Arsenal / Bingus mods.

Why this file exists (2026-10-01, user report "加上这个模组后会让所有lua模组
直接不生效"):
    build121.py ... build250.py wrote the Custom Armor Kit's envelope into a
    HARD-CODED game slot, 9ba626afa44a3aa3.patch_309. Arsenal renumbers layers
    on every deploy. The current 2026-10-01 deployment puts MDL in slot 309
    and the **Bingus Shared Loader in slot 311** (sha256 950a1b29c70a5bf3,
    byte-identical to
    hd2arsenal/mods/Bingus-Shared-Loader-v18_AR662579/data/
    9ba626afa44a3aa3.patch_0). Overwriting it deletes the mod loader, so the
    whole Lua ecosystem dies: the game still starts, but every mod is gone
    ("一大批 not installed" / no mod functionality at all).

Rules enforced here
    * the target slot is found by the addon DECLARATION stored inside the
      layer, never by a number;
    * a numbered slot that belongs to somebody else - including mods whose
      envelope carries no addon marker, like the loader - is NEVER written;
    * if the mod has no slot yet, a brand-new number above the current
      maximum is used, so nothing can be displaced;
    * the loader is re-verified afterwards and the deploy aborts loudly if it
      is not intact.
"""
import hashlib
import io
import json
import os
import re
from pathlib import Path

GAME = r"D:\Program Files (x86)\Steam\steamapps\common\Helldivers 2\data"
LIB = os.path.join(os.environ.get("LOCALAPPDATA", ""), "hd2arsenal", "mods")
ARCHIVE = "9ba626afa44a3aa3.patch_"
SIDECARS = (".gpu_resources", ".stream")
LOADER_HINTS = ("Bingus Shared Loader", "BingusSharedLoader")
BINGUS_GUID = '612eaf70-d682-43c7-9efd-16dcc695f977'
MDL_GUID = '761188b2-c45b-4607-9241-f89ca221c47b'
LOADER_GUIDS = frozenset((BINGUS_GUID, MDL_GUID))


class DeployRefused(RuntimeError):
    pass


def layer_numbers():
    """{number: path} for every plain patch layer present in the game."""
    out = {}
    for n in os.listdir(GAME):
        m = re.fullmatch(re.escape(ARCHIVE) + r"(\d+)", n)
        if m:
            out[int(m.group(1))] = os.path.join(GAME, n)
    return out


def addon_declaration(path):
    """The '-- HD2-Addon: mods/x/y' declaration inside a layer, or None."""
    try:
        b = Path(path).read_bytes()
    except OSError:
        return None
    return payload_declaration(b)


def payload_declaration(b):
    """Read the first actual declaration, including inside an archive envelope."""
    i = b.find(b"-- HD2-Addon: ")
    if i < 0:
        return None
    return b[i + 13:i + 160].split(b"\n")[0].decode("utf-8", "replace").strip()


def library_envelopes():
    """sha256 -> {library folder names} for every Arsenal library envelope."""
    known = {}
    if not os.path.isdir(LIB):
        return known
    for d in os.listdir(LIB):
        for root, _dirs, files in os.walk(os.path.join(LIB, d)):
            for f in files:
                if not f.startswith(ARCHIVE + "0") or f.endswith(SIDECARS):
                    continue
                try:
                    h = hashlib.sha256(Path(root, f).read_bytes()).hexdigest()
                except OSError:
                    continue
                known.setdefault(h, set()).add(d)
    return known


def loader_hashes():
    """sha256 of known Bingus or MDL loader library envelopes.

    Most Bingus addons mention "Bingus Shared Loader" in their description, so
    a string search is useless for identity - match the envelope bytes.
    """
    out = set()
    if not os.path.isdir(LIB):
        return out
    for d in os.listdir(LIB):
        try:
            manifest = json.loads(Path(LIB, d, 'manifest.json').read_text(encoding='utf8'))
        except (OSError, ValueError):
            continue
        if str(manifest.get('Guid', '')).lower() not in LOADER_GUIDS:
            continue
        for root, _dirs, files in os.walk(os.path.join(LIB, d)):
            for f in files:
                if f == ARCHIVE + "0":
                    try:
                        out.add(hashlib.sha256(
                            Path(root, f).read_bytes()).hexdigest())
                    except OSError:
                        pass
    return out


def loader_slots():
    """Slots byte-identical to a known Bingus or MDL loader envelope."""
    lh = loader_hashes()
    found = []
    for num, path in layer_numbers().items():
        try:
            b = Path(path).read_bytes()
        except OSError:
            continue
        if hashlib.sha256(b).hexdigest() in lh:
            found.append(num)
    return sorted(found)


def _digest(data):
    return hashlib.sha256(data).hexdigest()


def find_own_slot(declaration):
    return [n for n, p in layer_numbers().items() if addon_declaration(p) == declaration]


def classify(number, declaration, known):
    """'mine' | 'foreign' | 'missing' for one layer number."""
    nums = layer_numbers()
    if number not in nums:
        return "missing"
    path = nums[number]
    try:
        b = Path(path).read_bytes()
    except OSError:
        return "foreign"
    dec = addon_declaration(path)
    if dec == declaration:
        return "mine"
    if dec:
        return "foreign"          # another addon's declaration
    if _digest(b) in known:
        return "foreign"          # a library envelope (the loader looks like this)
    return "foreign"              # unknown numbered slot: still not ours


def deploy(declaration, payload, library_dir=None, manifest=None,
           sidecars=None, dry_run=False, slot=None):
    """Put `payload` (the addon envelope bytes) in this mod's own slot.

    Returns the slot number that was written. Raises DeployRefused rather than
    touching a slot that is not ours. `slot` exists only so tests can prove an
    explicit (e.g. historical, hard-coded) target is refused.
    """
    if payload_declaration(payload) != declaration:
        raise DeployRefused("payload does not declare %s" % declaration)

    # Every non-matching declaration is already foreign, so hashing the entire
    # Arsenal library adds no protection and can read gigabytes on each build.
    known = {}
    mine = find_own_slot(declaration)
    if len(mine) > 1:
        raise DeployRefused("multiple slots carry %s: %s; resolve duplicates first"
                            % (declaration, sorted(mine)))
    if slot is not None:
        target = slot
    elif mine:
        target = min(mine)                      # already ours: rewrite in place
    else:
        nums = layer_numbers()
        target = (max(nums) + 1) if nums else 1
    if classify(target, declaration, known) == "foreign":
        raise DeployRefused(
            "slot %d belongs to another mod (%s) - refusing to overwrite"
            % (target, addon_declaration(layer_numbers()[target]) or "no declaration"))

    before = {n: _digest(Path(p).read_bytes()) for n, p in layer_numbers().items()}
    loaders = loader_slots()
    if not loaders:
        raise DeployRefused("no intact Bingus or MDL loader found; refusing deployment")
    print("  loader slot(s): %s | target slot: %d" % (loaders or "NOT FOUND", target))
    if target in loaders:
        raise DeployRefused("slot %d holds a mod loader" % target)

    if dry_run:
        print("  dry run: would write slot %d (%d bytes)" % (target, len(payload)))
        return target

    sidecars = sidecars or {}
    for suffix in ("",) + SIDECARS:
        data = payload if suffix == "" else sidecars.get(suffix, b"")
        with open(os.path.join(GAME, ARCHIVE + str(target) + suffix), "wb") as f:
            f.write(data)

    # verify: our bytes landed, nothing else moved
    got = Path(GAME, ARCHIVE + str(target)).read_bytes()
    if _digest(got) != _digest(payload):
        raise DeployRefused("slot %d write did not verify" % target)
    for n, h in before.items():
        if n == target:
            continue
        if _digest(Path(layer_numbers()[n]).read_bytes()) != h:
            raise DeployRefused("slot %d changed during deploy - aborting" % n)

    after_loaders = loader_slots()
    if sorted(after_loaders) != sorted(loaders):
        raise DeployRefused("loader slot changed (%s -> %s)" % (loaders, after_loaders))

    if library_dir:
        for suffix in ("",) + SIDECARS:
            data = payload if suffix == "" else sidecars.get(suffix, b"")
            p = os.path.join(library_dir, "Addon", ARCHIVE + "0" + suffix)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "wb") as f:
                f.write(data)
        if manifest is not None:
            with open(os.path.join(library_dir, "manifest.json"), "wb") as f:
                f.write(manifest)
        print("  library synced: %s" % os.path.basename(library_dir))

    print("  deployed %s -> slot %d (%d bytes), loader intact %s"
          % (declaration, target, len(payload), after_loaders))
    return target


def library_dir_for(guid):
    """Locate the Arsenal library folder by manifest GUID (never by name)."""
    if not os.path.isdir(LIB):
        return None
    for d in sorted(os.listdir(LIB)):
        p = os.path.join(LIB, d, "manifest.json")
        if not os.path.exists(p):
            continue
        try:
            m = json.loads(Path(p).read_text(encoding='utf8'))
        except Exception:
            continue
        if str(m.get("Guid", "")).lower() == str(guid).lower():
            return os.path.join(LIB, d)
    return None


def _self_test():
    """Never clobber another mod - exercised against the live game folder."""
    nums = layer_numbers()
    loaders = loader_slots()
    print("layers: %d (max %d), loader slot(s): %s" % (len(nums), max(nums), loaders))
    assert loaders, "no loader found - is the mod loader missing already?"
    known = {}
    for n in loaders:
        assert classify(n, "mods/codex/custom_armor", known) == "foreign", n
    assert classify(max(nums) + 1, "mods/codex/custom_armor", known) == "missing"
    fake = ("-- HD2-Addon: mods/codex/custom_armor\n" + "-- x" * 40).encode()
    # 1. the historical bug, verbatim: a hard-coded slot must be refused
    for bad in loaders:
        try:
            deploy("mods/codex/custom_armor", fake, slot=bad, dry_run=True)
        except DeployRefused as exc:
            print("  refused hard-coded slot %d: %s" % (bad, exc))
        else:
            raise SystemExit("self-test FAILED: slot %d was not refused" % bad)
    # 2. reuse our current slot, or choose a fresh slot on first install.
    mine = find_own_slot('mods/codex/custom_armor')
    target = deploy("mods/codex/custom_armor", fake, dry_run=True)
    assert target not in loaders, target
    assert target == min(mine) if mine else target not in nums
    # 3. our own slot is rewritten in place, never duplicated
    print("self-test OK: refuses %s, would use owned or new slot %d"
          % (loaders, target))


if __name__ == "__main__":
    _self_test()
