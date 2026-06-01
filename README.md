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
| `Monsters.md` | [`decode_monsters_md.py`](decode_monsters_md.py) | ✅ working — overlay block + MaxHP + Experience + StopToKillIfAble; 1099 / 1100 records from MegaMUD 2.0 Beta P1 stock, 1737 / 1738 from legacy MegaMUD (one orphan empty-name in each); format-agnostic |
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
left-pane controls plus the user-set checkboxes) AND the rel-anchored
stat-block fields the dialog displays as read-only "Other Info":

```json
{
  "Number":           2,
  "Name":             "lashworm",
  "Relationship":     "Enemy",
  "Priority":         "Normal",
  "FindFirst":        false,
  "DontBackstab":     false,
  "NotHostile":       false,
  "CheckIfAlive":     false,
  "StopToKillIfAble": true,
  "MaxHP":            15,
  "Experience":       12
}
```

| Field | Type | Values |
|---|---|---|
| `Number` | int | MegaMUD monster ID (1..N) |
| `Name` | string | Display name |
| `Relationship` | string | `Unknown` / `Friend` / `Avoid` / `Enemy` / `Flee` / `Hangup` |
| `Priority` | string | `First` / `High` / `Normal` / `Low` / `Last` |
| `FindFirst` | bool | "Find first" Options checkbox |
| `DontBackstab` | bool | "Don't backstab" Options checkbox |
| `NotHostile` | bool | "Not hostile" Options checkbox |
| `CheckIfAlive` | bool | "Check if alive" Options checkbox |
| `StopToKillIfAble` | bool | "Stop to kill if able" Options checkbox (MegaMUD 2.0 Beta+ — confirmed via single-flag edit-diff on lashworm; older files / unmodified beta files leave this 0) |
| `MaxHP` | int | Maximum HP — `u16 LE` at `rel + 0x14` |
| `Experience` | int | Experience awarded on kill — `u32 BE` at `rel + 0x6c` (high-end monsters legitimately give 16M+; the byte at rel+0x6c carries the high octet for those) |

The decoder works transparently on both legacy MegaMUD and MegaMUD 2.0
Beta `Monsters.md` files — same record layout, same rel-anchored stat
block offsets, same flag-bit semantics. No version flag needed.

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
"Other Info" box — lives at fixed offsets after the rel byte:

| Offset (relative to rel byte) | Field | Type | Notes |
|---|---|---|---|
| `rel + 0x14` | MaxHP | u16 LE | Editable in the dialog; verified across 4+ stock monsters. |
| `rel + 0x6c` | Experience | u32 **BE** | Editable in the dialog. Big-endian inside an otherwise LE file — unusual but consistent. Top-tier monsters legitimately give 16M+ (Kai Master, dread planewalker, etc.). |

The dialog's other right-pane fields (Energy, MagicRes, Accuracy,
EnslaveLevel, Sex, Alignment, Type, Group, Animal, Attacks) all live
in this same rel-anchored block at observed-stable offsets between
`rel + 0x16` and `rel + 0x50`-ish, but aren't extracted by the current
decoder — MegaMUD treats them as read-only display data, so they're
unlikely to ever differ from the realm's source data and there's no
consumer that needs them. Trivial to add if a use case appears.

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
| Lashworm baseline read | — | MaxHP=15, Exp=12 | rel+0x14 u16 LE / rel+0x6c u32 BE | **MaxHP** / **Experience** field offsets confirmed against the dialog values |

**Cross-version validation**: the same decoder runs cleanly against a
legacy MegaMUD `MONSTERS.md` (827 KB, 1738 records, originally
parsed at only 80% accuracy with the initial heuristic) once the
spell-name-reference detection was tightened to require ≥2 consecutive
printable bytes. Both legacy and beta files now decode at 99.9%
accuracy (skipping only the known empty-name orphan at #84). Lashworm
in the legacy file: `Enemy / Normal / DontBackstab / MaxHP=15 / Exp=12`
— stat-block values identical to the beta file (as expected, since
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
- The rel-anchored stat-block offsets for the dialog's read-only
  "Other Info" fields (Energy, MagicRes, Accuracy, EnslaveLevel, Sex,
  Alignment, Type, Group, Animal, Attacks) — observed-stable values
  exist between `rel + 0x16` and `rel + 0x50`-ish but precise field
  positions haven't been pinned down. Easy edit-diff work for whoever
  wants them.

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
