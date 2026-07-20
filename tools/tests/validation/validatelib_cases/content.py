"""Phase ownership, prose, metadata, and title regression cases."""

import tempfile
from pathlib import Path

from validatelib import err, set_build_phase, warn
from validatelib.content import check_content, check_section, is_shouting_title
from validatelib.content.depth import check_taught_before_used, check_verbatim_prose
from validatelib.content.structure import check_meta, check_placeholders

from .support import findings


def run_content_cases():
    # Harness phases promote only obligations already owned by that phase. Future
    # work stays a warning; host-only advisories never become errors.
    set_build_phase(3)
    warn("content", "section debt", phase=3)
    warn("content", "future attack debt", phase=4)
    warn("advisory", "host limitation", phase=2)
    got = findings()
    assert [level for level, _, _ in got] == ["ERROR", "WARN", "WARN"], got
    err("content", "future hard contract", phase=6)
    assert findings()[0][0] == "WARN"
    set_build_phase(6)
    err("content", "now-owned hard contract", phase=6)
    assert findings()[0][0] == "ERROR"
    set_build_phase(None)

    set_build_phase(3)
    check_content({}, [{"id": "s01", "lessons": [{
        "id": "s01-l01", "body": "word " * 220, "readings": [],
    }]}], "tome.toml", include_manifest=False)
    got = findings()
    assert any(level == "ERROR" and "median lesson body" in message
               for level, _, message in got), got
    assert any("canonical math strips HTML tags" in message
               and "raise at least 1" in message and "s01/s01-l01=220" in message
               for _, _, message in got), got
    assert any(level == "ERROR" and "zero [[lessons.readings]]" in message
               for level, _, message in got), got
    set_build_phase(None)

    callback_sections = [
        {"id": "s01", "lessons": [{"id": "l01", "body": "Use player_speed.",
                                      "exercises": []}]},
        {"id": "s02", "lessons": [{"id": "l01", "body": "Track max_health.",
                                      "exercises": []}]},
        {"id": "s03", "lessons": [{"id": "l01", "body": "Add enemy_hp.",
                                      "exercises": [{"type": "text", "answer": "enemy_hp"}]}]},
    ]
    check_taught_before_used(callback_sections)
    got = findings()
    assert any("player_speed (s01)" in message and "capability slug" in message
               for _, _, message in got), got

    # TODO is valid in student starter code, but not in authored prose beside it.
    with tempfile.TemporaryDirectory() as directory:
        placeholder_path = Path(directory) / "section.toml"
        placeholder_path.write_text(
            'body = "Finished teaching prose"\nstarter = "# TODO: student writes this"\n',
            encoding="utf-8")
        check_placeholders([str(placeholder_path)])
        assert not findings(), "intentional student TODO was mistaken for author scaffolding"
        placeholder_path.write_text(
            'body = "TODO: author still owes this"\nstarter = "# TODO: student writes this"\n',
            encoding="utf-8")
        check_placeholders([str(placeholder_path)])
        assert any("placeholder" in msg for _, _, msg in findings())

    # Repeated cumulative source is expected in an evolving project and is not copied
    # prose. Actual repeated teaching prose must still trip the 14-word shingle gate.
    repeated_code = " ".join(f"token{i}" for i in range(20))
    prose_a = "This first explanation is deliberately unique and teaches the opening concept clearly."
    prose_b = "This second explanation takes a different route and teaches the later concept clearly."
    sections = [{"id": "s01", "lessons": [
        {"id": "s01-l01", "body": f"<p>{prose_a}</p><pre><code>{repeated_code}</code></pre>"},
        {"id": "s01-l02", "body": f"<p>{prose_b}</p><pre><code>{repeated_code}</code></pre>"},
    ]}]
    check_verbatim_prose(sections)
    assert not findings(), "repeated cumulative code was misclassified as copied prose"
    copied = "Every careful learner should receive a distinct explanation before applying the new idea in their project today"
    sections[0]["lessons"][0]["body"] = f"<p>{copied}.</p>"
    sections[0]["lessons"][1]["body"] = f"<p>{copied} again.</p>"
    check_verbatim_prose(sections)
    got = findings()
    assert any(label == "anti-template" and "repeat verbatim" in msg
               for _, label, msg in got), got

    # Catalog descriptions sell the artifact positively; scope cuts stay in the plan.
    meta = {"id": "test", "name": "Test", "description":
            "Build a working game. The course stops short of multiplayer.",
            "author": "The Arcanum", "version": "0.1.0", "favicon": "*"}
    check_meta({"meta": meta}, "tome.toml")
    got = findings()
    assert any(lv == "WARN" and "public shelf copy" in msg for lv, _, msg in got), got
    meta["description"] = "Build a working game. The course stops at local play: no networking."
    check_meta({"meta": meta}, "tome.toml")
    got = findings()
    assert any(lv == "WARN" and "public shelf copy" in msg for lv, _, msg in got), got
    meta["description"] = "Build a working single-player game with maps and combat."
    check_meta({"meta": meta}, "tome.toml")
    assert not findings(), "positive catalog description was falsely flagged"

    # Display titles share one casing contract: prose titles use Title Case while
    # short acronyms remain legal. This guards both section and lesson callers.
    assert is_shouting_title("TEMPERING III // STOP THE CLOCK")
    assert not is_shouting_title("Tempering III // Stop the Clock")
    assert not is_shouting_title("JSON")
    section = {"id": "s01", "codename": "CHAPTER I // TEST", "title": "Test Chapter",
               "build": "Build", "brief": "Brief", "freestyle": None,
               "lessons": [{"id": "s01-l01", "title": "TEMPERING I // ONE FOREMAN",
                            "body": "<p>Body</p>", "exercises": []}]}
    check_section(section, "s01", "s01", set(), set())
    got = findings()
    assert any(lv == "WARN" and label == "content" and "lesson 's01-l01'" in msg
               and "ALL CAPS" in msg for lv, label, msg in got), got
