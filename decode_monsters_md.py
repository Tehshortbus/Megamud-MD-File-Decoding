#!/usr/bin/env python3
"""Decode MegaMUD's proprietary Monsters.md binary file to JSON.

MegaMUD ships per-table .md files (Monsters.md, Items.md, Spells.md,
etc.) as a custom binary format with magic 'MDB2' — NOT Microsoft Jet
DB despite the file extension. This script extracts the per-monster
"overlay" fields (the values surfaced in the Monster/NPC Details
dialog) into a JSON document.

Fields extracted:
  Number, Name, Relationship, Priority, FindFirst, DontBackstab,
  NotHostile, CheckIfAlive

See README.md (sibling file) for the reverse-engineered file layout
and the validation history.

Usage:
  python3 decode_monsters_md.py <input.md> <output.json>
  python3 decode_monsters_md.py --help

Example:
  python3 decode_monsters_md.py \
      "MegaMMUD v2.0 Beta P1 (Stock)/Default/Monsters.md" \
      monsters.overlay.json

Tested against:
  MegaMMUD v2.0 Beta P1 (Stock) — 1099 / 1100 monsters parsed
  (1 orphan record with empty name skipped; 13 hand-verified
  monsters all match the MegaMUD UI defaults values).

License: public domain / unlicense — do whatever.
"""
import argparse
import json
import re
import struct
import sys
from collections import Counter


# 'MDB2' magic + 16-byte file header; records begin in the second
# 0x400-byte page at offset 0x400.
PAGE_SIZE = 0x400

# Per-record header marker: arbitrary byte, then 0x01, then the
# record's Number in ASCII digits, then null, then ≤8 zero padding
# bytes, then the 0x80 sentinel. Capture the digits for cross-check
# against the LE u16 that follows.
RECORD_MARKER_RE = re.compile(
    rb"[\x00-\xff]\x01([0-9]{1,5})\x00\x00{0,8}\x80",
    re.DOTALL,
)

# Relationship enum byte (matches MegaMUD UI dropdown order):
RELATIONSHIP_NAMES = {
    1: "Unknown",
    2: "Friend",
    3: "Avoid",
    4: "Enemy",
    5: "Flee",
    6: "Hangup",
}

# Priority enum (upper nibble of the priority byte; mutually exclusive):
PRIORITY_NAMES = {
    0x00: "Normal",
    0x10: "Last",
    0x20: "Low",
    0x40: "High",
    0x80: "First",
}


def scan_records(data: bytes) -> dict[int, tuple[int, int, str]]:
    """Find every record by header marker.

    Returns dict mapping monster Number → (marker_offset, name_end_offset,
    name_string). Skips duplicate Numbers (first occurrence wins).
    """
    out: dict[int, tuple[int, int, str]] = {}
    for m in RECORD_MARKER_RE.finditer(data, PAGE_SIZE):
        anchor = m.end() - 1  # position of the 0x80 sentinel byte
        if anchor + 4 >= len(data):
            continue
        # The 2 bytes after the sentinel are the Number again as u16 LE
        # — cross-check against the ASCII digits to filter false matches.
        num_le = struct.unpack_from("<H", data, anchor + 1)[0]
        if num_le != int(m.group(1)):
            continue
        # Name string starts at anchor + 3 (skip sentinel + u16), runs
        # to the next null. Cap at 64 chars to filter pathological matches.
        name_end = data.find(b"\x00", anchor + 3)
        if name_end == -1 or name_end - (anchor + 3) > 64:
            continue
        if num_le not in out:
            name = data[anchor + 3 : name_end].decode("latin-1", errors="replace")
            out[num_le] = (m.start(), name_end, name)
    return out


def find_rel_byte(data: bytes, name_end: int, record_end: int) -> int | None:
    """Locate the rel byte (overlay-block anchor) within a record.

    The overlay block sits after the name + zero or more null-terminated
    spell-name reference strings + zero padding. The rel byte is the
    last nonzero byte in the overlay block — identified by:

      - value in {0x01..0x06} (one of the 6 relationship enums)
      - followed by ≥4 trailing zero bytes (the overlay block ends here)
      - byte at -4 has a sane priority-enum value (0x00/10/20/40/80 in
        the upper nibble)

    Returns the absolute offset of the rel byte, or None if not found.
    """
    pos = name_end + 1
    while pos < record_end and pos < len(data):
        # Skip zero padding
        while pos < record_end and pos < len(data) and data[pos] == 0:
            pos += 1
        if pos >= record_end or pos >= len(data):
            return None
        b = data[pos]
        if 1 <= b <= 6:
            trailing_ok = (
                pos + 5 < len(data)
                and data[pos + 1] == 0
                and data[pos + 2] == 0
                and data[pos + 3] == 0
                and data[pos + 4] == 0
            )
            if trailing_ok and pos >= 7:
                pri_enum = data[pos - 4] & 0xF0
                if pri_enum in PRIORITY_NAMES:
                    return pos
        # Spell-name reference string (printable ASCII run, null-terminated)
        if 0x20 <= b <= 0x7E:
            sr_end = data.find(b"\x00", pos, record_end)
            if sr_end == -1:
                return None
            pos = sr_end + 1
            continue
        pos += 1
    return None


def extract_overlay(data: bytes, marker: int, name_end: int) -> tuple[int, int, int] | None:
    """Returns (rel_byte, priority_byte, flags_byte) for one record."""
    rel_pos = find_rel_byte(data, name_end, marker + 256)
    if rel_pos is None or rel_pos < 4:
        return None
    return data[rel_pos], data[rel_pos - 4], data[rel_pos - 3]


def decode(data: bytes, emit_defaults: bool = False) -> tuple[list[dict], list[tuple[int, str, str]]]:
    """Decode every record. Returns (overlays, skipped).

    If emit_defaults is False (default), monsters whose overlay matches
    the implicit defaults (Enemy / Normal priority / no flags set) are
    omitted to keep the output compact. Set emit_defaults=True to emit
    a record per monster regardless.
    """
    records = scan_records(data)
    overlays: list[dict] = []
    skipped: list[tuple[int, str, str]] = []

    for num in sorted(records):
        marker, name_end, name = records[num]
        if not name:
            skipped.append((num, name, "empty name"))
            continue
        result = extract_overlay(data, marker, name_end)
        if result is None:
            skipped.append((num, name, "extract failed"))
            continue
        rel_b, pri_b, flg_b = result
        rel_name = RELATIONSHIP_NAMES.get(rel_b)
        if rel_name is None:
            skipped.append((num, name, f"unknown relationship byte 0x{rel_b:02x}"))
            continue
        overlay = {
            "Number":       num,
            "Name":         name,
            "Relationship": rel_name,
            "Priority":     PRIORITY_NAMES.get(pri_b & 0xF0, "Normal"),
            "FindFirst":    bool(pri_b & 0x08),
            "DontBackstab": bool(flg_b & 0x01),
            "NotHostile":   bool(flg_b & 0x02),
            "CheckIfAlive": bool(flg_b & 0x04),
        }
        is_default = (
            overlay["Relationship"] == "Enemy"
            and overlay["Priority"] == "Normal"
            and not overlay["FindFirst"]
            and not overlay["DontBackstab"]
            and not overlay["NotHostile"]
            and not overlay["CheckIfAlive"]
        )
        if emit_defaults or not is_default:
            overlays.append(overlay)
    return overlays, skipped


def main() -> int:
    p = argparse.ArgumentParser(
        description="Decode MegaMUD Monsters.md to JSON.",
        epilog="See README.md for the file-format reverse-engineering notes.",
    )
    p.add_argument("input", help="Path to MegaMUD Monsters.md file (MDB2 format)")
    p.add_argument("output", help="Path to write JSON output")
    p.add_argument(
        "--emit-defaults",
        action="store_true",
        help="Emit every monster (default omits records that match Enemy/Normal/no-flags defaults)",
    )
    p.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress per-distribution summary output",
    )
    args = p.parse_args()

    try:
        with open(args.input, "rb") as f:
            data = f.read()
    except OSError as e:
        print(f"error: cannot read {args.input!r}: {e}", file=sys.stderr)
        return 1

    if data[:4] != b"MDB2":
        print(
            f"error: {args.input!r} does not begin with the 'MDB2' magic "
            f"(got {data[:4]!r}). Not a MegaMUD .md file?",
            file=sys.stderr,
        )
        return 2

    overlays, skipped = decode(data, emit_defaults=args.emit_defaults)

    try:
        with open(args.output, "w") as f:
            json.dump(overlays, f, indent=2)
    except OSError as e:
        print(f"error: cannot write {args.output!r}: {e}", file=sys.stderr)
        return 1

    if not args.quiet:
        print(f"input:    {args.input}")
        print(f"output:   {args.output}")
        print(f"records:  {len(overlays)} emitted, {len(skipped)} skipped")
        if overlays:
            rels = Counter(o["Relationship"] for o in overlays)
            pris = Counter(o["Priority"] for o in overlays)
            print(f"relationships: {dict(rels.most_common())}")
            print(f"priorities:    {dict(pris.most_common())}")
            print(f"FindFirst set:    {sum(o['FindFirst'] for o in overlays)}")
            print(f"DontBackstab set: {sum(o['DontBackstab'] for o in overlays)}")
            print(f"NotHostile set:   {sum(o['NotHostile'] for o in overlays)}")
            print(f"CheckIfAlive set: {sum(o['CheckIfAlive'] for o in overlays)}")
        if skipped:
            print(f"\nskipped records:")
            for num, name, why in skipped[:10]:
                print(f"  #{num} {name!r}: {why}")
            if len(skipped) > 10:
                print(f"  ... and {len(skipped) - 10} more")
    return 0


if __name__ == "__main__":
    sys.exit(main())
