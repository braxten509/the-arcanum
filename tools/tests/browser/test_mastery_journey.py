#!/usr/bin/env python3
"""Real-browser journey through learning, Workings, mastery labs, and the ledger."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from urllib.request import urlopen

from playwright.sync_api import Page, expect, sync_playwright


ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]

from tools.tests.browser.mastery_fixture import (
    LEGACY_TOME_ID, TOME_ID, _install, _remove,
)


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@contextmanager
def _server():
    port = _free_port()
    env = {**os.environ, "ARCANUM_NO_OPEN": "1"}
    process = subprocess.Popen(
        [sys.executable, "server.py", str(port)], cwd=ROOT, env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT, start_new_session=True)
    base_url = f"http://127.0.0.1:{port}"
    try:
        for _ in range(100):
            if process.poll() is not None:
                raise RuntimeError("the disposable browser server exited during startup")
            try:
                with urlopen(base_url + "/api/health", timeout=0.25) as response:
                    if response.status == 200:
                        break
            except OSError:
                time.sleep(0.05)
        else:
            raise RuntimeError("the disposable browser server did not become healthy")
        yield base_url
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def _shot(page: Page, artifacts: Path, name: str) -> None:
    page.screenshot(path=str(artifacts / name), full_page=True)


def _set_monaco(page: Page, host: str, source: str) -> None:
    """Type into the editor and make sure the workspace load does not undo it.

    The bench paints its Monaco surface before `/api/workspace` resolves, and the
    response attaches a fresh model holding the file already on disk. Writing
    once into whatever model is mounted at that instant reads back correctly and
    is then silently replaced -- the submit that follows grades the saved
    `print("READY")` instead of the text this test just set, so the run fails
    roughly half the time. Write, let the pending load land, and write again if
    it clobbered us.
    """
    editor_surface = page.locator(f"{host} .monaco-editor")
    expect(editor_surface).to_be_visible(timeout=20_000)
    script = """({host, source}) => {
      const root = document.querySelector(host);
      const editor = monaco.editor.getEditors().find(
        candidate => root.contains(candidate.getDomNode()));
      if (!editor) return null;
      if (source !== null) editor.setValue(source);
      return editor.getValue();
    }"""
    # Settle first, write once. Writing repeatedly until it sticks also works,
    # but every setValue fires onDidChangeContent -> scheduleDiagnostics, and
    # cancelling those in-flight requests floods the console with Monaco's
    # "Canceled" error, which this test treats as a page failure.
    previous, settled = None, 0
    for _ in range(80):
        current = page.evaluate(script, {"host": host, "source": None})
        settled = settled + 1 if current == previous else 0
        if settled >= 2:
            break
        previous = current
        page.wait_for_timeout(150)
    actual = page.evaluate(script, {"host": host, "source": source})
    assert actual == source, (host, actual)


def _unroll_first_scroll(page: Page, artifacts: Path, screenshot: str | None = None) -> None:
    exercise = page.locator("#view-lesson:not(.hidden) .exercise").first
    exercise.locator(".b-skip").click()
    modal = page.locator("#modal-root .modal")
    expect(modal).to_contain_text("UNROLL A SCROLL OF REVELATION?")
    expect(modal).to_contain_text("Completed with support")
    expect(modal).to_contain_text("does not prove independent capability")
    if screenshot:
        _shot(page, artifacts, screenshot)
    modal.get_by_role("button", name="UNROLL IT", exact=True).click()
    expect(exercise).to_have_class("exercise solved")
    expect(exercise).to_contain_text("Completed with support")
    expect(exercise).to_contain_text("may return later in a varied independent form")


def _working_result(page: Page, passed: bool):
    result = page.locator(".grade-overlay .assessment-result")
    expect(result).to_be_visible(timeout=60_000)
    expect(result).to_have_attribute("data-passed", "true" if passed else "false")
    expect(result).to_contain_text("DETERMINISTIC EVIDENCE")
    return result


def _run_journey(base_url: str, artifacts: Path, browser_name: str) -> None:
    errors: list[str] = []
    with sync_playwright() as playwright:
        if browser_name == "chromium":
            browser = playwright.chromium.launch(
                executable_path="/usr/bin/chromium", headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage"])
        else:
            browser = playwright.firefox.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 1000})
        page = context.new_page()
        page.emulate_media(reduced_motion="reduce")
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on("console", lambda message: errors.append(message.text)
                if message.type == "error" else None)
        page.goto(f"{base_url}/?tome={TOME_ID}", wait_until="domcontentloaded")

        section = page.locator("#view-section:not(.hidden)")
        expect(section.locator("h1")).to_have_text("Evidence Contract 8")
        capability_count = page.evaluate(
            "TOME.masteryEvidence.capabilityIds.length")
        expect(section.locator(".lesson-row .l-pts")).to_contain_text(
            "0/1 resolved · 0/1 independent")
        expect(section.locator(".freestyle-cta")).to_contain_text(
            "Working status: not ready")
        expect(section.locator("#btn-fs")).to_be_disabled()
        _shot(page, artifacts, "01-working-locked.png")

        section.locator(".lesson-row").click()
        _unroll_first_scroll(page, artifacts, "02-scroll-confirmation.png")
        _shot(page, artifacts, "03-supported-completion.png")
        page.locator("#view-lesson:not(.hidden) [data-nav=sec2]").click()
        expect(section.locator(".lesson-row .l-pts")).to_contain_text(
            "1/1 resolved · 0/1 independent")
        expect(section.locator(".freestyle-cta")).to_contain_text("Working status: ready")
        expect(section.locator("#btn-fs")).to_be_enabled()

        section.locator("#btn-fs").click()
        working = page.locator("#view-freestyle:not(.hidden)")
        expect(working.locator(".fs-title")).to_have_text("THE GREAT WORKING: S08")
        _set_monaco(page, "#editor-host", 'print("WRONG")\n')
        working.locator("#b-submit").click()
        failed_working = _working_result(page, False)
        expect(failed_working).to_contain_text("INCOMPLETE")
        expect(failed_working).to_contain_text("FAIL")
        expect(failed_working).to_contain_text("DETERMINISTIC RUBRIC")
        expect(failed_working).not_to_contain_text("QUALITATIVE REVIEW")
        _shot(page, artifacts, "04-working-essential-failure.png")
        page.locator(".grade-overlay #assessment-close").click()
        expect(page.locator(".grade-overlay")).to_have_count(0)

        _set_monaco(page, "#editor-host", 'print("READY")\n')
        working.locator("#b-submit").click()
        passed_working = _working_result(page, True)
        expect(passed_working).to_contain_text("A · 100/100")
        expect(passed_working).to_contain_text("INDEPENDENT EVIDENCE")
        _shot(page, artifacts, "05-working-passed.png")
        page.locator(".grade-overlay #assessment-close").click()
        expect(page.locator(".grade-overlay")).to_have_count(0)

        working.locator("[data-nav=sec]").click()
        page.locator("#ops-list .op-item").nth(8).click()
        expect(section.locator("h1")).to_have_text("Evidence Contract 9")
        expect(section.locator(".freestyle-cta")).to_contain_text(
            "Working status: not ready")
        section.locator(".lesson-row").click()
        _unroll_first_scroll(page, artifacts)
        page.locator("#view-lesson:not(.hidden) [data-nav=sec2]").click()
        expect(section.locator(".freestyle-cta")).to_contain_text("Working status: ready")
        section.locator("#btn-fs").click()
        expect(working.locator(".fs-title")).to_have_text("THE GREAT WORKING: S09")
        rationale = working.locator("#fs-rationale")
        expect(rationale).to_be_visible()
        rationale.fill(
            "The cumulative program intentionally emits the exact observable contract, "
            "and the isolated build plus cold launch verify it from a fresh process.")
        working.locator("#b-submit").click()
        final_working = _working_result(page, True)
        expect(final_working).to_contain_text("INDEPENDENT EVIDENCE")
        page.locator(".grade-overlay #assessment-close").click()
        expect(page.locator(".grade-overlay")).to_have_count(0)

        working.locator("[data-nav=sec]").click()
        section.locator(".crumb [data-nav=home]").click()
        home = page.locator("#view-home:not(.hidden)")
        expect(home.locator(".mastery-state")).to_have_text("learning")
        lab_row = home.locator(".mastery-lab-row")
        expect(lab_row).to_contain_text("BEGIN")
        lab_row.click()

        lab = page.locator("#view-mastery-lab:not(.hidden)")
        expect(lab.locator(".mastery-lab-shell")).to_be_visible(timeout=30_000)
        first_assignment = lab.locator(".lab-assignment code").inner_text()
        expect(lab.locator(".lab-policy")).to_contain_text("cold")
        expect(lab.locator("#lab-oracle")).to_have_count(0)
        expect(lab.locator(".lab-refresh-note")).to_contain_text(
            "Refreshing keeps this exact assignment")
        _shot(page, artifacts, "06-lab-assignment.png")

        page.wait_for_timeout(1_000)
        page.reload(wait_until="domcontentloaded")
        lab = page.locator("#view-mastery-lab:not(.hidden)")
        expect(lab.locator(".mastery-lab-shell")).to_be_visible(timeout=30_000)
        expect(lab.locator(".lab-assignment code")).to_have_text(first_assignment)

        lab.locator("#lab-run").click()
        public_result = lab.locator(".lab-public-result")
        expect(public_result).to_have_attribute("data-passed", "true", timeout=30_000)
        expect(public_result).to_contain_text("PUBLIC CHECKS PASSED")
        lab.locator("#lab-submit").click()
        failed_lab = lab.locator("#lab-output .assessment-result")
        expect(failed_lab).to_be_visible(timeout=60_000)
        expect(failed_lab).to_have_attribute("data-passed", "false")
        expect(failed_lab).to_contain_text("INCOMPLETE")
        _shot(page, artifacts, "07-lab-failed.png")

        lab.locator("#lab-retry").click()
        retry_modal = page.locator("#modal-root .modal")
        expect(retry_modal).to_contain_text("ABANDON THIS VARIANT?")
        retry_modal.get_by_role(
            "button", name="ASSIGN A NEW VARIANT", exact=True).click()
        lab = page.locator("#view-mastery-lab:not(.hidden)")
        expect(lab.locator(".mastery-lab-shell")).to_be_visible(timeout=30_000)
        expect(lab.locator(".lab-assignment code")).not_to_have_text(
            first_assignment, timeout=30_000)
        second_assignment = lab.locator(".lab-assignment code").inner_text()
        assert second_assignment != first_assignment

        brief = lab.locator(
            ".lab-brief-panel > p:not(.lab-refresh-note)").inner_text().strip()
        _set_monaco(page, "#lab-editor-host", f'print("READY {brief}")\n')
        lab.locator("#lab-submit").click()
        passed_lab = lab.locator("#lab-output .assessment-result")
        expect(passed_lab).to_be_visible(timeout=60_000)
        expect(passed_lab).to_have_attribute("data-passed", "true")
        expect(passed_lab).to_contain_text("A · 100/100")
        expect(passed_lab).to_contain_text("INDEPENDENT EVIDENCE")
        _shot(page, artifacts, "08-lab-passed.png")

        lab.locator("#lab-back").click()
        section.locator(".crumb [data-nav=home]").click()
        expect(home.locator(".mastery-state")).to_have_text("provisional")
        expect(home.locator(".mastery-metrics")).to_contain_text(
            f"{capability_count}/{capability_count} demonstrated")
        expect(home.locator(".mastery-lab-row")).to_contain_text("A")
        home.locator(".mastery-ledger").screenshot(
            path=str(artifacts / "09-provisional-ledger.png"))

        export = page.request.get(
            f"{base_url}/api/evidence/export?tome={TOME_ID}")
        assert export.ok
        payload = export.json()
        assert payload["masteryStatus"] == "provisional", payload
        assert len(payload["assessmentReceipts"]) == 3, payload
        assert all("workspaceHash" not in receipt
                   for receipt in payload["assessmentReceipts"].values())

        page.goto(
            f"{base_url}/?tome={LEGACY_TOME_ID}", wait_until="domcontentloaded")
        legacy = page.locator("#view-section:not(.hidden)")
        expect(legacy.locator("h1")).to_have_text("Classic Progression")
        expect(legacy.locator(".lesson-row .l-pts")).to_contain_text("7/10")
        expect(legacy.locator("#btn-fs")).to_be_enabled()
        expect(legacy.locator(".freestyle-cta")).to_contain_text("The scroll awaits")
        expect(legacy.locator(".freestyle-cta")).not_to_contain_text("Working status")
        expect(page.locator(".mastery-ledger")).to_have_count(0)
        expect(page.locator(".section-mastery-labs")).to_have_count(0)
        _shot(page, artifacts, "10-legacy-semantics.png")
        assert not errors, errors
        context.close()
        browser.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--artifacts", type=Path,
        default=ROOT / ".cache" / "mastery-browser-journey")
    parser.add_argument(
        "--browser", choices=("chromium", "firefox"),
        default=os.environ.get("ARCANUM_BROWSER", "chromium"),
        help="browser engine used for the real integration journey")
    args = parser.parse_args()
    args.artifacts.mkdir(parents=True, exist_ok=True)
    _install()
    try:
        with _server() as base_url:
            _run_journey(base_url, args.artifacts, args.browser)
    finally:
        _remove()
    print(f"mastery browser journey ({args.browser}): OK ({args.artifacts})")


if __name__ == "__main__":
    main()
