"""Padded prose and authored theme identity regression cases."""

import tempfile
from pathlib import Path
from unittest.mock import patch

from validatelib import set_build_phase
from validatelib.content.depth import check_padded_prose
from validatelib.themes import (check_sigil_palette_uniqueness,
                                check_theme_distinctness)

from .support import findings


def run_theme_cases():
    # 3. padded-prose guard: identical paragraphs in a language with no English glue
    # words must NOT cross-match (the all-'*' skeleton trap).
    para = "<p>" + " ".join(f"palabra{i} misma cosa distinta" for i in range(20)) + "</p>"
    sections = [{"id": "s01", "lessons": [{"id": "a", "body": para},
                                               {"id": "b", "body": para}]}]
    check_padded_prose(sections)
    assert not findings(), "non-English identical paragraphs false-flagged"
    # …while the same trick in English (glue intact) still fires.
    para = ("<p>" + "The ward is set on the line and the rune will hold it there for now. " * 6
            + "</p>")
    sections = [{"id": "s01", "lessons": [{"id": "a", "body": para},
                                               {"id": "b", "body": para}]}]
    check_padded_prose(sections)
    assert any("sentence frames" in msg for _, _, msg in findings()), \
        "English template clone missed"

    # 4. A complete four-ink sigil set may appear only once among authored tome
    # themes. Reordering the same four colors still duplicates the set, while
    # changing any one color clears it. Global skins are not scanned.
    sigil = {f"sigil-{i}": f"#00000{i}" for i in range(1, 5)}
    current = {"themes": [{"id": "ember", "vars": sigil}]}
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory) / "tomes"
        current_dir = root / "current"
        other_dir = root / "other"
        global_dir = Path(directory) / "skins" / "global"
        current_dir.mkdir(parents=True)
        other_dir.mkdir(parents=True)
        global_dir.mkdir(parents=True)
        reordered = [sigil[f"sigil-{i}"] for i in (4, 3, 2, 1)]
        (other_dir / "themes.toml").write_text(
            "[[themes]]\nid = \"echo\"\n\n[themes.vars]\n" +
            "\n".join(f"sigil-{i} = \"{color}\"" for i, color in enumerate(reordered, 1))
            + "\n"
        )
        (global_dir / "skin.toml").write_text(
            "id = \"global\"\n[vars]\n" +
            "\n".join(f"sigil-{i} = \"{sigil[f'sigil-{i}']}\"" for i in range(1, 5)) + "\n"
        )
        check_sigil_palette_uniqueness(current, current_dir, "L", root)
        got = findings()
        assert any(lv == "ERROR" and "other/echo" in msg and "sigil color set" in msg
                   for lv, _, msg in got), got
        assert not any("global/global" in msg for _, _, msg in got), got

        set_build_phase(3)
        check_sigil_palette_uniqueness(current, current_dir, "L", root)
        got = findings()
        assert any(lv == "WARN" and "other/echo" in msg for lv, _, msg in got), got
        set_build_phase(6)
        check_sigil_palette_uniqueness(current, current_dir, "L", root)
        got = findings()
        assert any(lv == "ERROR" and "other/echo" in msg for lv, _, msg in got), got
        set_build_phase(None)

        changed = dict(sigil)
        changed["sigil-4"] = "#000005"
        current = {"themes": [{"id": "ember", "vars": changed}]}
        check_sigil_palette_uniqueness(current, current_dir, "L", root)
        assert not findings(), "one changed sigil ink should make the set unique"

    # A tome's default is its visible identity. A palette barely beyond the
    # optional-variant floor must not ship as a renamed Vellum first impression.
    almost_vellum = {"defaults": {"theme": "signature"}, "themes": [
        {"id": "signature", "vars": {}},
    ]}
    with patch("validatelib.themes._palette_dist", return_value=9.0):
        check_theme_distinctness(almost_vellum, "L")
    got = findings()
    assert any("default mean channel distance 9.0 < 10" in msg for _, _, msg in got), got
