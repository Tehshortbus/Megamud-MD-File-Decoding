#!/usr/bin/env python3
"""Decode MegaMUD's proprietary Monsters.md binary file to JSON.

MegaMUD ships per-table .md files (Monsters.md, Items.md, Spells.md,
etc.) as a custom binary format with magic 'MDB2' — NOT Microsoft Jet
DB despite the file extension. MegaMUD does NOT read the MDB sources
at runtime; the .md files are the authoritative store. This script
extracts every per-monster field visible in MegaMUD's Monster/NPC
Details dialog into a JSON document, including the read-only "Other
Info" panel.

Works on both **legacy MegaMUD** and **MegaMUD 2.0 Beta** Monsters.md
files transparently — same record layout, same rel-anchored stat
block offsets, same flag-bit semantics; the only meaningful difference
is that 2.0 Beta added the StopToKillIfAble flag (rel-3 & 0x08), which
older saves leave at 0. No version flag needed — point the script at
either file and it just works.

Fields extracted (with rel-anchored offsets):

  Header / overlay block (the editable left-pane fields):
    Number              header                u16 LE
    Name                header                null-terminated string
    Relationship        rel+0                 u8 enum (Unknown / Friend / Avoid / Enemy / Flee / Hangup)
    Priority            rel-4 upper nibble    u8 enum (First / High / Normal / Low / Last)
    FindFirst           rel-4 & 0x08          bool
    DontBackstab        rel-3 & 0x01          bool
    NotHostile          rel-3 & 0x02          bool
    CheckIfAlive        rel-3 & 0x04          bool
    StopToKillIfAble    rel-3 & 0x08          bool  (new in MegaMUD 2.0 Beta)
    MaxHP               rel+0x14              u16 LE
    Experience          rel+0x6f              u32 LE  (the dialog-displayed total
                                                       — equals JSON.EXP × JSON.ExpMulti
                                                       for monsters loaded from the
                                                       imported MDB)

  Stat block (rel-anchored static record data; read-only "Other Info"
  in the UI but still serialised in the .md). Offsets pinned down by
  cross-referencing every record against an exported Monsters.json
  representation of the MDB tables — 100% match rates across 1100
  stock records unless otherwise noted:

    Sex                 rel+0x0f              u8 enum  (It / Male / Female)
    Level               rel+0x10              u16 LE   (= MDB's HPRegen field;
                                                         dialog labels it Level)
    Energy              rel+0x16              u16 LE
    MagicRes            rel+0x18              u16 LE   (98.5% — 16 outliers)
    FollowPercent       rel+0x1a              u8
    ArmourClass         rel+0x1c              u16 LE   (dialog renders "AC: X/Y"
                                                         where Y is DamageResist)
    DamageResist        rel+0x1e              u16 LE
    EnslaveLevel        rel+0x20              u16 LE   (= CharmLVL in MDB)
    Type                rel+0x24              u8 enum  (Solo / Leader / Follower / Stationary)
    Alignment           rel+0x25              u8 enum  (Good / Evil / Chaotic Evil / Neutral / Lawful Good / Neutral Evil / Lawful Evil)
    GameLimit           rel+0x26              u8
    RegenTime           rel+0x28              u8       (display unit varies — hours / days)
    Weapon              rel+0x5b              u16 LE   (item Number; 0 = none)
    DeathSpell          rel+0x9b              u16 LE   (spell Number; 0 = none)
    CreateSpell         rel+0x9d              u16 LE   (spell Number; 0 = none)
    Undead              rel+0xa4              u8 bool  (No / Yes — any non-zero
                                                         value = Yes; sentinel
                                                         0xFF appears on ~1% of
                                                         records and means Yes)

  Abilities (5 slots — each a {Code, Name, Value} triple). These are
  the dialog's "extra Other Info rows" — NonLiving, SeeHidden,
  Magical, SpellImmu, Resist-Cold, Resist-Fire, etc. — synthesised
  from MajorMUD's canonical ability-code table (mirrored in this
  script as ABILITY_NAMES). Empty slots (code==0) are omitted.

    Abil-N code         rel+0x47, 0x49, 0x4B, 0x4D, 0x4F   5 × u16 LE
    AbilVal-N value     rel+0x51, 0x53, 0x55, 0x57, 0x59   5 × i16 LE (signed)

  Attacks (5 slots — each {Min, Max, Energy, [HitSpell], [Percent]}).
  Renders as the dialog's "Attacks: Min-Max (Percent%) [E:Energy]"
  rows. HitSpell + Percent are only stored for slots 0..2 (the .md
  doesn't carry them for slots 3-4 — JSON exposes them as always-zero
  placeholders). Empty slots (Min == Max == Energy == 0) are omitted.

    AttMin-N        rel+0x7D, 0x7F, 0x81, 0x83, 0x85   5 × u16 LE
    AttMax-N        rel+0x87, 0x89, 0x8B, 0x8D, 0x8F   5 × u16 LE
    AttEnergy-N     rel+0x91, 0x93, 0x95, 0x97, 0x99   5 × u16 LE
    AttHitSpell-N   rel+0xA5, 0xA7, 0xA9               3 × u16 LE (slots 0..2)
    Att%-N          rel+0xAB, 0xAC, 0xAD               3 × u8     (slots 0..2)

  AttType-N (Normal/Spell/Rob) and AttAcc-N (per-attack accuracy)
  appear in the MDB export but don't match anywhere in the .md at any
  offset — likely derived at MDB-export time and not actually stored.
  AttName-N (the "slashes you" / "bites you" strings) are confirmed
  ABSENT from Monsters.md — exhaustive string search returns zero
  hits. They must live in a separate MegaMUD file or come from the
  source MDB.

  MidSpells (5 mid-round spell slots — each {Spell, Percent, Level}).
  These are the engine's mid-round / between-rounds spell procs.
  Spell is a Spells.md Number; rendering as text needs a Spells.md
  decoder. Empty slots (Spell == 0 or 0xFFFF sentinel) are omitted.

    MidSpell-N      rel+0x5D, 0x5F, 0x61, 0x63, 0x65   5 × u16 LE
    MidSpell%-N     rel+0x73, 0x74, 0x75, 0x76, 0x77   5 × u8
    MidSpellLVL-N   rel+0x9F, 0xA0, 0xA1, 0xA2, 0xA3   5 × u8

  Naming note: MegaMUD's dialog uses "Casts:" rows for the Attack
  slots where AttType=Spell (e.g. "plant summon (20% - Lev 100)
  [E:200]" on hanging tree's attack slot 0). Those are spell-typed
  attacks living in the Attacks array, NOT in MidSpells. The two
  surface together in MegaMUD's UI but are structurally separate in
  the .md file.

  DropItems (5 drop slots — each {Item, Percent}). The MDB schema
  exposes 10 fields but only 5 are serialised in the .md (slots 5-9
  are always 0 and aren't stored). Empty slots (Item == 0) are omitted.

    DropItem-N      rel+0x2E, 0x30, 0x32, 0x34, 0x36   5 × u16 LE
    DropItem%-N     rel+0x38, 0x39, 0x3A, 0x3B, 0x3C   5 × u8

See README.md (sibling file) for the reverse-engineered file layout,
the rel-anchored stat-block discovery, the cross-reference validation
methodology, and the dialog-shown-values verification history.

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
import os
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

# Group-role enum (Monsters.Type — what role this monster plays in its
# group composition).
TYPE_NAMES = {
    0: "Solo",
    1: "Leader",
    2: "Follower",
    3: "Stationary",
}

# Alignment enum (Monsters.Align — values 0..6, gaps in MDB enum order):
ALIGNMENT_NAMES = {
    0: "Good",
    1: "Evil",
    2: "Chaotic Evil",
    3: "Neutral",
    4: "Lawful Good",
    5: "Neutral Evil",
    6: "Lawful Evil",
}

# Sex enum — pinned via 3 known-distinct dialog values (giant rat=It,
# drunken brawler=Male, barmaid=Female). Stock distribution: 596 It
# (creatures), 418 Male (humanoid NPCs), 86 Female (priestesses, sages,
# demonesses, etc.).
SEX_NAMES = {
    0: "It",
    1: "Male",
    2: "Female",
}

# Ability code → human-readable name. Mirrors MegaMUD's canonical
# ability-name table verbatim — used to expand each monster's
# Abil-0..4 slots into the readable rows MegaMUD's dialog shows ("NonLiving",
# "Resist-Cold", "SeeHidden", etc.). Codes not in this table render as
# "code{N}" so unknown abilities still surface.
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

# Read-only stat-block field map. Each entry is
# (offset_relative_to_rel_byte, struct_format, enum_table_or_None).
# Offsets pinned down by cross-referencing every record against MMUD
# Explorer's exported Monsters.json (100% match across 1100 stock
# records unless noted in the docstring). Adding a new field here is
# the only thing needed to surface it in the JSON output.
STAT_BLOCK = [
    # name              offset   fmt    enum
    ("Sex",             0x0F,   "<B",  SEX_NAMES),
    # Level == MDB's HPRegen field; same byte. MegaMUD's dialog labels
    # it "Level" because that's what users recognise — the engine
    # internally treats the same value as HP-regen-per-tick.
    ("Level",           0x10,   "<H",  None),
    ("MaxHP",           0x14,   "<H",  None),
    ("Energy",          0x16,   "<H",  None),
    ("MagicRes",        0x18,   "<H",  None),
    ("FollowPercent",   0x1A,   "<B",  None),
    ("ArmourClass",     0x1C,   "<H",  None),
    ("DamageResist",    0x1E,   "<H",  None),
    ("EnslaveLevel",    0x20,   "<H",  None),
    ("Type",            0x24,   "<B",  TYPE_NAMES),
    ("Alignment",       0x25,   "<B",  ALIGNMENT_NAMES),
    ("GameLimit",       0x26,   "<B",  None),
    ("RegenTime",       0x28,   "<B",  None),
    ("Weapon",          0x5B,   "<H",  None),
    ("Experience",      0x6F,   "<I",  None),
    ("DeathSpell",      0x9B,   "<H",  None),
    ("CreateSpell",     0x9D,   "<H",  None),
    # Undead is a 1-of-2 with occasional sentinels (0xFF / 255 appears on
    # 8 stock + 9 legacy records — banshee, hanging tree, etc.). MegaMUD
    # treats any non-zero value as "Yes". Handled inline (not via
    # STAT_BLOCK enum dict) so the fallback is explicit.
    ("Undead",          0xA4,   "<B",  None),
]

# Abil-N slots — 5 (code, value) pairs at consecutive offsets after
# the stat block. Each code looks up into ABILITY_NAMES to produce
# the dialog's "NonLiving / Resist-Cold / SpellImmu / Magical / …"
# rows. AbilVal is signed (resist values can be negative, e.g.
# hanging tree's Resist-Fire = -50).
ABIL_CODE_OFFSETS = [0x47, 0x49, 0x4B, 0x4D, 0x4F]   # 5 × u16 LE
ABIL_VAL_OFFSETS  = [0x51, 0x53, 0x55, 0x57, 0x59]   # 5 × i16 LE

# ----- Multi-record sub-sections -----
# All offsets pinned via JSON cross-reference at 100% match unless noted.

# Attack profile slots (5 attack records). MegaMUD's dialog renders each
# row as "Min-Max (Percent%) [E:Energy]". AttType / AttAcc / AttName are
# in the MDB export but don't appear in the .md at any offset — likely
# derived / computed at MDB-export time. Slot-3 and slot-4 lack
# HitSpell and Percent in the .md (they're effectively always 0 there).
ATTACK_MIN_OFFSETS      = [0x7D, 0x7F, 0x81, 0x83, 0x85]   # 5 × u16 LE
ATTACK_MAX_OFFSETS      = [0x87, 0x89, 0x8B, 0x8D, 0x8F]   # 5 × u16 LE
ATTACK_ENERGY_OFFSETS   = [0x91, 0x93, 0x95, 0x97, 0x99]   # 5 × u16 LE
ATTACK_HITSPELL_OFFSETS = [0xA5, 0xA7, 0xA9]               # 3 × u16 LE (slots 0..2 only)
ATTACK_PERCENT_OFFSETS  = [0xAB, 0xAC, 0xAD]               # 3 × u8     (slots 0..2 only)

# Cast / MidSpell slots (5 spell records). Dialog renders each as
# "spell-name (Percent% - Lev Level) [E:?]". Spell-name lookup needs
# a Spells.md decoder; we emit the Number.
CAST_SPELL_OFFSETS   = [0x5D, 0x5F, 0x61, 0x63, 0x65]      # 5 × u16 LE (spell Number)
CAST_PERCENT_OFFSETS = [0x73, 0x74, 0x75, 0x76, 0x77]      # 5 × u8
CAST_LEVEL_OFFSETS   = [0x9F, 0xA0, 0xA1, 0xA2, 0xA3]      # 5 × u8

# DropItem slots — only 5 in the .md (JSON exposes 10 fields but slots
# 5-9 are always zero and aren't serialised).
DROP_ITEM_OFFSETS    = [0x2E, 0x30, 0x32, 0x34, 0x36]      # 5 × u16 LE (item Number)
DROP_PERCENT_OFFSETS = [0x38, 0x39, 0x3A, 0x3B, 0x3C]      # 5 × u8


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
        # Spell-name reference string (printable ASCII run, null-terminated).
        # Require ≥2 consecutive printable bytes before treating as a string —
        # older Monsters.md files have lone printable bytes (e.g. 0x40 / '@')
        # in unused field slots, and a single-byte heuristic would skip past
        # the real rel byte that follows.
        if 0x20 <= b <= 0x7E and pos + 1 < len(data) and 0x20 <= data[pos + 1] <= 0x7E:
            sr_end = data.find(b"\x00", pos, record_end)
            if sr_end == -1:
                return None
            pos = sr_end + 1
            continue
        pos += 1
    return None


def extract_overlay(data: bytes, marker: int, name_end: int) -> tuple[int, int, int, dict] | None:
    """Returns (rel_byte, priority_byte, flags_byte, stat_block_fields).

    The first three values come from the overlay block (rel / rel-4 /
    rel-3 — the editable left-pane). The fourth is a dict of every
    field listed in <see cref="STAT_BLOCK"/>, with enum codes already
    mapped to their human-readable strings.
    """
    rel_pos = find_rel_byte(data, name_end, marker + 256)
    if rel_pos is None or rel_pos < 4:
        return None
    # Bound check — the furthest stat-block field reads at rel+0xa4 + 1.
    if rel_pos + 0xA8 >= len(data):
        return None
    stats: dict = {}
    for name, off, fmt, enum in STAT_BLOCK:
        raw = struct.unpack_from(fmt, data, rel_pos + off)[0]
        if name == "Undead":
            # Boolean-style with sentinel handling — see STAT_BLOCK comment.
            # MegaMUD treats any non-zero value as "Yes" (banshee, hanging
            # tree, etc. store 255; standard zombies/skeletons store 1).
            stats[name] = "Yes" if raw != 0 else "No"
        elif enum is not None:
            stats[name] = enum.get(raw, raw)
        else:
            stats[name] = raw

    # Abil-0..4 + AbilVal-0..4 → "Abilities" list of {Code, Name, Value}.
    # Only emit slots with a non-zero code (unused slots are noise).
    abilities: list[dict] = []
    for code_off, val_off in zip(ABIL_CODE_OFFSETS, ABIL_VAL_OFFSETS):
        code = struct.unpack_from("<H", data, rel_pos + code_off)[0]
        if code == 0: continue
        val = struct.unpack_from("<h", data, rel_pos + val_off)[0]
        abilities.append({
            "Code":  code,
            "Name":  ABILITY_NAMES.get(code, f"code{code}"),
            "Value": val,
        })
    stats["Abilities"] = abilities

    # Attacks — 5 slots, each {Min, Max, Energy, [HitSpell], [Percent]}.
    # HitSpell + Percent only present for slots 0..2 (the .md doesn't
    # store them for slots 3-4; the JSON has them as always-zero
    # placeholders). Skip slots where Min == Max == 0 (no attack defined).
    attacks: list[dict] = []
    for i in range(5):
        mn = struct.unpack_from("<H", data, rel_pos + ATTACK_MIN_OFFSETS[i])[0]
        mx = struct.unpack_from("<H", data, rel_pos + ATTACK_MAX_OFFSETS[i])[0]
        en = struct.unpack_from("<H", data, rel_pos + ATTACK_ENERGY_OFFSETS[i])[0]
        if mn == 0 and mx == 0 and en == 0: continue
        slot: dict = {"Min": mn, "Max": mx, "Energy": en}
        if i < len(ATTACK_HITSPELL_OFFSETS):
            slot["HitSpell"] = struct.unpack_from("<H", data, rel_pos + ATTACK_HITSPELL_OFFSETS[i])[0]
            slot["Percent"]  = data[rel_pos + ATTACK_PERCENT_OFFSETS[i]]
        attacks.append(slot)
    stats["Attacks"] = attacks

    # MidSpells — 5 mid-round spell slots, each {Spell, Percent, Level}.
    # Spell is a spell Number; 0 and 0xFFFF (65535) are both "unused"
    # sentinels (0 in slot 0 typically, 0xFFFF in slots 1..4 when
    # padded). Skip both.
    # Naming note: MegaMUD's dialog uses "Casts:" rows for Attacks where
    # AttType=Spell — those are spell-typed attacks, NOT MidSpells.
    # MidSpells are the engine's "between rounds" spell procs and are
    # structurally separate in the .md.
    midspells: list[dict] = []
    for i in range(5):
        sp = struct.unpack_from("<H", data, rel_pos + CAST_SPELL_OFFSETS[i])[0]
        if sp == 0 or sp == 0xFFFF: continue
        midspells.append({
            "Spell":   sp,
            "Percent": data[rel_pos + CAST_PERCENT_OFFSETS[i]],
            "Level":   data[rel_pos + CAST_LEVEL_OFFSETS[i]],
        })
    stats["MidSpells"] = midspells

    # DropItems — 5 drop slots, each {Item, Percent}. Skip empty slots.
    drops: list[dict] = []
    for i in range(5):
        it = struct.unpack_from("<H", data, rel_pos + DROP_ITEM_OFFSETS[i])[0]
        if it == 0: continue
        drops.append({
            "Item":    it,
            "Percent": data[rel_pos + DROP_PERCENT_OFFSETS[i]],
        })
    stats["DropItems"] = drops

    return data[rel_pos], data[rel_pos - 4], data[rel_pos - 3], stats


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
        rel_b, pri_b, flg_b, stats = result
        rel_name = RELATIONSHIP_NAMES.get(rel_b)
        if rel_name is None:
            skipped.append((num, name, f"unknown relationship byte 0x{rel_b:02x}"))
            continue
        overlay: dict = {
            "Number":           num,
            "Name":             name,
            "Relationship":     rel_name,
            "Priority":         PRIORITY_NAMES.get(pri_b & 0xF0, "Normal"),
            "FindFirst":        bool(pri_b & 0x08),
            "DontBackstab":     bool(flg_b & 0x01),
            "NotHostile":       bool(flg_b & 0x02),
            "CheckIfAlive":     bool(flg_b & 0x04),
            "StopToKillIfAble": bool(flg_b & 0x08),
        }
        overlay.update(stats)
        # "Defaults" only applies to the editable overlay-block fields;
        # the stat-block values are intrinsic to each monster and never
        # equal across records, so they don't factor into the default
        # check (otherwise every record would emit, defeating compaction).
        is_default = (
            overlay["Relationship"] == "Enemy"
            and overlay["Priority"] == "Normal"
            and not overlay["FindFirst"]
            and not overlay["DontBackstab"]
            and not overlay["NotHostile"]
            and not overlay["CheckIfAlive"]
            and not overlay["StopToKillIfAble"]
        )
        if emit_defaults or not is_default:
            overlays.append(overlay)
    return overlays, skipped


def load_spell_names(path: str) -> dict[int, str]:
    """Build {spell Number: Name} from a Spells.md or a decoded spells.json.

    Accepts either form so you can point at the raw game file or at the
    output of decode_spells_md.py, whichever you have to hand.
    """
    with open(path, "rb") as f:
        magic = f.read(4)

    if magic == b"MDB2":
        # Reuse the sibling decoder's scanner rather than duplicating the
        # Spells.md record layout here.
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        try:
            import decode_spells_md as ds
        except ImportError:
            raise SystemExit(
                "error: --spells was given a Spells.md file but "
                "decode_spells_md.py is not next to this script"
            )
        with open(path, "rb") as f:
            data = f.read()
        return {
            num: ds._string(payload, ds.OFF_NAME, 30)
            for num, payload in ds.scan_records(data).items()
        }

    with open(path) as f:
        rows = json.load(f)
    return {r["Number"]: r["Name"] for r in rows}


def spell_label(number: int, names: dict[int, str]) -> str:
    """Render a spell reference as "name (number)".

    Unresolvable Numbers still surface their id so nothing is silently
    dropped — Monsters.md references spells that a trimmed Spells.md may
    not carry.
    """
    name = names.get(number)
    return f"{name} ({number})" if name else f"unknown ({number})"


def annotate_spell_names(overlays: list[dict], names: dict[int, str]) -> int:
    """Add readable labels to every spell-Number reference. Returns count.

    Touches DeathSpell / CreateSpell, each MidSpells slot, and the
    HitSpell on each Attacks slot — all four are Spells.md Numbers.
    """
    resolved = 0
    for o in overlays:
        for key in ("DeathSpell", "CreateSpell"):
            num = o.get(key)
            if num:
                o[f"{key}Label"] = spell_label(num, names)
                resolved += num in names
        for slot in o.get("MidSpells", []):
            if slot.get("Spell"):
                slot["SpellLabel"] = spell_label(slot["Spell"], names)
                resolved += slot["Spell"] in names
        for slot in o.get("Attacks", []):
            if slot.get("HitSpell"):
                slot["HitSpellLabel"] = spell_label(slot["HitSpell"], names)
                resolved += slot["HitSpell"] in names
    return resolved


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
        "--spells",
        metavar="PATH",
        help="Path to Spells.md (or a decode_spells_md.py JSON). Resolves "
             "DeathSpell / CreateSpell / MidSpells / Attacks[].HitSpell "
             'into readable "name (number)" labels.',
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

    spell_names: dict[int, str] = {}
    if args.spells:
        try:
            spell_names = load_spell_names(args.spells)
        except OSError as e:
            print(f"error: cannot read {args.spells!r}: {e}", file=sys.stderr)
            return 1
        annotate_spell_names(overlays, spell_names)

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
        if args.spells:
            refs = unresolved = 0
            for o in overlays:
                nums = [o.get("DeathSpell"), o.get("CreateSpell")]
                nums += [s["Spell"] for s in o.get("MidSpells", [])]
                nums += [s.get("HitSpell") for s in o.get("Attacks", [])]
                for n in nums:
                    if n:
                        refs += 1
                        unresolved += n not in spell_names
            print(f"spells:   {len(spell_names)} names loaded from {args.spells}")
            print(f"          {refs} spell references, {refs - unresolved} resolved, "
                  f"{unresolved} unknown")
        if overlays:
            rels = Counter(o["Relationship"] for o in overlays)
            pris = Counter(o["Priority"] for o in overlays)
            types = Counter(o["Type"] for o in overlays)
            aligns = Counter(o["Alignment"] for o in overlays)
            print(f"relationships:   {dict(rels.most_common())}")
            print(f"priorities:      {dict(pris.most_common())}")
            print(f"types:           {dict(types.most_common())}")
            print(f"alignments:      {dict(aligns.most_common())}")
            print(f"FindFirst set:    {sum(o['FindFirst'] for o in overlays)}")
            print(f"DontBackstab set: {sum(o['DontBackstab'] for o in overlays)}")
            print(f"NotHostile set:   {sum(o['NotHostile'] for o in overlays)}")
            print(f"CheckIfAlive set: {sum(o['CheckIfAlive'] for o in overlays)}")
            print(f"StopToKillIfAble: {sum(o['StopToKillIfAble'] for o in overlays)} "
                  f"(new flag in MegaMUD 2.0 Beta — packaged files don't set it yet)")
            print(f"Undead = Yes:     {sum(1 for o in overlays if o['Undead'] == 'Yes')}")
            hps = [o["MaxHP"] for o in overlays]
            lvls = [o["Level"] for o in overlays]
            exps = [o["Experience"] for o in overlays]
            print(f"Level range:      {min(lvls)} – {max(lvls)}")
            print(f"MaxHP range:      {min(hps)} – {max(hps)}")
            print(f"Experience range: {min(exps)} – {max(exps)}")
            abil_counts = Counter()
            for o in overlays:
                for a in o["Abilities"]:
                    abil_counts[a["Name"]] += 1
            print(f"Most common ability codes on monsters (top 8):")
            for nm, c in abil_counts.most_common(8):
                print(f"  {nm}: {c}")
        if skipped:
            print(f"\nskipped records:")
            for num, name, why in skipped[:10]:
                print(f"  #{num} {name!r}: {why}")
            if len(skipped) > 10:
                print(f"  ... and {len(skipped) - 10} more")
    return 0


if __name__ == "__main__":
    sys.exit(main())
