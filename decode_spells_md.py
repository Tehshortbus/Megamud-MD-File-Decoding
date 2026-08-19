#!/usr/bin/env python3
"""Decode MegaMUD's proprietary Spells.md binary file to JSON.

Sibling of decode_monsters_md.py / decode_items_md.py — same MDB2 file
family, same record header shape, different per-record payload. This
script extracts the fields surfaced in MegaMUD's "Spell Details" dialog:
the editable Spell box (Name / Code / Minimum level / Required Mana-Kai
/ Type / target checkboxes / Special command) and the read-only
"More Info" pane (Difficulty / Max. level / Energy used / Duration /
Sphere / From item / ability rows).

Unlike Monsters.md (which needs rel-byte anchor scanning) Spells.md is
strictly fixed-layout: every payload field sits at a constant offset
from the record's 0x80 sentinel byte, so decoding is a straight read.
The payload is always exactly 0x9f bytes — the marker byte is
0xa5 + digit-count and the sentinel sits digit-count bytes further in,
so record length varies with the Number's width but the tail does not.

  python3 decode_spells_md.py <input.md> <output.json>

Offsets were pinned by cross-referencing every record against an
exported Spells.json of the source MDB (the same methodology the
README describes for Monsters.md): 20 of the MDB's numeric columns
match at 99.7-100% across the 1994 records the two files share.

See README.md (sibling file) for the full field map and the validation
history.

License: public domain / unlicense — do whatever.
"""
import argparse
import json
import re
import struct
import sys
from collections import Counter


# Same MDB2 family as Monsters.md / Items.md — 0x400-byte pages,
# slot-allocated records, marker header before each record body.
PAGE_SIZE = 0x400

RECORD_MARKER_RE = re.compile(
    rb"[\x00-\xff]\x01([0-9]{1,5})\x00\x00{0,8}\x80",
    re.DOTALL,
)

# Bytes of record payload following the 0x80 sentinel — constant.
PAYLOAD_LEN = 0x9F

# ---------------------------------------------------------------- offsets
# All offsets are relative to the 0x80 sentinel byte. The "MDB" column
# names the matching column in an exported Spells.json; fields with no
# MDB counterpart are MegaMUD's own per-spell overlay.
OFF_NUMBER      = 0x01   # u16 — cross-check against the ASCII digits
OFF_NAME        = 0x03   # 30-byte null-terminated field
OFF_CODE        = 0x21   # 7-byte null-terminated field   MDB: Short
OFF_OVERLAY     = 0x28   # u16 — MegaMUD overlay bitfield (no MDB twin)
OFF_SPECIAL_CMD = 0x2C   # 26-byte null-terminated field (no MDB twin)
OFF_REQ_LEVEL   = 0x55   # u8    MDB: ReqLevel      dialog "Minimum level"
OFF_MAX_INC     = 0x56   # u8    MDB: MaxInc
OFF_MANA_COST   = 0x57   # u16   MDB: ManaCost      dialog "Required Mana/Kai"
OFF_ENERGY_COST = 0x59   # u16   MDB: EnergyCost    dialog "Energy used"
OFF_MIN_BASE    = 0x5B   # i16   MDB: MinBase
OFF_MAX_BASE    = 0x5D   # i16   MDB: MaxBase
OFF_DURATION    = 0x5F   # i16   MDB: Dur           dialog "Duration"
OFF_DIFFICULTY  = 0x61   # i16   MDB: Diff          dialog "Difficulty"
OFF_MDB_TARGETS = 0x63   # u8    MDB: Targets (stock; drives More Info "Effects")
OFF_MAGERY      = 0x64   # u8    MDB: Magery + MageryLVL folded together
OFF_ATT_TYPE    = 0x65   # u8    MDB: AttType       dialog "Sphere"
OFF_ABIL        = 0x66   # 10 x u16, stride 2   MDB: Abil-0 .. Abil-9
OFF_ABIL_VALUE  = 0x7A   # 10 x i16, stride 2   MDB: AbilVal-0 .. AbilVal-9
OFF_CAP         = 0x8E   # u8    MDB: Cap           dialog "Max. level"
OFF_MAX_INC_LVL = 0x8F   # u8    MDB: MaxIncLVLs
OFF_MIN_INC     = 0x90   # u8    MDB: MinInc
OFF_DUR_INC     = 0x91   # u8    MDB: DurInc
OFF_CAST_TYPE   = 0x92   # u8 — cast type, 0 / 1 / 3 (no MDB twin)
OFF_FROM_ITEM   = 0x93   # u16 — Items.md Number of the scroll/item

ABIL_SLOTS = 10

# Unused ability-value slots carry 0x2020 ("  ") left over from the
# space-padded source MDB text columns rather than zero. The exported
# Spells.json shows the same 8224 filler, so this is inherited from the
# MDB, not a MegaMUD artefact.
ABIL_VALUE_FILLER = 0x2020

# The +0x28 word is MegaMUD's per-spell overlay — the same role the
# +0x6E Options word plays in Items.md. It has no counterpart in the
# source MDB (no column matches it at any offset/encoding). Every bit
# below except 0x0001 was confirmed against the Spell Details dialog
# using a controlled set of Targets=Self spells that differ only in the
# low nibble: way of the swan (24), illuminate (26), arrow trap (20),
# wounded (30), plus magic missile (100) and bites (98) for the target
# nibble. All 7 read back exactly.
BIT_ITEM_ACTIVATED  = 0x0001  # only the 16 "use <item>" records set this
BIT_TIMED_DURATION  = 0x0002  # dialog "Timed duration"
BIT_EVIL_IN_COMBAT  = 0x0004  # dialog "Evil in combat"
BIT_CAST_IMMEDIATE  = 0x0008  # mirrors OFF_CAST_TYPE == 3, exactly

# Dialog target checkboxes. Note the bit order is Self / Player /
# Monster / Area — Monster comes before Area, which is NOT the order
# the checkboxes are laid out in the dialog (Self, Player / Area,
# Monster).
TARGET_BITS = [
    (0x0010, "Self"),
    (0x0020, "Player"),
    (0x0040, "Monster"),
    (0x0080, "Area"),
]

# --------------------------------------------------------------- enums
# Dialog "Type" radio grid: Priest 1/2/3, Mage 1/2/3, Druid 1/2/3,
# Bard 1/2/3, Mystic 1, Any. The .md folds the MDB's Magery (class) and
# MageryLVL (circle) columns into this single byte. Cross-tabulating
# (Magery, MageryLVL) against it over 1994 records is fully
# deterministic:
#
#   Magery 0 (none)   -> 0                Magery 3 (Druid)  -> 7/8/9
#   Magery 2 (Priest) -> 1/2/3            Magery 4 (Bard)   -> 10
#   Magery 1 (Mage)   -> 4/5/6            Magery 5 (Mystic) -> 11
#
# (MageryLVL 0 and 1 both map to the circle-1 value.)
#
# CAVEAT: no Bard circle-2/3 spell exists in the corpus, so whether 11
# means "Mystic 1" or "Bard 2" is not decidable from the data alone. If
# the grid is a flat sequential index, Bard would own 10/11/12 and
# Mystic would be 13 — but every Magery=5 (Mystic) record stores 11, so
# the compact reading below is the one consistent with the file.
TYPE_NAMES = {
     0: "Any",
     1: "Priest 1",   2: "Priest 2",   3: "Priest 3",
     4: "Mage 1",     5: "Mage 2",     6: "Mage 3",
     7: "Druid 1",    8: "Druid 2",    9: "Druid 3",
    10: "Bard 1",    11: "Mystic 1",
}

# MDB AttType — the resist/damage school. MegaMUD's More Info pane
# labels this row "Sphere". All seven values confirmed against the
# dialog: frost jet (0), sunbolt (1), stonestrike (2), lightning bolt
# (3), illuminate + magic missile (4), acid jet (5), bites (6).
#
# The names are MegaMUD's own and are NOT the intuitive ones — 1 is
# "Hot" rather than Fire, 2 is "Stone" rather than Earth, and 5 is
# "Water" rather than Acid (acid jet's sphere reads "Water"). They line
# up with the ability table's Resist-* entries: Resist-Cold,
# Resist-Fire, Resist-Stone, Resist-Lightning, Resist-Water.
SPHERE_NAMES = {
    0: "Cold",
    1: "Hot",
    2: "Stone",
    3: "Lightning",
    4: "Normal",
    5: "Water",
    6: "Poison",
}

# More Info "Cast type". Values 0 and 1 both render "Per round"; the 16
# records storing 1 additionally annotate the Max. level row as
# "(always used)" (single dialog witness: #80 bites). Raw value is kept
# in CastTypeCode so the distinction is not lost.
CAST_TYPE_NAMES = {0: "Per round", 1: "Per round", 3: "Immediate"}

# Ability code -> readable name. Mirrors the canonical MajorMUD ability
# table (identical to ABILITY_NAMES in decode_monsters_md.py) — it is
# what turns the dialog's "Illu: +95" More Info rows back into
# structured data. Codes absent from the table render as "code{N}" so
# unknown abilities still surface.
ABILITY_NAMES: dict[int, str] = {
       1: "Damage",     2: "AC",     3: "Resist-Cold",     4: "MaxDamage",
       5: "Resist-Fire",     6: "Enslave",     7: "DR",     8: "DrainLife",
       9: "Shadow",    10: "AC Blur",    11: "AlterEnergyLevel",    12: "Summon",
      13: "Illu",    14: "RoomIllu",    15: "GypsyFortune",    16: "Rinaldo",
      17: "Damage(-MR)",    18: "Heal",    19: "Poison",    20: "CurePoison",
      21: "ImmuPoison",    22: "Accuracy",    23: "AffectsUndeadOnly",    24: "ProtEvil",
      25: "ProtGood",    26: "DetectMagic",    27: "Stealth",    28: "Magical",
      29: "Punch",    30: "Kick",    31: "Bash",    32: "Smash",
      33: "Killblow",    34: "Dodge",    35: "JumpKick",    36: "M.R.",
      37: "Picklocks",    38: "Tracking",    39: "Thievery",    40: "FindTraps",
      41: "DisarmTraps",    42: "LearnSp",    43: "CastsSp",    44: "Intel",
      45: "Wisdom",    46: "Strength",    47: "Health",    48: "Agility",
      49: "Charm",    50: "MageBaneQuest",    51: "AntiMagic",    52: "EvilInCombat",
      53: "BlindingLight",    54: "IlluTarget",    55: "AlterLightDuration",    56: "RechargeItem",
      57: "SeeHidden",    58: "Crits",    59: "ClassOk",    60: "Fear",
      61: "AffectExit",    62: "AlterEvilChance",    63: "AlterExperience",    64: "AddCP",
      65: "Resist-Stone",    66: "Resist-Lightning",    67: "Quickness",    68: "Slowness",
      69: "MaxMana",    70: "Spellcasting",    71: "Confusion",    72: "ShockShield",
      73: "DispellMagic",    74: "HoldPerson",    75: "Paralyze",    76: "Mute",
      77: "Perception",    78: "Animal",    79: "MageBind",    80: "AffectsAnimalsOnly",
      81: "Freedom",    82: "Cursed",    83: "CursedMajor",    84: "RemoveCurse",
      85: "Shatter",    86: "Quality",    87: "Speed",    88: "MaxHP",
      89: "PunchAcc",    90: "KickAcc",    91: "JumpKAcc",    92: "PunchDmg",
      93: "KickDmg",    94: "JumpKDmg",    95: "Slay",    96: "Encum%",
      97: "GoodOnly",    98: "EvilOnly",    99: "AlterDRpercent",   100: "LoyalItem",
     101: "ConfuseMsg",   102: "RaceStealth",   103: "ClassStealth",   104: "DefenseModifier",
     105: "Accuracy2",   106: "Accuracy3",   107: "BlindUser",   108: "AffectsLivingOnly",
     109: "NonLiving",   110: "NotGood",   111: "NotEvil",   112: "NeutralOnly",
     113: "NotNeutral",   114: "%Spell",   115: "DescMsg",   116: "BSAccu",
     117: "BsMinDmg",   118: "BsMaxDmg",   119: "Del@Maint",   120: "StartMsg",
     121: "Recharge",   122: "RemovesSpell",   123: "HPRegen",   124: "NegateAbility",
     125: "IceSorcQuest",   126: "GoodQuest",   127: "NeutralQuest",   128: "EvilQuest",
     129: "DarkDruidQuest",   130: "BloodChampQuest",   131: "SheDragonQuest",   132: "WereratQuest",
     133: "PhoenixQuest",   134: "DaoLordQuest",   135: "MinLevel",   136: "MaxLevel",
     137: "ShockMsg",   138: "RoomVisible",   139: "SpellImmu",   140: "TeleportRoom",
     141: "TeleportMap",   142: "HitMagic",   143: "ClearItem",   144: "NonMagicalSpell",
     145: "ManaRgn",   146: "MonsGuards",   147: "Resist-Water",   148: "TextBlock",
     149: "Remove@Maint",   150: "HealMana",   151: "EndCast",   152: "Rune",
     153: "KillSpell",   154: "Visible@Maint",   155: "DeathText",   156: "QuestItem",
     157: "ScatterItems",   158: "ReqToHit",   159: "KaiBind",   160: "GiveTempSpell",
     161: "OpenDoor",   162: "Lore",   163: "SpellComponent",   164: "EndCast%",
     165: "AlterSpDmg",   166: "AlterSpLength",   167: "UnEquipItem",   168: "EquipItem",
     169: "CannotWearLocation",   170: "Sleep",   171: "Invisibility",   172: "SeeInvisible",
     173: "Scry",   174: "StealMana",   175: "StealHPtoMP",   176: "StealMPtoHP",
     177: "SpellColours",   178: "Shadowform",   179: "FindTrapsValue",   180: "PickLocksValue",
     181: "GHouseDeed",   182: "GHouseTax",   183: "GHouseItem",   184: "GShopItem",
     185: "NoAttackIfItemNum",   186: "PerfectStealth",   187: "Meditate",   188: "Unique Pool",
     189: "Witchy Badges",   190: "No Stock",   200: "Mandos Quest",   201: "Volums Quest",
     202: "CartographerQuest",   203: "LoremasterQuest",   204: "GuildmasterQuest",   205: "DarkbaneQuest",
     206: "GrizzledRanger",   207: "AmazonHuntress",   208: "Conquest1",   209: "Conquest2",
     210: "TarlChain",   211: "MerchantCaptain",   212: "TrendelQuest",   213: "LucaProdigio",
     214: "EtherealWatcher",   215: "KatoQuest",   216: "GoodCheck",   217: "NeutralCheck",
     218: "EvilCheck",   220: "NagaQuest",   221: "DreadWraith",   222: "CourtesanQuest",
    1001: "GrantThievery",  1002: "GrantTraps",  1003: "GrantPicklocks",  1004: "GrantTracking",
    1100: "AntiMagicNotOK",  1101: "MeetsReqToHit",  1103: "ShadowRest",  1104: "AlterSpellHeal",
    1105: "AlterSpells",  1106: "AlterSpellBuffs",  1107: "NoAutoLearn",  1108: "NotForPVP",
    1109: "Enchant",  1110: "BSDR",  1111: "Absorb",  1112: "Patrol",
    1113: "VileWard",  1114: "CastOnKill%",  1115: "NoFirstKillDrop",  1116: "AccountVerified",
    1117: "NotSellable",  1118: "NoRandomRegen",  1119: "Del@Ganghouse",
}


def ability_name(code: int) -> str:
    return ABILITY_NAMES.get(code, f"code{code}")


def _string(payload: bytes, off: int, width: int) -> str:
    """Read a fixed-width, null-terminated, space-padded field."""
    raw = payload[off : off + width].split(b"\x00", 1)[0]
    return raw.decode("latin-1", errors="replace").strip()


def scan_records(data: bytes) -> dict[int, bytes]:
    """Find every record by header marker. Returns {Number: payload}.

    The payload is the fixed-length PAYLOAD_LEN run starting at the
    record's 0x80 sentinel. Duplicate Numbers keep the first occurrence.
    """
    out: dict[int, bytes] = {}
    for m in RECORD_MARKER_RE.finditer(data, PAGE_SIZE):
        anchor = m.end() - 1  # the 0x80 sentinel
        if anchor + PAYLOAD_LEN > len(data):
            continue
        num = struct.unpack_from("<H", data, anchor + OFF_NUMBER)[0]
        if num != int(m.group(1)):
            continue
        # Name must terminate inside its field, else this is a false match.
        name_end = data.find(b"\x00", anchor + OFF_NAME)
        if name_end == -1 or name_end - (anchor + OFF_NAME) > 30:
            continue
        out.setdefault(num, data[anchor : anchor + PAYLOAD_LEN])
    return out


def extract_abilities(p: bytes) -> list[dict]:
    """Expand the 10 ability slots into {Slot, Code, Name, Value} rows.

    Slots whose code is 0 are dropped; the matching value word is left
    as 0x2020 filler in that case and must not leak into output.

    Slot 0 is the spell's primary effect. MegaMUD renders its dialog row
    using MinBase..MaxBase rather than AbilVal-0 (illuminate: Abil-0 =
    13 "Illu", AbilVal-0 = 0, MinBase = MaxBase = 95, dialog shows
    "Illu: +95"), so consumers should prefer MinBase/MaxBase for slot 0.
    """
    rows = []
    for k in range(ABIL_SLOTS):
        code = struct.unpack_from("<H", p, OFF_ABIL + 2 * k)[0]
        if code == 0:
            continue
        value = struct.unpack_from("<h", p, OFF_ABIL_VALUE + 2 * k)[0]
        if (value & 0xFFFF) == ABIL_VALUE_FILLER:
            value = 0
        rows.append({"Slot": k, "Code": code, "Name": ability_name(code), "Value": value})
    return rows


def decode_record(num: int, p: bytes) -> dict:
    u8 = lambda o: p[o]
    u16 = lambda o: struct.unpack_from("<H", p, o)[0]
    i16 = lambda o: struct.unpack_from("<h", p, o)[0]

    magery = u8(OFF_MAGERY)
    sphere = u8(OFF_ATT_TYPE)
    overlay = u16(OFF_OVERLAY)
    cast_type = u8(OFF_CAST_TYPE)

    return {
        "Number":         num,
        "Name":           _string(p, OFF_NAME, 30),
        "Code":           _string(p, OFF_CODE, 7),
        # --- editable Spell box ---
        "MinLevel":       u8(OFF_REQ_LEVEL),
        "Mana":           u16(OFF_MANA_COST),
        "Type":           TYPE_NAMES.get(magery, f"type{magery}"),
        "TypeCode":       magery,
        "Targets":        [name for bit, name in TARGET_BITS if overlay & bit],
        "TimedDuration":  bool(overlay & BIT_TIMED_DURATION),
        "EvilInCombat":   bool(overlay & BIT_EVIL_IN_COMBAT),
        "ItemActivated":  bool(overlay & BIT_ITEM_ACTIVATED),
        "SpecialCommand": _string(p, OFF_SPECIAL_CMD, 26),
        # --- read-only More Info pane ---
        "Difficulty":     i16(OFF_DIFFICULTY),
        "MaxLevel":       u8(OFF_CAP),
        "Energy":         u16(OFF_ENERGY_COST),
        "Duration":       i16(OFF_DURATION),
        "CastType":       CAST_TYPE_NAMES.get(cast_type, f"cast{cast_type}"),
        "CastTypeCode":   cast_type,
        "Sphere":         SPHERE_NAMES.get(sphere, f"sphere{sphere}"),
        "FromItem":       u16(OFF_FROM_ITEM),
        "MdbTargets":     u8(OFF_MDB_TARGETS),
        "MinBase":        i16(OFF_MIN_BASE),
        "MaxBase":        i16(OFF_MAX_BASE),
        # per-level scaling (MDB MaxInc / MaxIncLVLs / MinInc / DurInc)
        "Scaling": {
            "MaxInc":       u8(OFF_MAX_INC),
            "MaxIncLevels": u8(OFF_MAX_INC_LVL),
            "MinInc":       u8(OFF_MIN_INC),
            "DurInc":       u8(OFF_DUR_INC),
        },
        "Abilities":      extract_abilities(p),
        # raw overlay word, kept so nothing is lost round-tripping
        "Unknown": {"Overlay@0x28": overlay},
    }


def decode(data: bytes, keep_unknown: bool = False) -> tuple[list[dict], list[tuple[int, str]]]:
    records = scan_records(data)
    spells: list[dict] = []
    skipped: list[tuple[int, str]] = []
    for num in sorted(records):
        rec = decode_record(num, records[num])
        if not rec["Name"]:
            skipped.append((num, "empty name"))
            continue
        if not keep_unknown:
            del rec["Unknown"]
        spells.append(rec)
    return spells, skipped


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Decode MegaMUD Spells.md to JSON.",
        epilog="See README.md for the file-format reverse-engineering notes.",
    )
    ap.add_argument("input",  help="Path to MegaMUD Spells.md file (MDB2 format)")
    ap.add_argument("output", help="Path to write JSON output")
    ap.add_argument(
        "--keep-unknown",
        action="store_true",
        help="Include the two not-yet-identified overlay bytes under an 'Unknown' key",
    )
    ap.add_argument("--quiet", action="store_true", help="Suppress the summary")
    args = ap.parse_args()

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

    spells, skipped = decode(data, keep_unknown=args.keep_unknown)

    try:
        with open(args.output, "w") as f:
            json.dump(spells, f, indent=2)
    except OSError as e:
        print(f"error: cannot write {args.output!r}: {e}", file=sys.stderr)
        return 1

    if not args.quiet:
        print(f"input:   {args.input}")
        print(f"output:  {args.output}")
        print(f"records: {len(spells)} emitted, {len(skipped)} skipped")
        types = Counter(s["Type"] for s in spells)
        print("type distribution: " + ", ".join(f"{k}={v}" for k, v in types.most_common()))
        spheres = Counter(s["Sphere"] for s in spells)
        print("sphere distribution: " + ", ".join(f"{k}={v}" for k, v in spheres.most_common()))
        print(f"with FromItem:   {sum(1 for s in spells if s['FromItem'])}")
        print(f"with abilities:  {sum(1 for s in spells if s['Abilities'])}")
        print(f"with spec. cmd:  {sum(1 for s in spells if s['SpecialCommand'])}")
        for num, why in skipped[:10]:
            print(f"  skipped #{num}: {why}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
