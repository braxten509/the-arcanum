"""Support package for tools/validate_tome.py. Module map:
- structure  layout contract, placeholders, badges, meta/runtime/narrative/economy/shop
- themes     the 22-ink palette contract + palette distinctness
- content    sections/lessons/exercises, anti-template, density, content-quality gates
- attacks    attack bank, attacks_src sync, hex-defense intrusions
- coverage   capability-ledger ordering and cumulative C# type handoffs
- phase2     one-placeholder-lesson boundary + Phase-0 tooling contract
- phase3     active-section and complete-Arc authored-completion gates
- depth      taught-before-used, verbatim prose, economy totals, static pre-solved tell,
             identifier-spelling drift, self-answering questions
- execute    the --run checks: snippet compilation, starter build/run/pre-solved
Shared constants, the findings registry (err/warn), and small helpers live here."""
import os
import re
import sys

try:
    import tomllib
except ModuleNotFoundError:  # Python < 3.11
    sys.exit("validate_tome.py needs Python 3.11+ (the tomllib module).")

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RUNTIMES_DIR = os.path.join(REPO, "global-configs", "runtimes")
SKINS_DIR = os.path.join(REPO, "skins")

sys.path.insert(0, REPO)  # for tome_layout (shared split-tome layout, in lockstep with server)

# The 22-ink theme contract (tome-authoring/2-tome-toml.md § [[themes]], mirrored in
# the web css's "Theme palettes are injected" vellum block). Every palette
# MUST define exactly these.
THEME_VARS = {
    "bg0", "bg1", "bg2", "bg3", "line", "line-hi",
    "tx", "tx-dim", "tx-faint", "ac", "ac-dim", "ac-bg",
    "warn", "bad", "info", "slab", "slab-tx", "candle",
    "sigil-1", "sigil-2", "sigil-3", "sigil-4",
}
EXERCISE_TYPES = {"mc", "text", "fill", "type", "write"}
# Coin faces a palette may pick (the engine's COIN_ICONS; tome-authoring/2-tome-toml.md § [[themes]])
COIN_FACES = {"star", "rune", "gem", "holed", "serpent", "sun", "bolt", "eye"}
# The six engine consumable mechanics (§ [[shop]]). Any other consumable id
# renders in the shop but does nothing — a WARN, never an ERROR.
CONSUMABLE_IDS = {"firewall", "x2", "skip", "vpn", "xray", "oracle"}
# The five power-ups every tome MUST stock (each reflavored + filled). oracle is an
# optional 6th — it needs a [runtime] oracle model, so it isn't required.
REQUIRED_CONSUMABLES = {"firewall", "x2", "skip", "vpn", "xray"}
# consumables whose strength is the number of charges — a lone charge makes a dud ward.
MULTI_CHARGE = {"firewall", "vpn"}
META_REQUIRED = ["id", "name", "description", "author", "version", "favicon"]
ID_RE = re.compile(r"[A-Za-z0-9_-]+")
# tome-workflow phase 7 runs --strict, and --strict fails on EVERY WARN except the
# "advisory" label — a finished tome carries zero warnings. "advisory" is reserved for
# findings no tome author can fix (an uncalibrated language, a missing toolchain feature);
# everything else, whatever its label, is fixable and therefore gates.
# scaffolding text that must not survive to a finished tome (TODO/FIXME exact-case —
# lowercase "todo" appears in honest prose; lorem any case)
PLACEHOLDER_RE = re.compile(r"\bTODO\b|\bFIXME\b|(?i:lorem ipsum)")

_findings = []  # (level, file_label, msg)


def err(label, msg):
    _findings.append(("ERROR", label, msg))


def warn(label, msg):
    _findings.append(("WARN", label, msg))


def rel(path):
    """Label a path relative to the repo root when possible, else as given."""
    try:
        r = os.path.relpath(path, REPO)
        return r if not r.startswith("..") else path
    except ValueError:
        return path


def load_toml(path):
    """Parse a TOML file. Returns (data, error_message)."""
    try:
        with open(path, "rb") as f:
            return tomllib.load(f), None
    except FileNotFoundError:
        return None, "file not found"
    except tomllib.TOMLDecodeError as e:
        return None, "does not parse as TOML 1.0: " + str(e)
    except OSError as e:
        return None, "could not read: " + str(e)


def norm_lines(s):
    """Engine output normalization: trim line ends, collapse internal whitespace
    runs to one space, drop blank lines. Used for the attack append invariant."""
    out = []
    for line in str(s).splitlines():
        line = " ".join(line.split())
        if line:
            out.append(line)
    return out


def global_skin_ids():
    """Ids of the platform skins under skins/<id>/skin.toml (e.g. vellum)."""
    ids = set()
    try:
        for name in os.listdir(SKINS_DIR):
            if os.path.isfile(os.path.join(SKINS_DIR, name, "skin.toml")):
                ids.add(name)
    except OSError:
        pass
    ids.add("vellum")  # the baseline global skin always exists
    return ids


def runtime_resolves(name):
    """True if global-configs/runtimes/<name>.toml exists (mirrors the engine's
    lang_config lookup in runtimes/__init__.py)."""
    if not name or not ID_RE.fullmatch(name):
        return False
    return os.path.isfile(os.path.join(RUNTIMES_DIR, name + ".toml"))


def lang_config(name):
    """The language TOML's keys, or {} if it is missing/unparseable."""
    if not runtime_resolves(name):
        return {}
    data, _ = load_toml(os.path.join(RUNTIMES_DIR, name + ".toml"))
    return data or {}
