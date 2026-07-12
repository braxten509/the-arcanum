/* The Oracle — one question whispered into the crystal, and the notes it leaves behind. */
import { ORACLE_COST, gp, langName, newFileExt } from "../core/config.js";
import { $, esc, ico, modal, sfx } from "../core/dom.js";
import { secById, spend } from "../game/progress.js";
import { S, save } from "../core/state.js";
import { activeFile, ed, models } from "./workbench.js";

// what the operator has highlighted right now: Monaco selection, textarea/input selection, or page text.
// call from pointerdown — by click time the browser has already collapsed document selections.
export function grabSelection() {
  if (S.nav && S.nav.view === "freestyle" && ed && ed.getModel()) {
    const s2 = ed.getSelection();
    if (s2 && !s2.isEmpty()) return ed.getModel().getValueInRange(s2);
  }
  const ae = document.activeElement;
  if (ae && (ae.tagName === "TEXTAREA" || ae.tagName === "INPUT") && ae.selectionStart !== ae.selectionEnd)
    return ae.value.slice(ae.selectionStart, ae.selectionEnd);
  return String(window.getSelection()).trim();
}

// context for a global oracle ask, based on where the operator currently is
export function oracleContext() {
  const nav = S.nav || {};
  const sec = nav.sec && secById(nav.sec);
  let label = "global", detail = `no specific lesson open — general ${langName()} question`;
  if (nav.view === "lesson" && sec) {
    const l = sec.lessons.find((x) => x.id === nav.lesson);
    label = `${sec.codename} / ${l ? l.title : ""}`;
    detail = `${sec.codename} — ${sec.title}` + (l ? ` / lesson: ${l.title}` : "");
  } else if (nav.view === "freestyle" && sec) {
    label = `${sec.codename} / freestyle`;
    detail = `${sec.codename} — ${sec.title} / freestyle build: ${sec.build}`;
    const m = activeFile && models[activeFile];
    if (activeFile && activeFile.endsWith(newFileExt()) && m && !m.isDisposed())
      detail += `\n\nSTUDENT'S CURRENT FILE (${activeFile}):\n${m.getValue()}`;
  } else if (sec) {
    label = sec.codename;
    detail = `${sec.codename} — ${sec.title}`;
  }
  return { label, detail };
}

export function paintOracleBtn() {
  const n = `(${S.inv.oracle || 0})`;
  const hit = $("#obj-orb .obj-hit"); if (hit) hit.title = `Ask the Oracle a question — ${n} left`;
  const ob = $("#b-oracle"); if (ob) ob.innerHTML = `${ico("orb")} CONSULT THE ORACLE ${n}`;
}

export function askOracle(label, detail, selection) {
  if ((S.inv.oracle || 0) < 1) {
    modal(`<h2>WAKE THE ORACLE?</h2>
      <p class="dim">One question whispered into the crystal — an AI spirit dwelling in this very machine (Ollama). Each scrying answers a single question.</p>
      <p>The orb demands: <b class="num">${ORACLE_COST}</b>${gp()} — your purse holds <span class="num">${S.credits}</span>${gp()}.</p>`,
      [["LET IT SLEEP", "quiet"], [`PAY (${ORACLE_COST}${gp()})`, "", () => {
        if (!spend(ORACLE_COST)) return;
        S.inv.oracle = (S.inv.oracle || 0) + 1;
        sfx("peddler"); save(); paintOracleBtn();
        askOracle(label, detail, selection);
      }]]);
    return;
  }
  modal(`<h2>CONSULT THE ORACLE</h2>
    <p class="dim">One question to the spirit in the crystal. Consumes one scrying — you hold ${S.inv.oracle}.</p>
    ${selection ? `<div class="faint" style="font-size:10.5px;letter-spacing:.14em;margin-bottom:4px">THE ORB REFLECTS YOUR SELECTION</div>
    <pre style="max-height:110px;overflow:auto;margin:0 0 10px;padding:8px;border:1px solid var(--line-hi);border-radius:3px;font-family:var(--mono);font-size:12px"><code></code></pre>` : ""}
    <textarea id="oracle-q" rows="3" style="width:100%" placeholder="e.g. why does ReadLine return null? what's the difference between var and int?"></textarea>
    <div id="oracle-a" class="hidden" style="margin-top:12px;padding:12px;border:1px solid var(--line-hi);border-left:2px solid var(--ac-dim);border-radius:3px;font-size:13px;white-space:pre-wrap;max-height:45vh;overflow-y:auto"></div>`,
    [["COVER THE ORB", "quiet"]], { sticky: true });
  if (selection) $("#modal-root pre code").textContent = selection.slice(0, 600);
  const actions = $("#modal-root .modal-actions");
  const askBtn = document.createElement("button");
  askBtn.className = "btn"; askBtn.textContent = "ASK (1 SCRYING)";
  askBtn.onclick = async () => {
    const q = $("#oracle-q").value.trim();
    if (!q) return;
    askBtn.disabled = true; askBtn.textContent = "THE MISTS SWIRL...";
    $("#oracle-q").readOnly = true; // readOnly, not disabled — disabled fields swallow right-clicks and the browser's native menu leaks through
    const out = $("#oracle-a");
    out.classList.remove("hidden");
    out.textContent = "gazing into the glass...";
    let data;
    try {
      const r = await fetch("/api/oracle", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question: q,
          model: S.ai.oracle,
          kind: S.ai.oracleKind || "ollama",
          language: langName(),
          context: detail + (selection ? `\n\nTHE STUDENT HIGHLIGHTED THIS TEXT (their question likely refers to it):\n${selection.slice(0, 2000)}` : ""),
        }),
      });
      data = await r.json();
    } catch (err) { data = { ok: false, answer: "server error: " + err }; }
    out.textContent = data.answer;
    if (data.ok) {
      (S.oracleLog = S.oracleLog || []).push({ q, a: data.answer, ctx: label, at: Date.now() });
      S.inv.oracle--;
      save();
      paintOracleBtn();
      askBtn.remove();   // one question per scrying — pay again for the next
    } else {
      askBtn.disabled = false; askBtn.textContent = "ASK (1 SCRYING)";
      $("#oracle-q").readOnly = false;
    }
  };
  actions.prepend(askBtn);
  setTimeout(() => { const f = $("#oracle-q"); if (f) f.focus(); }, 50);
}

export function showOracleLog() {
  const rows = (S.oracleLog || []).slice().reverse().map((e) =>
    `<div style="margin-bottom:14px;padding-bottom:12px;border-bottom:1px solid var(--line)">
      <div class="dim" style="font-size:11px">${new Date(e.at).toLocaleString()} — ${esc(e.ctx || "")}</div>
      <div style="margin:6px 0"><b>&gt; ${esc(e.q)}</b></div>
      <div style="white-space:pre-wrap;font-size:12.5px">${esc(e.a)}</div>
    </div>`).join("");
  modal(`<h2>THE ORACLE'S NOTES</h2>
    <div style="max-height:60vh;overflow-y:auto">${rows || '<p class="dim">The pages are blank. Consult the Oracle and its answers will be copied down here.</p>'}</div>`,
    [["SET THE NOTES DOWN", "quiet"]]);
}
