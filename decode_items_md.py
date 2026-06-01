#!/usr/bin/env python3
"""Decode MegaMUD's proprietary Items.md binary file to JSON.

Sibling of decode_monsters_md.py — same MDB2 file family, same record
header shape, different per-record payload. This script extracts the
per-item "overlay" fields (the values surfaced in the Game Item Details
dialog's Item / Options / Details boxes) into a JSON document:

  Number, Name, MinToKeep, MaxToGet, and 9 Options flags:
  AutoCollect, AutoDiscard, AutoFind, AutoOpen, AutoBuy, AutoSell,
  CannotBeTaken, MustHaveMinimum, LoyalItem
  plus CanUseToBackstab (round-tripped for completeness — combat
  systems should consult this flag when picking BS weapons).

See README.md (sibling file) for the reverse-engineered file layout,
the validation history, and the methodology for both decoders.

Usage:
  python3 decode_items_md.py <input.md> <output.json>
  python3 decode_items_md.py --help

Example:
  python3 decode_items_md.py \\
      "MegaMMUD v2.0 Beta P1 (Stock)/Default/Items.md" \\
      items.overlay.json

Tested against:
  MegaMMUD v2.0 Beta P1 (Stock) — 1950 / 1950 items parsed.
  All UI flag positions confirmed via single-flag-edit diffs against
  the stock binary (the methodology described in README.md).

License: public domain / unlicense — do whatever.
"""
import argparse
import json
import re
import struct
import sys
from collections import Counter


# Same MDB2 family as Monsters.md / Spells.md / Rooms.md / etc. —
# 0x400-byte pages, slot-allocated records, marker header before each
# record's body.
PAGE_SIZE = 0x400

RECORD_MARKER_RE = re.compile(
    rb"[\x00-\xff]\x01([0-9]{1,5})\x00\x00{0,8}\x80",
    re.DOTALL,
)


# Record-relative offsets confirmed via the diff methodology
# (see README.md — single-flag toggles against pristine waterskin #283).
OFF_MIN_TO_KEEP = 0x62   # u16 LE — 0 = "None" default
OFF_MAX_TO_GET  = 0x64   # u16 LE — 0 = "All" default
OFF_OPTIONS     = 0x6E   # u16 LE — main Options bitfield
OFF_EXTENDED    = 0x70   # u16 LE — extended Options (Loyal item lives here)


# Bit positions inside the +0x6E Options u16.
BIT_AUTO_COLLECT       = 0x0002
BIT_AUTO_BUY           = 0x0004
BIT_AUTO_SELL          = 0x0008
BIT_AUTO_FIND          = 0x0020
BIT_AUTO_FIND_2        = 0x2000   # alternate Auto-find bit; UI collapses
                                  # both into the same checkbox (rare —
                                  # only ~2 stock items use this form,
                                  # e.g. golden idol / wire key)
BIT_CANNOT_BE_TAKEN    = 0x0040
BIT_CAN_USE_BACKSTAB   = 0x0200
BIT_MUST_HAVE_MINIMUM  = 0x0400
BIT_AUTO_DISCARD       = 0x0800
BIT_AUTO_OPEN          = 0x1000
BIT_CANNOT_BE_TAKEN_2  = 0x4000   # alternate "cannot be taken" bit; UI
                                  # collapses both into the same checkbox

# Bit position inside the +0x70 Extended u16.
BIT_LOYAL_ITEM         = 0x0002


def scan_records(data: bytes) -> dict[int, tuple[int, int, str]]:
    """Find every record by header marker.

    Returns dict mapping item Number → (marker_offset, name_end_offset,
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
        # Name string starts at anchor + 3, runs to the next null.
        # Items can have long-ish names ("scroll of burning aura"); cap
        # at 64 chars to filter pathological matches.
        name_end = data.find(b"\x00", anchor + 3)
        if name_end == -1 or name_end - (anchor + 3) > 64:
            continue
        if num_le not in out:
            name = data[anchor + 3 : name_end].decode("latin-1", errors="replace")
            out[num_le] = (m.start(), name_end, name)
    return out


def extract_overlay(data: bytes, marker: int) -> dict:
    """Read every overlay field at its fixed record-relative offset."""
    min_to_keep = struct.unpack_from("<H", data, marker + OFF_MIN_TO_KEEP)[0]
    max_to_get  = struct.unpack_from("<H", data, marker + OFF_MAX_TO_GET)[0]
    options     = struct.unpack_from("<H", data, marker + OFF_OPTIONS)[0]
    extended    = struct.unpack_from("<H", data, marker + OFF_EXTENDED)[0]

    cannot_be_taken = bool(options & (BIT_CANNOT_BE_TAKEN | BIT_CANNOT_BE_TAKEN_2))
    auto_find       = bool(options & (BIT_AUTO_FIND        | BIT_AUTO_FIND_2))

    return {
        "AutoCollect":      bool(options & BIT_AUTO_COLLECT),
        "AutoDiscard":      bool(options & BIT_AUTO_DISCARD),
        "AutoFind":         auto_find,
        "AutoOpen":         bool(options & BIT_AUTO_OPEN),
        "AutoBuy":          bool(options & BIT_AUTO_BUY),
        "AutoSell":         bool(options & BIT_AUTO_SELL),
        "CannotBeTaken":    cannot_be_taken,
        "MustHaveMinimum":  bool(options & BIT_MUST_HAVE_MINIMUM),
        "LoyalItem":        bool(extended & BIT_LOYAL_ITEM),
        "CanUseToBackstab": bool(options & BIT_CAN_USE_BACKSTAB),
        "MinToKeep":        min_to_keep,
        "MaxToGet":         max_to_get,
    }


def decode(data: bytes, emit_defaults: bool = False) -> tuple[list[dict], list[tuple[int, str, str]]]:
    """Decode every record. Returns (overlays, skipped).

    If emit_defaults is False (default), items whose overlay matches the
    implicit defaults (every flag off, MinToKeep == 0, MaxToGet == 0)
    are omitted to keep the output compact.
    """
    records = scan_records(data)
    overlays: list[dict] = []
    skipped: list[tuple[int, str, str]] = []

    for num in sorted(records):
        marker, _name_end, name = records[num]
        if not name:
            skipped.append((num, name, "empty name"))
            continue
        fields = extract_overlay(data, marker)
        overlay = {
            "Number": num,
            "Name":   name,
            **fields,
        }
        is_default = (
            overlay["MinToKeep"] == 0
            and overlay["MaxToGet"] == 0
            and not overlay["AutoCollect"]   and not overlay["AutoDiscard"]
            and not overlay["AutoFind"]      and not overlay["AutoOpen"]
            and not overlay["AutoBuy"]       and not overlay["AutoSell"]
            and not overlay["CannotBeTaken"] and not overlay["MustHaveMinimum"]
            and not overlay["LoyalItem"]     and not overlay["CanUseToBackstab"]
        )
        if emit_defaults or not is_default:
            overlays.append(overlay)
    return overlays, skipped


def main() -> int:
    p = argparse.ArgumentParser(
        description="Decode MegaMUD Items.md to JSON.",
        epilog="See README.md for the file-format reverse-engineering notes.",
    )
    p.add_argument("input",  help="Path to MegaMUD Items.md file (MDB2 format)")
    p.add_argument("output", help="Path to write JSON output")
    p.add_argument(
        "--emit-defaults",
        action="store_true",
        help="Emit every item (default omits records that match all-off / None / All defaults)",
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
            flag_counts = {
                "AutoCollect":      sum(1 for o in overlays if o["AutoCollect"]),
                "AutoDiscard":      sum(1 for o in overlays if o["AutoDiscard"]),
                "AutoFind":         sum(1 for o in overlays if o["AutoFind"]),
                "AutoOpen":         sum(1 for o in overlays if o["AutoOpen"]),
                "AutoBuy":          sum(1 for o in overlays if o["AutoBuy"]),
                "AutoSell":         sum(1 for o in overlays if o["AutoSell"]),
                "CannotBeTaken":    sum(1 for o in overlays if o["CannotBeTaken"]),
                "MustHaveMinimum":  sum(1 for o in overlays if o["MustHaveMinimum"]),
                "LoyalItem":        sum(1 for o in overlays if o["LoyalItem"]),
                "CanUseToBackstab": sum(1 for o in overlays if o["CanUseToBackstab"]),
            }
            print(f"flag counts:")
            for name, count in flag_counts.items():
                print(f"  {name:<20} {count}")
            min_keep_set = sum(1 for o in overlays if o["MinToKeep"] != 0)
            max_get_set  = sum(1 for o in overlays if o["MaxToGet"]  != 0)
            print(f"MinToKeep non-zero:   {min_keep_set}")
            print(f"MaxToGet  non-zero:   {max_get_set}")
        if skipped:
            print(f"\nskipped records:")
            for num, name, why in skipped[:10]:
                print(f"  #{num} {name!r}: {why}")
            if len(skipped) > 10:
                print(f"  ... and {len(skipped) - 10} more")
    return 0


if __name__ == "__main__":
    sys.exit(main())
