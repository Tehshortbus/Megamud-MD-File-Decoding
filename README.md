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
| `Classes.md`  | —                                                | not yet reversed |
| `Paths.md`    | —                                                | not yet reversed |
| `Races.md`    | —                                                | not yet reversed |
| `Spells.md`   | —                                                | not yet reversed |

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
```

Both scripts share the same CLI shape:

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
- **DeathSpell-as-text** — the `DeathSpell` Number is extracted, but
  rendering the spell name would need a `Spells.md` decoder.

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

### Validation methodology

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

## Combined findings — what's the same across both files

Both Monsters.md and Items.md share:

1. **MDB2 magic** at file offset 0.
2. **1024-byte (0x400) page-allocated** record layout, with records
   slot-packed (not necessarily sorted by Number).
3. **Identical record header** — a marker byte / `0x01` / ASCII Number
   digits / `0x80` sentinel / LE u16 Number cross-check / null-terminated
   Name string.
4. **Variable string-table area after the Name** — Monsters.md uses
   this for spell-name references the monster casts; Items.md uses it
   for shop-display strings. Both are zero-or-more null-terminated
   ASCII strings, terminated by null padding before the overlay block.

The same scanner regex finds every record in either file. Most of the
forward work for the remaining MDB2 files (Classes / Paths / Races /
Spells) is discovering each file's per-record payload, not redoing
the framing.

## Combined findings — what's different

The overlay block's structure varies:

- **Monsters.md** uses **variable-position fields anchored on a rel
  byte** at the end of the overlay block. Records aren't fixed-width
  in their useful portion — the rel byte's position drifts based on
  how many spell-name reference strings the monster has after its
  name. The decoder scans for the rel byte using a heuristic
  (in-range value + extended trailing zeros + sane preceding bytes).

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
- **Death spell rendered as text** — `DeathSpell` field is extracted
  as a Number; the dialog labels it with the spell's name (e.g. "tree"
  for hanging tree). Resolution would require a `Spells.md` decoder.
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
- **MegaMUD 2.0 Beta P1 (Paradigm)** — same versions of both files.
- **Legacy MegaMUD `MONSTERS.md`** — 1737 / 1738 records (one orphan
  empty-name at #84, same in every variant), confirms the decoder is
  format-agnostic across MegaMUD versions.

If you find a MegaMUD distribution where these decoders misread
records, please open an issue with the offending record's WCC No,
expected values from the UI, and what the decoder emitted.

## License

Public domain / Unlicense. Use freely; no warranty.
