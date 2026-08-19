# megamud-mdb2-decoders

Decoders for MegaMUD's proprietary `.md` game-data files.

Despite the `.md` extension, MegaMUD does **not** ship its game data as
Microsoft Jet `.mdb` databases. Each file uses a custom binary format
with the magic bytes `MDB2` and a slot-allocated page layout. This
repo contains scripts that decode those files into plain JSON without
needing Wine, the Microsoft Access Database Engine, or any other
Windows-only dependency.

## Scope — which MegaMUD `.md` files actually need decoding

MegaMUD's `Default/` folder ships **nine** `.md` files. Six are
binary MDB2 format and need a decoder; three are plain-text /
human-readable and don't:

**Encoded (MDB2 — need a decoder):**

| Source file | Script | Status |
|---|---|---|
| `Monsters.md` | [`decode_monsters_md.py`](decode_monsters_md.py) | ✅ working — full extraction: overlay block + 17 read-only "Other Info" fields + 5-slot Abilities array with human-readable code names; 1099 / 1100 records from MegaMUD 2.0 Beta P1 stock, 1859 / 1860 from paradigm, 1737 / 1738 from legacy MegaMUD (one empty-name orphan in each); format-agnostic |
| `Items.md`    | [`decode_items_md.py`](decode_items_md.py)       | ✅ working — 1950 / 1950 items from MegaMMUD v2.0 Beta P1 stock; every UI flag confirmed via single-flag-edit diffs |
| `Spells.md`   | [`decode_spells_md.py`](decode_spells_md.py)     | ✅ working — full extraction: every Spell Details dialog field, 10-slot ability array, per-level scaling formula; 2011 / 2011 records from MegaMUD 2.0 Beta P1 (Paradigm), 0 skipped; 12 spells verified field-by-field against the dialog |
| `Classes.md`  | —                                                | not yet reversed |
| `Paths.md`    | —                                                | not yet reversed |
| `Races.md`    | —                                                | not yet reversed |

The MDB2 framing (magic, 1024-byte pages, record header) is shared
across all six, so most of the forward work is discovering each
file's per-record payload layout — not rewriting the scanner.

**Plain-text (no decoder needed):**

| Source file | Notes |
|---|---|
| `Messages.md` | Human-readable per-line message catalogue. Open in any text editor; comma-separated. |
| `Rooms.md`    | Same as Above |
| `Macros.md`   | Same as above |

For these 3 files, you can very quickly figure out the flag toggles and how the lines are constructed.
i have an HTML based app that can generate the info for rooms.md and also loop files(which isn't the focus
of this repo)

## Requirements

- Python 3.10+ (uses `int | None` style type hints)
- No third-party packages

## Quickstart

```bash
python3 decode_monsters_md.py path/to/Monsters.md monsters.overlay.json
python3 decode_items_md.py    path/to/Items.md    items.overlay.json
python3 decode_spells_md.py   path/to/Spells.md   spells.json
```

`decode_monsters_md.py` additionally takes `--spells`, which resolves
every spell Number it emits into a readable `"name (number)"` label
(see [Cross-file spell names](#cross-file-spell-names) below):

```bash
python3 decode_monsters_md.py path/to/Monsters.md monsters.overlay.json \
    --spells path/to/Spells.md
```

All three scripts share the same CLI shape:

```
positional arguments:
  input        Path to a MegaMUD .md file (MDB2 format)
  output       Path to write JSON output

options:
  --emit-defaults   Emit every record (default: omit records that
                    match the implicit defaults — keeps the output
                    file small; consumers fill in defaults on read)
  --quiet           Suppress the per-distribution summary line
```

`decode_spells_md.py` emits every record (spells have no "implicit
defaults" tier to omit), so in place of `--emit-defaults` it takes
`--keep-unknown`, which includes the raw `+0x28` overlay word in the
output. `decode_monsters_md.py` additionally takes `--spells PATH`.

Example against a stock install:

```bash
python3 decode_items_md.py \
    "MegaMMUD v2.0 Beta P1 (Stock)/Default/Items.md" \
    items.overlay.json
```

## What the decoders extract

### `decode_monsters_md.py` — output schema

Per-monster record matching the Monster/NPC Details dialog. Each
output JSON object carries the overlay-block fields (the editable
left-pane controls), the read-only "Other Info" stat block, and a
decoded **Abilities** array surfacing the dialog's ability-based
rows (NonLiving / Resist-Cold / Magical / SpellImmu / SeeHidden /
Resist-Fire / etc.):

```json
{
  "Number":           818,
  "Name":             "hanging tree",
  "Relationship":     "Enemy",
  "Priority":         "High",
  "FindFirst":        false,
  "DontBackstab":     false,
  "NotHostile":       false,
  "CheckIfAlive":     true,
  "StopToKillIfAble": false,
  "Level":            2000,
  "MaxHP":            7200,
  "Energy":           1000,
  "MagicRes":         130,
  "FollowPercent":    100,
  "ArmourClass":      0,
  "DamageResist":     80,
  "EnslaveLevel":     9999,
  "Type":             "Stationary",
  "Alignment":        "Chaotic Evil",
  "GameLimit":        1,
  "RegenTime":        22,
  "Weapon":           0,
  "Experience":       6500000,
  "DeathSpell":       1122,
  "CreateSpell":      0,
  "Undead":           "Yes",
  "Abilities": [
    { "Code":  28, "Name": "Magical",     "Value":   5 },
    { "Code": 139, "Name": "SpellImmu",   "Value":  35 },
    { "Code": 109, "Name": "NonLiving",   "Value":   0 },
    { "Code":  57, "Name": "SeeHidden",   "Value":   0 },
    { "Code":   5, "Name": "Resist-Fire", "Value": -50 }
  ]
}
```

| Field | Type | Notes |
|---|---|---|
| `Number` | int | MegaMUD monster ID (= dialog's WCC No) |
| `Name` | string | Display name |
| **Overlay block** *(editable left-pane fields)* | | |
| `Relationship` | string | `Unknown` / `Friend` / `Avoid` / `Enemy` / `Flee` / `Hangup` |
| `Priority` | string | `First` / `High` / `Normal` / `Low` / `Last` |
| `FindFirst` | bool | "Find first" Options checkbox |
| `DontBackstab` | bool | "Don't backstab" Options checkbox |
| `NotHostile` | bool | "Not hostile" Options checkbox |
| `CheckIfAlive` | bool | "Check if alive" Options checkbox |
| `StopToKillIfAble` | bool | "Stop to kill if able" Options checkbox (new in MegaMUD 2.0 Beta — older files leave this 0) |
| **Stat block** *(read-only "Other Info" pane — all `rel`-anchored, see file-format section below)* | | |
| `Sex` | string | `It` / `Male` / `Female` |
| `Level` | int | Dialog "Level" — same byte as the MDB's `HPRegen` field |
| `MaxHP` | int | "Max. HP's" |
| `Energy` | int | Dialog "Energy" |
| `MagicRes` | int | Dialog "Magic Res" |
| `FollowPercent` | int | "Follow %" (used by Type=Follower roles) |
| `ArmourClass` | int | The first number in the dialog's `AC: X/Y` row |
| `DamageResist` | int | The second number in `AC: X/Y` |
| `EnslaveLevel` | int | "Enslave Level" (= MDB's `CharmLVL` field) |
| `Type` | string | `Solo` / `Leader` / `Follower` / `Stationary` |
| `Alignment` | string | `Good` / `Evil` / `Chaotic Evil` / `Neutral` / `Lawful Good` / `Neutral Evil` / `Lawful Evil` |
| `GameLimit` | int | "Game max" — concurrent-instance cap |
| `RegenTime` | int | "Regen" value (display unit varies — MegaMUD renders as hours / days based on magnitude) |
| `Weapon` | int | Weapon item Number (0 = none / unarmed) |
| `Experience` | int | "Experience" the dialog shows — the full multiplied total per kill |
| `DeathSpell` | int | Spell Number cast on the monster's death (0 = none) |
| `CreateSpell` | int | Spell Number cast on the monster's spawn (0 = none) |
| `Undead` | string | `Yes` / `No` (any non-zero byte = Yes; 1 and 255 both appear in stock as Yes sentinels) |
| **Abilities** *(synthesised dialog rows)* | | |
| `Abilities[]` | array | Up to 5 `{ Code, Name, Value }` triples. Empty slots (code 0) are omitted. Surfaces dialog rows like NonLiving / Resist-Cold / Resist-Fire / SpellImmu / Magical / SeeHidden / Crits / Slay / Quickness / etc. — see ABILITY_NAMES in the script for the full code table. |
| **Multi-record sections** | | |
| `Attacks[]` | array | Up to 5 `{ Min, Max, Energy, [HitSpell], [Percent] }` slots. Each surfaces as a dialog "Attacks:" or "Casts:" row (MegaMUD splits by AttType — Normal → Attacks, Spell → Casts — but AttType isn't stored in the .md). `HitSpell` + `Percent` only emitted for slots 0–2. Empty slots (Min == Max == Energy == 0) are omitted. |
| `MidSpells[]` | array | Up to 5 `{ Spell, Percent, Level }` slots — the engine's mid-round / between-rounds spell procs. `Spell` is a Spells.md Number. Empty slots (Spell == 0 or 0xFFFF) are omitted. |
| `DropItems[]` | array | Up to 5 `{ Item, Percent }` slots. The MDB schema exposes 10 drop fields but only 5 are serialised in the .md (slots 5–9 are always zero and unstored). Empty slots (Item == 0) are omitted. |

The decoder works transparently on **both legacy MegaMUD and MegaMUD
2.0 Beta** `Monsters.md` files — same record layout, same rel-anchored
stat-block offsets, same flag-bit semantics. No version flag needed.

### `decode_items_md.py` — output schema

Per-item overlay matching the Game Item Details dialog. Each record:

```json
{
  "Number":           172,
  "Name":             "black star key",
  "MinToKeep":        0,
  "MaxToGet":         1,
  "AutoCollect":      true,
  "AutoDiscard":      false,
  "AutoFind":         true,
  "AutoOpen":         false,
  "AutoBuy":          false,
  "AutoSell":         false,
  "CannotBeTaken":    false,
  "MustHaveMinimum":  false,
  "LoyalItem":        false,
  "CanUseToBackstab": false
}
```

| Field | Type | Values |
|---|---|---|
| `Number` | int | MegaMUD item ID |
| `Name` | string | Display name |
| `MinToKeep` | int | Engine's "Min. to keep" — 0 means the UI's "None" default |
| `MaxToGet` | int | Engine's "Max to get" — 0 means the UI's "All" default |
| `AutoCollect` / `AutoDiscard` / `AutoFind` / `AutoOpen` / `AutoBuy` / `AutoSell` | bool | The six "Auto-*" Options checkboxes |
| `CannotBeTaken` | bool | "Cannot be taken" — folds both encoded bits (`0x0040` + `0x4000`) since MegaMUD renders them under the same checkbox |
| `MustHaveMinimum` | bool | "Must have minimum" |
| `LoyalItem` | bool | "Loyal item" — lives in a separate extended byte at record offset `+0x70`, not the main Options word |
| `CanUseToBackstab` | bool | "Can use to backstab" — exposed for completeness (combat code consumes this to filter BS-eligible weapons) |

### "Auto-equip" — beta-only checkbox, bit position still unknown

The **`Auto-equip`** checkbox appears on items in the MegaMUD 2.0 Beta
UI (between Auto-discard and Auto-find) but no packaged item record
ships with it pre-set, so there's no positive witness yet to identify
the bit position via diff. Once a witness exists (a stock record with
it on, or a single-toggle edit), the bit can be added to
`decode_items_md.py` without changing the rest of the code.

The corresponding **`Stop to kill if able`** monster checkbox **has
been identified** — see the `decode_monsters_md.py` schema above and
the Monsters.md overlay-block table below.

### `decode_spells_md.py` — output schema

Per-spell record matching the Spell Details dialog: the editable Spell
box (left pane) plus the read-only "More Info" pane (right).

```json
{
  "Number":         2,
  "Name":           "illuminate",
  "Code":           "illu",
  "MinLevel":       2,
  "Mana":           4,
  "Type":           "Mage 1",
  "TypeCode":       4,
  "Targets":        ["Self"],
  "TimedDuration":  true,
  "EvilInCombat":   false,
  "ItemActivated":  false,
  "SpecialCommand": "",
  "Difficulty":     5,
  "MaxLevel":       24,
  "Energy":         0,
  "Duration":       70,
  "CastType":       "Immediate",
  "CastTypeCode":   3,
  "Sphere":         "Normal",
  "FromItem":       120,
  "MdbTargets":     1,
  "MinBase":        95,
  "MaxBase":        95,
  "Scaling":        { "MaxInc": 5, "MaxIncLevels": 2, "MinInc": 5, "DurInc": 1 },
  "Abilities": [
    { "Slot": 0, "Code": 13,  "Name": "Illu",    "Value": 0 },
    { "Slot": 1, "Code": 115, "Name": "DescMsg", "Value": 10140 }
  ]
}
```

| Field | Type | Notes |
|---|---|---|
| `Number` | int | Spell ID — the dialog's **WCC No**, and the same value `Monsters.md` stores in `DeathSpell` / `MidSpells` / `Attacks[].HitSpell` |
| `Name` / `Code` | string | Display name and the 4-char cast code ("illu", "mmis") |
| **Editable Spell box** | | |
| `MinLevel` | int | "Minimum level" |
| `Mana` | int | "Required Mana/Kai" |
| `Type` / `TypeCode` | string / int | Class + circle — `Any`, `Priest 1..3`, `Mage 1..3`, `Druid 1..3`, `Bard 1`, `Mystic 1` |
| `Targets` | array | Any of `Self` / `Player` / `Area` / `Monster` |
| `TimedDuration` | bool | "Timed duration" checkbox |
| `EvilInCombat` | bool | "Evil in combat" checkbox |
| `ItemActivated` | bool | Set on exactly the 16 `use <item>` records (#10001–10077) |
| `SpecialCommand` | string | "Special command" text field, e.g. `use cosmic staff` |
| **Read-only "More Info" pane** | | |
| `Difficulty` | int | Signed — negative values occur (sunbolt is −14) |
| `MaxLevel` | int | "Max. level" (0 = the dialog omits the row) |
| `Energy` | int | "Energy used" (0 renders as "None") |
| `Duration` | int | Rounds (0 renders as "None"); negative values occur on enchantments |
| `CastType` / `CastTypeCode` | string / int | `Immediate` or `Per round`. The 16 records with code `1` annotate the Max. level row "(always used)" |
| `Sphere` | string | `Cold` / `Hot` / `Stone` / `Lightning` / `Normal` / `Water` / `Poison` |
| `FromItem` | int | Items.md Number of the scroll/item taught from (0 = none) |
| `MdbTargets` | int | The stock MDB `Targets` column, which drives the "Effects:" line. Kept alongside `Targets` because that one is user-editable and this one is not |
| `MinBase` / `MaxBase` | int | Effect magnitude range |
| `Scaling` | object | Per-level growth — see the formula below |
| `Abilities[]` | array | Up to 10 `{Slot, Code, Name, Value}` entries, using the **same ability table as Monsters.md** |

**Damage / effect formula.** The `Scaling` block is what the More Info
pane's parenthesised expression renders from:

    MinBase  to  (MaxBase + MaxInc * level / MaxIncLevels)

| Spell | Dialog shows | MinBase | MaxBase | MaxInc | MaxIncLevels |
|---|---|---|---|---|---|
| magic missile | 6 to (15 + 1 \* level) | 6 | 15 | 1 | 1 |
| lightning bolt | 12 to (20 + 2 \* level) | 12 | 20 | 2 | 1 |
| way of the swan | 4(4 + 1 \* level / 3) | 4 | 4 | 1 | 3 |

**Abilities.** Slot 0 is the primary effect, and its dialog magnitude
comes from `MinBase`..`MaxBase` rather than its own `Value` — illuminate
stores `Abil-0 = 13` (Illu) with `AbilVal-0 = 0`, `MinBase = MaxBase =
95`, and the dialog renders `Illu: +95`. Slots 1–9 use their own values.
Some reads that make the alignment obvious:

| Spell | Abilities |
|---|---|
| petrification | ConfuseMsg, DescMsg, NonMagicalSpell, StartMsg, M.R. 100, Magical 10, DR 500, AC 100, Damage 5 |
| form of the viper | JumpKDmg + Crits, JumpKAcc, KickAcc, PunchAcc, PunchDmg, KickDmg, Dodge |
| purifying tonic | CurePoison + 9 × RemovesSpell, each pointing at a spell Number |

### Cross-file spell names

`Monsters.md` stores spell references as bare Numbers. With a
`Spells.md` (or a `decode_spells_md.py` JSON) supplied via `--spells`,
`decode_monsters_md.py` adds a `"name (number)"` label beside each one —
`DeathSpell`, `CreateSpell`, every `MidSpells` slot, and every
`Attacks[].HitSpell`:

```json
"DeathSpell": 1122,
"DeathSpellLabel": "tree (1122)",
"MidSpells": [
  { "Spell": 1037, "Percent": 20, "Level": 100, "SpellLabel": "plant summon (1037)" }
],
"Attacks": [
  { "Min": 65, "Max": 100, "Energy": 200, "HitSpell": 318,
    "Percent": 20, "HitSpellLabel": "knockdown (318)" }
]
```

The numeric fields are untouched, so the addition is purely additive and
output without `--spells` is byte-identical to before. Unresolvable
Numbers render as `unknown (N)` rather than being dropped, so a trimmed
`Spells.md` degrades visibly. Across the Paradigm `Monsters.md`,
**1314 / 1314** references resolve with none unknown.

## File format reverse-engineered

Both `.md` files share the MDB2 framing — only the per-record body
differs. The framing is described once here; per-file specifics follow.

### Top-level layout (shared)

- Bytes 0..3: magic `MDB2`.
- Bytes 4..15: file header (purpose unclear; not needed for decoding).
- Bytes 0x400..end: **1024-byte (0x400) pages** of slot-allocated
  records. Records are **not** sorted by `Number` and can span page
  boundaries in some cases.

### Per-record header (shared)

Variable length depending on Number's digit count:

```
+0      1 B   marker byte (0xdb / 0xdc / 0xdd — varies per record/page)
+1      1 B   0x01 (constant)
+2      N B   ASCII digits of Number (1–5 chars)
+2+N    1 B   0x00 null terminator
+3+N    4 B   zero padding
+7+N    1 B   0x80 sentinel
+8+N    2 B   u16 little-endian Number (sanity check vs ASCII digits)
+10+N   ...   Name string (null-terminated ASCII / Latin-1)
```

The scanner regex `[\x00-\xff]\x01([0-9]{1,5})\x00\x00{0,8}\x80` finds
every record by anchoring on the sentinel and cross-checking the
LE u16 against the captured ASCII digits.

### After the name

This is where the two file types diverge.

**Monsters.md** stores zero or more **null-terminated spell-name
reference strings** — short codes from the Spells table naming the
spells the monster casts. (Living dummy's `fsdfsd` reference is a
truncation of spell #986 `sdfsdfsdfsdfs`.) Then zero padding, then the
overlay block anchored on the rel byte.

**Items.md** stores **shop-display strings** in fixed-width slots
(MegaMUD's "Bought/sold" combobox values). After the shop strings comes
the fixed-width overlay block at predictable record-relative offsets.

### Monsters.md overlay block (rel-anchored)

The overlay fields sit at fixed offsets relative to the **rel byte**
(the relationship enum at the end of the overlay block, followed by
≥4 trailing zeros).

| Offset (relative to rel byte) | Field | Bits |
|---|---|---|
| `rel − 4` | priority byte | upper nibble: `0x10` Last, `0x20` Low, `0x40` High, `0x80` First, `0x00` Normal. Bit `0x08` = **FindFirst**. |
| `rel − 3` | flags byte | `0x01` **DontBackstab**, `0x02` **NotHostile**, `0x04` **CheckIfAlive**, `0x08` **StopToKillIfAble** (MegaMUD 2.0 Beta+). |
| `rel` | relationship byte | `0x01` Unknown, `0x02` Friend, `0x03` Avoid, `0x04` Enemy, `0x05` Flee, `0x06` Hangup. |

Anchoring algorithm: scan forward past the name + spell-ref strings;
the first byte in `{0x01..0x06}` followed by ≥4 trailing zeros and
preceded (4 bytes earlier) by a sane priority enum value
(`0x00 / 10 / 20 / 40 / 80` in the upper nibble) is the rel byte. The
extended-trailing-zeros requirement filters out the false-anchor
classes — the `CheckIfAlive` byte (also `0x04` when set) and the
`DontBackstab` byte (`0x01`, same as the Unknown rel value) sit too
close to non-zero data to satisfy it.

**Spell-name reference run detection requires ≥2 consecutive printable
bytes** to count as a string-skip. A single-byte `0x40` / `0x4e` / etc.
at rel-1 in legacy MegaMUD files is data, not a string — being strict
about run length is what makes the same decoder work on both legacy
and 2.0 Beta files without a version flag.

### Monsters.md stat block (rel-anchored, read-only "Other Info")

The static record data — what the dialog renders in its right-pane
"Other Info" box — lives at fixed offsets after the rel byte. Offsets
were pinned down by **cross-referencing every record's bytes against
an exported `Monsters.json` representation of the MDB tables** (any tool that converts the source MDB to per-table JSON works as the side-table for offset discovery).
For each candidate offset/encoding, we test how many of the 1100 stock
records read a value matching the JSON twin's field — 100% match means
the offset is right. This methodology surfaced 17 stable fields in one
sweep without needing any single-flag edit-diff testing.

| Offset (relative to rel byte) | Field | Type | Notes |
|---|---|---|---|
| `rel + 0x0f` | Sex | u8 enum | `0=It, 1=Male, 2=Female`. Pinned via 3-way dialog cross-check (giant rat / drunken brawler / barmaid). |
| `rel + 0x10` | Level | u16 LE | Dialog "Level". Same byte as the MDB's `HPRegen` field — MegaMUD treats monster level and HP-regen-per-tick as the same value. |
| `rel + 0x14` | MaxHP | u16 LE | "Max. HP's" |
| `rel + 0x16` | Energy | u16 LE | "Energy" |
| `rel + 0x18` | MagicRes | u16 LE | "Magic Res" |
| `rel + 0x1a` | FollowPercent | u8 | "Follow %" (only used when Type=Follower) |
| `rel + 0x1c` | ArmourClass | u16 LE | First number in dialog's `AC: X/Y` |
| `rel + 0x1e` | DamageResist | u16 LE | Second number in `AC: X/Y` |
| `rel + 0x20` | EnslaveLevel | u16 LE | "Enslave Level" (= MDB `CharmLVL`) |
| `rel + 0x24` | Type | u8 enum | `0=Solo, 1=Leader, 2=Follower, 3=Stationary` |
| `rel + 0x25` | Alignment | u8 enum | `0=Good, 1=Evil, 2=Chaotic Evil, 3=Neutral, 4=Lawful Good, 5=Neutral Evil, 6=Lawful Evil` |
| `rel + 0x26` | GameLimit | u8 | "Game max" — instance cap |
| `rel + 0x28` | RegenTime | u8 | "Regen" — MegaMUD renders as hours / days based on magnitude |
| `rel + 0x47` | Abil-0 code | u16 LE | Ability code 0 |
| `rel + 0x49` | Abil-1 code | u16 LE | Ability code 1 |
| `rel + 0x4b` | Abil-2 code | u16 LE | Ability code 2 |
| `rel + 0x4d` | Abil-3 code | u16 LE | Ability code 3 |
| `rel + 0x4f` | Abil-4 code | u16 LE | Ability code 4 |
| `rel + 0x51` | AbilVal-0 | i16 LE | Ability 0 value (signed — Resist-Fire can be −50) |
| `rel + 0x53` | AbilVal-1 | i16 LE | |
| `rel + 0x55` | AbilVal-2 | i16 LE | |
| `rel + 0x57` | AbilVal-3 | i16 LE | |
| `rel + 0x59` | AbilVal-4 | i16 LE | |
| `rel + 0x5b` | Weapon | u16 LE | Item Number (0 = unarmed) |
| `rel + 0x5d..0x65` | MidSpell-0..4 (slot Numbers) | 5 × u16 LE, stride 2 | Spell Number; 0 / 0xFFFF = unused |
| `rel + 0x6f` | Experience | u32 LE | Total exp per kill (= dialog value verbatim — 5/5 dialog matches: lashworm=12, Kai Master=450000, dwarven cleric=150, Zanthus the Lich=250000000, Tyrannosaur=649935000) |
| `rel + 0x73..0x77` | MidSpell%-0..4 | 5 × u8 | Cast chance |
| `rel + 0x7d..0x85` | AttMin-0..4 | 5 × u16 LE, stride 2 | Attack min damage |
| `rel + 0x87..0x8f` | AttMax-0..4 | 5 × u16 LE, stride 2 | Attack max damage |
| `rel + 0x91..0x99` | AttEnergy-0..4 | 5 × u16 LE, stride 2 | Attack energy cost |
| `rel + 0x9b` | DeathSpell | u16 LE | Spell Number cast on death |
| `rel + 0x9d` | CreateSpell | u16 LE | Spell Number cast on spawn |
| `rel + 0x9f..0xa3` | MidSpellLVL-0..4 | 5 × u8 | Cast level |
| `rel + 0xa4` | Undead | u8 | Non-zero = Yes (1 standard; 255 sentinel) |
| `rel + 0xa5..0xa9` | AttHitSpell-0..2 | 3 × u16 LE, stride 2 | Spell-on-hit (slots 0–2 only) |
| `rel + 0xab..0xad` | Att%-0..2 | 3 × u8 | Per-attack use chance (slots 0–2 only) |
| `rel + 0x2e..0x36` | DropItem-0..4 | 5 × u16 LE, stride 2 | Loot item Number |
| `rel + 0x38..0x3c` | DropItem%-0..4 | 5 × u8 | Loot drop chance |

**Ability decoding**: each Abil-N code looks up into MajorMUD's
canonical ability-name table (mirrored verbatim in the decoder script
as `ABILITY_NAMES`). That's how the dialog's `Resist-Cold: +100` /
`SpellImmu: 35` / `NonLiving: 0` rows are synthesised — they're
ability slots, not separate stat fields. Only 5 slots are stored in
`Monsters.md` (the MDB has 10 fields, but slots 5–9 are always zero
and aren't serialised).

**Fields that don't exist in `Monsters.md` at all** (verified absent
via exhaustive string + numeric searches across the full file):

- **AttName-N** (the "slashes you" / "bites you" attack strings) —
  searched the entire 541 KB binary for `bites` / `smashes` /
  `slashes` / `claws` / `rips you` / `punches`: **zero occurrences**.
  The only printable strings in the file are monster names. AttName
  strings must live in a separate MegaMUD file (likely `messages.md`
  or equivalent) or come from the source MDB.
- **AttType-N** (Normal / Spell / Rob enum) and **AttAcc-N**
  (per-attack accuracy) — appear in the MDB export but don't match
  anywhere in the .md at any offset/encoding combo. Likely computed
  / derived at display time from other fields and not stored. Without
  AttType, downstream tools can't reliably split the Attacks array
  into the dialog's "Attacks:" vs "Casts:" sections the way MegaMUD
  does (the dialog branches on AttType=Spell to pick the Casts label).
- **Group** (dialog string like "Slums, Sewers" / "Graveyard Crypt")
  and **Location** (`Map X, Room Y`) — derived from room / lair table
  joins at display time, not stored per-monster.
- ~~**DeathSpell-as-text**~~ — **resolved.** Pass `--spells` to render
  every spell reference as `"name (number)"`; see
  [Cross-file spell names](#cross-file-spell-names).

Per the project's scope (decode what `Monsters.md` stores), nothing
above is a gap in the decoder — they're either elsewhere on disk or
computed at runtime.

In the MegaMMUD v2.0 Beta P1 stock file the overlay-block distribution is:

- DontBackstab: 1 monster (#66 moaning spirit)
- NotHostile: 1 monster (#848 ivory golem)
- CheckIfAlive: 140 monsters (#113 banshee, #818 hanging tree, many boss-tier mobs)
- FindFirst: 180 monsters
- StopToKillIfAble: 0 monsters (brand-new flag in 2.0 Beta; no packaged record uses it yet)

### Items.md overlay block (fixed-offset)

Item records are **fixed-layout** within their slot — every overlay
field lives at a known record-relative offset regardless of the name
or shop-string lengths:

| Offset | Field | Type | Notes |
|---|---|---|---|
| `+0x62` | MinToKeep | u16 LE | 0 = UI's "None" default |
| `+0x64` | MaxToGet | u16 LE | 0 = UI's "All" default |
| `+0x6E` | Options | u16 LE | main flag bitfield (see below) |
| `+0x70` | Extended Options | u16 LE | Loyal item lives in bit `0x0002` of this word |

Bit layout inside the `+0x6E` Options u16:

| Bit | Flag |
|---|---|
| `0x0002` | Auto-collect |
| `0x0004` | Auto-buy |
| `0x0008` | Auto-sell (or stash) |
| `0x0020` | Auto-find |
| `0x0040` | Cannot be taken |
| `0x0200` | Can use to backstab |
| `0x0400` | Must have minimum |
| `0x0800` | Auto-discard |
| `0x1000` | Auto-open |
| `0x2000` | Auto-find (alternate — UI surfaces the same checkbox) |
| `0x4000` | Cannot be taken (alternate — same UI checkbox) |

Bit layout inside the `+0x70` Extended Options u16:

| Bit | Flag |
|---|---|
| `0x0002` | Loyal item |

#### Notes on the dual-bit flags

Two UI flags have **two distinct bit positions** that surface as the
same checkbox in MegaMUD's dialog — fold both into a single boolean
when decoding:

- **Cannot be taken**: `0x0040` is set on 199 stock items (mostly
  fixed-in-room scenery: books, stoves, bulletins); `0x4000` is set on
  252 items (gravestones, parchment deeds, plaques). Items with `0x4400`
  (both set) exist (6 items in the stock corpus). Best guess at why
  two bits: one tags "system-fixed furniture", the other tags
  "quest-bound / per-instance fixed". MegaMUD's UI doesn't
  distinguish — both render as a checked "Cannot be taken".
- **Auto-find**: `0x0020` is the common form (18 stock items, all
  keys / jewelry); `0x2000` is the rare alternate (only 2 stock items
  — golden idol, wire key). Confirmed via UI screenshot of golden
  idol showing Auto-find checked at the defaults tier.

#### Bits that aren't UI Options

Some bits in the `+0x6E` low byte are set on stock items but do **not**
surface as any visible Options checkbox in the Game Item Details
dialog — verified by opening items like `#1244 cosmic staff`
(`Options=0x000e`, three bits set, dialog shows zero checkboxes
checked) and `#1200 red chitin shield` (`Options=0x0001`, one bit
set, dialog shows nothing checked). These appear to be **internal
categorization flags** the engine uses but doesn't expose to the user:

| Bit | Stock items affected | Sample items |
|---|---|---|
| `0x0001` | 8 | red chitin shield / leggings / helm, parchment deeds |
| `0x0002` (when isolated) | 26 | basic starter weapons (club, dagger, longsword, broadsword, shortsword) — they have low-bit `0x02` for some engine reason despite Auto-collect ALSO being `0x02` |
| `0x0008` (in `0x000e`/`0x000f`) | 4 | cosmic staff, starhammer, deathblade, deathcoil |

The `0x0002` overload is the most surprising: that bit IS Auto-collect
when surfacing in the dialog, but also appears to be set on starter
weapons as an internal flag (perhaps a "ships in the auto-collect
default profile" tag), with the dialog showing no checkbox at the
defaults tier. For the decoder we treat it as Auto-collect uniformly —
downstream consumers can override individual records if needed.

In `+0x70`, the byte at `+0x71` carries an unknown `0x40` flag set on
many stock items (waterskin, e.g.) that doesn't move when toggling any
of the UI Options. Probably another internal categorization byte; not
surfaced by the decoder.

### Spells.md layout (fixed-offset, constant-length payload)

Spells.md is the **easiest** of the three. Like Items.md it is
fixed-layout with no anchor scanning, and better still the payload
length is constant: the marker byte is `0xa5 + digit-count` and the
`0x80` sentinel sits digit-count bytes further in, so the run from the
sentinel to end-of-record is **always `0x9f` bytes** no matter how wide
the Number is. Records pack 3–4 per page.

All offsets below are relative to the `0x80` sentinel. The "MDB" column
names the matching column in an exported `Spells.json`.

| Offset | Type | Field | MDB column | Dialog label |
|---|---|---|---|---|
| `+0x01` | u16 | Number | `Number` | WCC No |
| `+0x03` | 30B str | Name | `Name` | Name |
| `+0x21` | 7B str | Code | `Short` | Code |
| `+0x28` | u16 | **MegaMUD overlay bitfield** | — | target checkboxes, Timed duration, Evil in combat |
| `+0x2C` | 26B str | Special command | — | Special command |
| `+0x55` | u8 | MinLevel | `ReqLevel` | Minimum level |
| `+0x56` | u8 | MaxInc | `MaxInc` | — |
| `+0x57` | u16 | Mana | `ManaCost` | Required Mana/Kai |
| `+0x59` | u16 | Energy | `EnergyCost` | Energy used (0 = None) |
| `+0x5B` | i16 | MinBase | `MinBase` | — |
| `+0x5D` | i16 | MaxBase | `MaxBase` | — |
| `+0x5F` | i16 | Duration | `Dur` | Duration (rounds) |
| `+0x61` | i16 | Difficulty | `Diff` | Difficulty |
| `+0x63` | u8 | Targets (stock) | `Targets` | drives "Effects:" |
| `+0x64` | u8 | Class + circle | `Magery` + `MageryLVL` | Type |
| `+0x65` | u8 | Sphere | `AttType` | Sphere |
| `+0x66` + 2k | 10 × u16 | Abil-0..9 | `Abil-0..9` | More Info ability rows |
| `+0x7A` + 2k | 10 × i16 | AbilVal-0..9 | `AbilVal-0..9` | " |
| `+0x8E` | u8 | MaxLevel | `Cap` | Max. level |
| `+0x8F` | u8 | MaxIncLevels | `MaxIncLVLs` | — |
| `+0x90` | u8 | MinInc | `MinInc` | — |
| `+0x91` | u8 | DurInc | `DurInc` | — |
| `+0x92` | u8 | Cast type (0 / 1 / 3) | — | Cast type |
| `+0x93` | u16 | FromItem | (`Learned From`) | From item |

Bytes `+0x46`–`+0x54` and `+0x95`–`+0x9E` are always zero.

**Unused ability-value slots hold `0x2020`**, not zero — space padding
inherited from the source MDB's text columns (the exported
`Spells.json` shows the same 8224 filler). Decoding them naively yields
a bogus 8224 on most records.

### Spells.md — Type, the class/circle byte

`+0x64` folds the MDB's `Magery` (class) and `MageryLVL` (circle)
columns into one byte. Cross-tabulating the pair against it across 1994
records is fully deterministic:

| MDB `Magery` | Class | `MageryLVL` 0/1 | 2 | 3 |
|---|---|---|---|---|
| 0 | none | 0 | | |
| 2 | Priest | 1 | 2 | 3 |
| 1 | Mage | 4 | 5 | 6 |
| 3 | Druid | 7 | 8 | 9 |
| 4 | Bard | 10 | — | — |
| 5 | Mystic | 11 | — | — |

The encoding is **compact, not a flat sequential index** over the radio
grid — Bard and Mystic each occupy a single value rather than Bard
owning 10/11/12 with Mystic at 13. Confirmed by dialog: `way of the cat`
and `way of the swan` both store 11 and both render **Mystic 1**.

### Spells.md — Sphere (MDB `AttType`)

| Value | Sphere | Dialog witness |
|---|---|---|
| 0 | Cold | frost jet |
| 1 | **Hot** | sunbolt |
| 2 | **Stone** | stonestrike |
| 3 | Lightning | lightning bolt |
| 4 | Normal | illuminate, magic missile |
| 5 | **Water** | acid jet |
| 6 | Poison | bites |

**Don't guess these names** — three are counter-intuitive and cohort
inference gets them wrong: 1 is "Hot" not Fire, 2 is "Stone" not Earth,
and 5 is "Water" not Acid (acid jet's sphere reads **Water**). They
line up with the ability table's `Resist-*` entries: Resist-Cold,
Resist-Fire, Resist-Stone, Resist-Lightning, Resist-Water.

### Spells.md overlay block (`+0x28`)

`+0x28` matches **no** MDB column at any offset/encoding. It is
MegaMUD's own per-spell overlay — the same role the `+0x6E` Options
word plays in Items.md — and holds every editable checkbox in the
dialog's Spell box:

| Bit | Flag |
|---|---|
| `0x0001` | item-activated (exactly the 16 `use <item>` records, #10001–10077) |
| `0x0002` | **Timed duration** |
| `0x0004` | **Evil in combat** |
| `0x0008` | Cast type Immediate (mirrors `+0x92 == 3` exactly, 2011/2011) |
| `0x0010` | target **Self** |
| `0x0020` | target **Player** |
| `0x0040` | target **Monster** |
| `0x0080` | target **Area** |

Note the target bit order is Self / Player / **Monster** / **Area** —
*not* the order the checkboxes are laid out in the dialog (Self, Player
/ Area, Monster).

These are the editable overlay; the MDB `Targets` column at `+0x63` is
the stock value the read-only "Effects:" line renders from. The two
agree throughout the stock corpus — each `+0x63` value maps to exactly
one checkbox set (`1` → Self, `2` → Self+Player, `4` → Monster, `6` →
Self+Monster, `8` → Player+Monster, `7` → Self+Player+Monster, `11`/`12`
→ Area, `13` → Self+Area; `0` is the monster-spell catch-all and
varies) — but since one is editable and the other is not, the decoder
reports both.

### Spells.md — the "Use:" dropdown is not per-spell data

Its options are *installed defaults / for all characters / only for this
BBS / only for this character* — the same override-tier selector the
Items.md methodology below refers to as `Use: installed defaults`. It
chooses which data layer the dialog reads and writes, so it is not
stored per record and no byte in the payload correlates with it. Every
spell captured reads "only for this character" because that is the tier
the session was on.

### Fields NOT stored in Spells.md

Present in an exported `Spells.json` but absent from the binary — the
best-scoring offset for each is one of the always-zero trailing bytes,
i.e. it only matches the zero-valued majority:

- `TypeOfResists` (83.6% — spurious), `MageryLVL` as a standalone
  column (85.4% — folded into `+0x64`), `Learnable` (85.9%)
- `MinIncLVLs` (93.6%, best offset is `MaxIncLVLs`) and `DurIncLVLs`
  (90.2%, best offset is `DurInc`) — MegaMUD keeps only one of each
  pair. In the MDB itself `MinIncLVLs == MaxIncLVLs` for 1871/1994
  records and `DurIncLVLs == DurInc` for 1801/1994, which is exactly
  the ceiling those offsets hit. That equality-rate ceiling is the
  signature of a field that isn't stored at all.
- `Classes`, `Casted By` — join-derived strings, not per-spell data.

## Validation methodology — Spells.md

Same JSON cross-reference sweep used for the Monsters.md stat block:
brute-force every (offset, encoding) pair against every numeric column
of an exported `Spells.json` and count exact matches. Against the
Paradigm 1.9.1 MDB export (1994 Numbers shared with the `.md`):

| Field | Match |
|---|---|
| Energy, Sphere, Type | 100.00% |
| MdbTargets, MinLevel | 99.95% |
| Difficulty, DurInc | 99.90% |
| MaxBase, MaxLevel | 99.85% |
| Abilities (code + value, 5758 populated slots) | 99.84% |
| Mana, MaxInc, MinInc | 99.80% |
| MinBase, MaxIncLevels | 99.75% |
| Duration | 99.70% |

The residual handful are genuine data drift — the `.md` was built from a
different snapshot than the 1.9.1 MDB, and where they disagree **the
`.md` is what MegaMUD displays** (illuminate's targets: the `.md` says
Self, the MDB export says Player, and the dialog shows **Self**
checked). `ReqLevel` has exactly one mismatch, `#1252`, where the MDB
holds 999 and the `.md` holds 231 — a u8 truncation of 999, not a decode
error.

Independently, `FromItem` at `+0x93` resolves for **544 / 544** non-zero
records to a real Items.md entry, and every one is named `scroll of
<that spell's name>`.

**Dialog verification.** Twelve spells checked field-by-field against
Spell Details — illuminate, magic missile, frost jet, lightning bolt,
sunbolt, stonestrike, acid jet, way of the cat, way of the swan, bites,
arrow trap, wounded — covering Mage / Druid / Mystic / Any types, all
three cast types, both target nibbles, every checkbox state, and all
seven spheres. **All twelve match on every visible field.**

The `+0x28` bits were pinned with a controlled set: five
`Targets = Self` spells differing only in the low nibble, so each bit
isolates against illuminate as baseline.

| # | Spell | `+0x28` | Timed | Evil | Cast type |
|---|---|---|---|---|---|
| 623 | arrow trap | 20 | ☐ | ☑ | Per round |
| 36 | way of the swan | 24 | ☐ | ☐ | Immediate |
| 2 | illuminate | 26 | ☑ | ☐ | Immediate |
| 455 | wounded | 30 | ☑ | ☑ | Immediate |

Illuminate vs way of the swan differ in exactly bit `0x02` and exactly
the Timed duration checkbox; arrow trap vs way of the swan swap bits
`0x04`/`0x08` and swap Evil-in-combat/Immediate. `#1 magic missile`
(100) and `#80 bites` (98) then pin the target nibble as Player+Monster
against illuminate's Self.

## Validation methodology — Items.md

Items.md's bit assignments were locked down via **single-flag edit
diffs** against the stock binary — the cleanest possible probe:

1. Start with the pristine `Items.md` file.
2. Pick a baseline item (we used `#283 waterskin` — it ships with
   only `Auto-buy` set, so the baseline `Options = 0x0004`).
3. In stock MegaMUD with `Use: installed defaults`, toggle a single UI
   Options flag (e.g. Auto-collect) on, hit OK.
4. Re-read the `Options` u16 from the modified `Items.md`.
5. The new bit that flipped is the bit position for whichever flag was
   toggled.

Sequence we ran against waterskin (cumulative — each toggle adds one
bit while the previous toggles stay on):

| Toggle | Pre `Options` | Post `Options` | New bit | Flag |
|---|---|---|---|---|
| (baseline) | — | `0x0004` | — | Auto-buy was already on by default |
| Auto-collect | `0x0004` | `0x0006` | `0x0002` | **Auto-collect** |
| Auto-open | `0x0006` (after revert) | `0x1004` | `0x1000` | **Auto-open** |
| Auto-sell | `0x1004` (after revert) | `0x000c` | `0x0008` | **Auto-sell** |
| Must have minimum | `0x000c` (after revert) | `0x0404` | `0x0400` | **Must have minimum** |
| Loyal item | `0x0404` | `0x0004` (no change!) | `+0x70` bit `0x02` | **Loyal item** (separate field) |
| Min to keep = 1 + Max to get = 5 | (defaults) | u16 `1` at `+0x62`, u16 `5` at `+0x64` | offsets | **MinToKeep / MaxToGet** |

Cannot-be-taken (`0x0040`), Can-use-to-backstab (`0x0200`),
Auto-discard (`0x0800`), and the Auto-find / Cannot-be-taken alternate
bits (`0x2000` / `0x4000`) were confirmed by **shipped-default UI
witnesses** — items where the stock binary already has the bit set
and the dialog at the `Use: installed defaults` tier shows the
corresponding checkbox ticked (book #580 → Cannot be taken; starsteel
scimitar #272 → Can use to backstab; agate stone #882 →
Auto-discard; golden idol #1281 → Auto-find; yellow parchment deed
#1010 → Cannot be taken).

## Validation methodology — Monsters.md

The overlay-block bit assignments were initially pinned down by
comparing the binary output of the decoder against the MegaMUD
`Monster/NPC Details` dialog for monsters with known flag combinations
at the `Use: installed defaults` tier:

| # | Monster | Priority | FF | NH | DB | CIA | Notes |
|---|---|---|---|---|---|---|---|
| 1   | giant rat                | Normal | - | - | - | - | sanity: all-defaults baseline |
| 54  | kobold slave             | Normal | ✓ | - | - | - | pins FindFirst alone with no priority enum |
| 63  | gigantic black ooze      | High   | - | - | - | - | pins Flee relationship |
| 66  | moaning spirit           | Normal | - | - | ✓ | - | pins DontBackstab at flags 0x01 |
| 113 | banshee                  | First  | - | - | - | ✓ | pins First (0x80) + CheckIfAlive (0x04) |
| 320 | mutant spider            | Normal | ✓ | - | - | - | pins FindFirst at priority 0x08 |
| 341 | dark-elf high priestess  | High   | ✓ | - | - | - | pins High + FindFirst combo (0x48) |
| 809 | Death Shrieker           | High   | - | - | - | - | High alone |
| 818 | hanging tree             | High   | - | - | - | ✓ | CheckIfAlive on High-priority Enemy |
| 838 | gremlin                  | Low    | - | - | - | - | pins Low (0x20) |
| 848 | ivory golem              | Normal | - | ✓ | - | - | pins NotHostile at flags 0x02 |
| 1091| jeweled viper            | Last   | - | - | - | - | pins Last (0x10), the rarest priority |

All 12 cross-checks pass against the rel-anchored extractor.

**Single-flag edit-diffs** (same methodology as Items.md) then
confirmed the rel-anchored stat-block additions:

| Edit | Before | After | Delta | Conclusion |
|---|---|---|---|---|
| Lashworm `Stop to kill if able` ON | flags=0x00 | flags=0x08 | rel-3 bit `0x08` | **StopToKillIfAble** (new in MegaMUD 2.0 Beta) |

**JSON cross-reference discovery** (much faster than per-field
edit-diffs): for the read-only "Other Info" fields, we scan every
candidate offset/encoding combo and count how many of the 1100
records read a value matching the same field in an exported
`Monsters.json`. 17 stable fields were identified in a single
sweep at 100% match (Level / MaxHP / Energy / MagicRes /
FollowPercent / ArmourClass / DamageResist / EnslaveLevel / Type /
Alignment / GameLimit / RegenTime / Weapon / DeathSpell /
CreateSpell / Undead, plus the 5 Abil-N + AbilVal-N slot pairs).

**Dialog-shown verification** (closes the loop on Experience):

| Monster | Dialog shows | Decoder reads | Match |
|---|---|---|---|
| #2 lashworm | Exp 12 | 12 | ✓ |
| #448 Kai Master | Exp 450,000 | 450,000 | ✓ |
| #417 dwarven cleric | Exp 150 | 150 | ✓ |
| #215 Zanthus the Lich | Exp 250,000,000 | 250,000,000 | ✓ |
| #514 Tyrannosaur | Exp 649,935,000 | 649,935,000 | ✓ |

(The earlier `u32 BE at rel+0x6c` interpretation happened to match
small-Exp monsters by coincidence — for high-end values it was
~100,000× wrong. `u32 LE at rel+0x6f` is the actual encoding.)

**Cross-version validation**: the same decoder runs cleanly against a
legacy MegaMUD `MONSTERS.md` (827 KB, 1738 records, originally
parsed at only 80% accuracy with the initial heuristic) once the
spell-name-reference detection was tightened to require ≥2 consecutive
printable bytes. Both legacy and beta files now decode at 99.9%
accuracy (skipping only the known empty-name orphan at #84). Lashworm
in the legacy file: `Enemy / Normal / DontBackstab / Level=1 / MaxHP=15
/ Exp=12 / Undead=No / Type=Follower / Alignment=Chaotic Evil` —
stat-block values identical to the beta file (as expected, since
they're the same realm data).

## Combined findings — what's the same across all three files

Monsters.md, Items.md and Spells.md share:

1. **MDB2 magic** at file offset 0.
2. **1024-byte (0x400) page-allocated** record layout, with records
   slot-packed (not necessarily sorted by Number).
3. **Identical record header** — a marker byte / `0x01` / ASCII Number
   digits / `0x80` sentinel / LE u16 Number cross-check / null-terminated
   Name string.
4. **String area after the Name** — Monsters.md uses this for
   spell-name references the monster casts; Items.md for shop-display
   strings; Spells.md for the 4-char cast Code and the Special command.
5. **The same ability-code table** (`ABILITY_NAMES`) — monsters and
   spells both encode their effects as `{code, value}` slots drawn from
   one shared MajorMUD ability enum. That is what lets Spells.md
   resolve `Monsters.md`'s spell references.

The same scanner regex finds every record in any of the three. Most of
the forward work for the remaining MDB2 files (Classes / Paths / Races)
is discovering each file's per-record payload, not redoing the framing.

## Combined findings — what's different

The overlay block's structure varies:

- **Monsters.md** uses **variable-position fields anchored on a rel
  byte** at the end of the overlay block. Records aren't fixed-width
  in their useful portion — the rel byte's position drifts based on
  how many spell-name reference strings the monster has after its
  name. The decoder scans for the rel byte using a heuristic
  (in-range value + extended trailing zeros + sane preceding bytes).

- **Spells.md** is the simplest: **fixed offsets from the `0x80`
  sentinel**, and the payload after that sentinel is a **constant
  `0x9f` bytes** on every record regardless of Number width. No anchor
  scanning, no variable-width region to skip.

- **Items.md** uses **fixed record-relative offsets** for every
  overlay field. The shop-display strings sit in fixed-width slots
  ahead of the overlay block, so MinToKeep / MaxToGet / Options /
  Extended-Options always land at the same offsets within each record.
  The decoder just reads bytes at known positions.

Items.md is therefore **easier to decode** than Monsters.md once the
field offsets are known — no anchor-scanning needed.

## Things NOT yet figured out (Monsters.md)

- **Group** — dialog string (e.g. "Slums, Sewers" / "Graveyard Crypt").
  Likely derived from room/lair table joins, not stored per-monster.
- ~~**Death spell rendered as text**~~ — **resolved** by
  `decode_spells_md.py`. `decode_monsters_md.py --spells Spells.md` now
  labels `DeathSpell` / `CreateSpell` / `MidSpells` /
  `Attacks[].HitSpell` as `"name (number)"` — hanging tree's death
  spell renders `tree (1122)`, matching the dialog exactly. 1314 / 1314
  references resolve across the Paradigm `Monsters.md`.
- **Location** — dialog "Map X, Room Y" — derived from room
  population data, not stored in `Monsters.md`.
- **Multi-record sections**: the dialog shows multiple `Attacks:` rows
  (5 slots in the MDB schema: `Att-0` through `Att-4`, each with
  type/min/max/acc/percent/energy/hitspell) and multiple `Casts:` rows
  (5 slots: `MidSpell-0..4`). Layout sub-pattern still TBD — likely
  rel-anchored at some offset past the Abilities block.
- **DropItems** — 10 item-Number slots with drop percentages, not yet
  decoded.
- Priority byte bit `0x02` — set on exactly one record in the stock
  file (#812 `sdfsdfsfs`, a placeholder/test record) with no visible
  UI flag. Treated as deprecated/internal; ignored.
- The 16-byte file header's exact contents — partly identified as a
  save-counter / timestamp region (bytes 0x06–0x18 change on every
  MegaMUD save with no other record-level edits) but the precise
  layout isn't known.
- The marker-byte variations (`0xdb` / `0xdc` / `0xdd`).
- Page-level structure: how the page header (if any) decides which
  slots are live.

## Things NOT yet figured out (Items.md)

- The exact meaning of the low-byte categorization bits (`0x0001`,
  `0x0002` when alone on starter weapons, `0x0008` inside
  `0x000e`/`0x000f` patterns) — they're set in the binary but don't
  drive a visible UI checkbox in stock MegaMUD's dialog. Probably
  engine-internal item-class flags.
- The `0x40` byte at `+0x71` set on many stock items by default —
  static; not driven by any UI Options toggle. Likely another
  engine-internal categorization byte.
- "Auto-equip" Options checkbox — bit position unknown; no stock
  witnesses.

## Tested against

- **MegaMUD 2.0 Beta P1 (Stock)** — `Default/Monsters.md`
  (1099 / 1100 records, 1 orphan with empty name skipped) and
  `Default/Items.md` (1950 / 1950 records).
- **MegaMUD 2.0 Beta P1 (Paradigm)** — same versions of both files,
  plus `Default/Spells.md` (2011 / 2011 records, 0 skipped), validated
  against a `Spells.json` export of the Paradigm 1.9.1 MDB and against
  the Spell Details dialog for 12 spells.
- **Legacy MegaMUD `MONSTERS.md`** — 1737 / 1738 records (one orphan
  empty-name at #84, same in every variant), confirms the decoder is
  format-agnostic across MegaMUD versions.

If you find a MegaMUD distribution where these decoders misread
records, please open an issue with the offending record's WCC No,
expected values from the UI, and what the decoder emitted.

## License

Public domain / Unlicense. Use freely; no warranty.
