# Retirement findings / 退役时留下的实测结论

This repository is **archived and read-only**. It is kept because the in-game experiments
produced quantitative results about the armor kit record that are worth preserving.
本仓库已归档（只读）。保留原因是开发期间的实机实验产出了关于护甲 kit 记录的定量结论。

The mod itself is superseded: use
**[Super Earth Armory Forge](https://github.com/Hung1510/Super-Earth-Armory-Forge)**.
Do **not** install both — they patch the same records.

---

## 1. Writing 11 merged effect rows makes the game fastfail on READ

All cards below target the same armor (A-9 Helljumper, a 28-piece kit record) and were applied
with `merge=sum` semantics (shared effects added; others deduped by id + kind + description).

| test | perks | rows written | stats/weight swap | result |
|---|---|---|---|---|
| L1 | 1 | 2 | no | safe |
| L2 | 4 | 6 | no | safe |
| L3 | 1 | 2 | yes — 0 unmatched pieces | safe |
| L4 | 1 | 2 | yes — 1 unmatched piece | safe |
| L5 | 1 | 2 | yes — 3 unmatched pieces | safe |
| **T1** | **5** | **11** | **no** | **CRASH** |
| **T3** | **4** | **11** | no | **CRASH** |
| **T2B** | **5** | **11** | no | **CRASH** |
| **L6** | **5** | **11** | yes | **CRASH** |

### Crash signature (identical in all 5 reproductions)

```
faulting module : game.dll 1.0.0.19155  (module timestamp 0x6ab3b43f)
exception code  : 0xc0000409            (fastfail; exception data = 5, FAST_FAIL_INVALID_ARG)
fault offset    : 0x20d63a4
WER             : fault bucket type 5, Event Name BEX64
```

The exception code is a **fastfail**, i.e. the game deliberately aborts on an argument it
considers invalid; it is not an access violation (`0xc0000005`).

### The trigger is a read, not the write

- Applying a card and **never reading the record** — no crash.
- **Hovering the modified armor in the Armory** — crashes within seconds (most reliable trigger).
- Opening the Armory and viewing the armor — same thing.

This is consistent with a comment in this mod's own source:
*"enum 0 is the empty passive; merging it corrupts the record the game reads on hover"* —
the hover/armory read path is known to be sensitive to the record's contents.

### Ruled out by experiment (not by reasoning)

| hypothesis | how it was falsified |
|---|---|
| stats/weight swapping causes it | **T1 has no swap at all** and still crashes |
| one specific modifier row causes it | **T2B and T3 write 11 rows sharing zero modifier ids with T1** and still crash |
| the perk count (5) causes it | **T3 uses 4 perks** (like the safe L2) and still crashes |
| the `(假)` row (`Set` type, description id 0, 击倒抗性) causes it | **T2B/T3 do not contain it** and still crash |
| an enum-0 (empty passive) merge causes it | the mod sanitizes enum 0 out of every config; none of the cards above contained it |

**Every configuration that wrote 11 rows crashed; every configuration that wrote ≤ 6 rows was
safe. Rows 7–10 were not tested**, so the boundary lies in 7–10 and **11 is confirmed unsafe**.
**The mechanism behind it is still unknown** — only the boundary and the signature were
established.

### Minimal repro

1. Wear armor X. Apply a stack whose merged effect rows on that armor's kit record number 11.
2. Open the Armory and hover armor X.
3. Within seconds: `game.dll` fastfail at offset `0x20d63a4`, as above.

---

## 2. Slot model: decorative vs real effect slots

Transcribed from a third-party research note (screenshots + raw notes) that was provided during
development. It explains *why* editing dynamic passives is dangerous.

- A passive's rows split into **装饰词条 (decorative)** and **实际词条 (real)**. The decorative
  ones are what the game displays first and they have **no actual effect** — changing their
  values is meaningless. The **real rows sit after all the decorative ones**, in the same order.
  - 蓄势出击 (Siege-Ready): decorative 1 ↔ real 3, decorative 2 ↔ real 4.
  - 强化肩章 (Reinforced Epaulettes): of three rows only the first (装填速度) is dynamic, and its
    **real position is slot 4**.
- **Changing the TYPE of a row in slots 3 or 4 is what crashes.** Overwriting a purely
  **decorative** row is safe, which is why "cover slot 1 with something else" is the recommended
  way to reuse a reload-perk armor.
- Overwriting the **装填速度 (reload speed)** row (e.g. slot 3 → a death-chance row) makes the
  game **crash when loading into a map** — a different trigger from the hover crash above.
- **Description id `0` is legitimate** — the game displays that row as blank and skips its text.
  It is not a defect by itself. The `(假)` annotation on `击倒抗性（假）设置1` is a separate
  marker.
- Value editing: **装填速度 accepts edits** (1.3 = +30%, 2 = +100%); **弹药容量 (magazine
  capacity) resists edits** (1.2 up or down makes no difference — likely hard-coded).
- Raising the row count above the passive's own count yields a half-broken armor
  (some effects apply, some silently stop).

---

## 3. Known defects, left unfixed

1. **The stats/weight swap produces hybrid values.** Pieces are matched by `(body, slot, type)`;
   a look piece the donor lacks **keeps the look's weight**, and a donor piece the look lacks
   **is never written at all**. The result is a mixture: e.g. `AD-49 ← A-9` ends up with total
   weight **25** while pure A-9 is **28**, so the armor's rating/speed/stamina come out as
   neither armor's. Fix directions (renormalise the profile to the donor's total, or fail
   closed when the piece sets differ) were designed but never implemented.
2. **`rowbudget = 11` is a defensive guard, not a measured limit** — and it does **not** prevent
   the crash in §1: T1 writes exactly 11 rows, one under the cap, and crashes anyway.
3. **The crash mechanism in §1 was never identified.** Only the boundary and the signature.
