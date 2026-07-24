/* THE GREAT WORKING — the workbench: monaco, the file tabs, diagnostics,
   the speaking stone, and casting the project. */
import { J, SRANK_MULT, editorLang, entryFile, externalByAuthor, externalDir, externalMode, gp, newFileExt, persona, projName, requiredFiles, runLabel } from "../core/config.js";
import { $, closeModal, esc, ico, modal, sfx, toast } from "../core/dom.js";
import { reviewBanner, wireReview } from "../game/exercise.js";
import { paintSubmitBtn, submitForGrading } from "../game/grading.js";
import { fsBest, secById } from "../game/progress.js";
import { castSigil } from "../game/sigil.js";
import { getState, save } from "../core/store.js";
import { externalEditorModal, openExternalFolder, openStarterFile, seedWorkspace } from "./workspace.js";
import { apiFetch } from "../core/api-client.js";
import { go } from "../core/router.js";
import { tome } from "../core/bootstrap.js";
import { isEvidenceTome } from "../mastery/policy.js";
import { performanceForNode } from "../mastery/assessment.js";
import { WorkbenchSession } from "./session.js";

const workingSession = new WorkbenchSession("cumulative-working");
let workingSection = null;
export const currentWorking = () => workingSection;
export const currentWorkbench = () => workingSession;
export const workbenchHasFiles = () => workingSession.models.size > 0;

export async function renderFreestyle(sid) {
  const sec = secById(sid);
  workingSection = sec;
  const v = $("#view-freestyle");
  v.classList.remove("hidden");
  $("#hud-op").textContent = "— the great working";
  const best = fsBest(sid);
  const xrayOn = getState().fs[sid] && getState().fs[sid].xray;
  const evidenceMode = isEvidenceTome(tome());
  const performance = performanceForNode(tome(), `${sid}.working`);
  const requirements = Array.isArray(sec.freestyle.requirements) ? sec.freestyle.requirements : [];

  v.innerHTML = `
    <div id="fs-wrap">
      ${reviewBanner()}
      <div class="fs-top">
        <div>
          <span class="crumb" style="margin:0"><button data-nav="sec">${esc(sec.codename)}</button> / THE GREAT WORKING</span>
          <div class="fs-title">${esc(sec.freestyle.title)}</div>
        </div>
        <div class="fs-actions">
          ${best ? `<span class="tag ${best.essentialPassed === false ? "warn" : "ac"} num">BEST: ${best.essentialPassed === false ? "INCOMPLETE" : esc(best.grade)} ${best.total}/100</span>` : ""}
          ${externalMode()
            ? (externalDir()
                ? `<button class="btn quiet" id="b-openext" title="Open ${esc(externalDir())} in your file explorer">${ico("file")} OPEN IN FILE EXPLORER</button><button class="btn quiet" id="b-extern" title="${esc(externalDir())}">${ico("quill")} EDITOR PATH</button>`
                : `<button class="btn" id="b-extern">${ico("file")} CHOOSE PROJECT FOLDER</button>`)
            : `<button class="btn quiet" id="b-extern">${ico("file")} USE MY OWN EDITOR</button>`}
          ${!externalMode() && (J().runtime && J().runtime.packages) !== false ? `<button class="btn quiet" id="b-pkg">${ico("pkg")} REAGENTS</button>` : ""}
          ${!externalMode() ? `<button class="btn quiet" id="b-save">${ico("quill")} BLOT THE PAGE</button>` : ""}
          <button class="btn ghost" id="b-run">${ico("play")} CAST THE SPELL</button>
          <button class="btn" id="b-submit">${ico("upload")} ${evidenceMode ? "SUBMIT FOR ASSESSMENT" : `PRESENT TO ${esc(persona())}`}</button>
        </div>
      </div>
      <div id="fs-cols">
        <div id="fs-left" class="${externalMode() ? "ext" : ""}">
          ${externalMode() ? `
          <div id="ext-panel">
            <div class="ext-head">${ico("file")} YOU'RE EDITING IN YOUR OWN EDITOR</div>
            <div class="ext-grid${externalByAuthor() || !externalDir() ? " solo" : ""}">
              <div class="ext-main">
                ${externalDir() ? `
                <p>Open and build this project in your own IDE (IntelliJ, VS Code, and so on):</p>
                <div class="ext-dir"><code>${esc(externalDir())}</code></div>
                <p><b>CAST THE SPELL</b> runs that folder via <code>${esc(runLabel())}</code>, and <b>PRESENT TO ${esc(persona())}</b> sends the whole folder for judgement. Both read your folder directly — the workbench never edits or resets it. Save in your own editor before you cast or present.</p>
                <div class="ext-buttons">
                  ${externalByAuthor() ? "" : `<button class="btn quiet" id="b-seed">${ico("file")} PLACE STARTER FILES</button>`}
                  <button class="btn quiet" id="b-extern2">${ico("quill")} CHANGE FOLDER</button>
                  ${externalByAuthor() ? "" : `<button class="btn quiet" id="b-builtin">${ico("quill")} SWITCH BACK TO THE BUILT-IN EDITOR</button>`}
                </div>`
                : `
                <p>${externalByAuthor()
                    ? "This course is built in your own project — there is no built-in editor. Follow the setup lessons to create the project folder, then point the workbench at it:"
                    : "Point the workbench at a folder you build in with your own IDE (IntelliJ, VS Code, a real project):"}</p>
                <div class="ext-buttons">
                  <button class="btn" id="b-choose">${ico("file")} CHOOSE PROJECT FOLDER</button>
                  ${externalByAuthor() ? "" : `<button class="btn quiet" id="b-builtin">${ico("quill")} USE THE BUILT-IN EDITOR INSTEAD</button>`}
                </div>
                <p class="dim">An absolute path to a folder that already exists. The engine only reads it — it never edits, scaffolds, or resets your project.</p>`}
              </div>
              ${externalByAuthor() || !externalDir() ? "" : `
              <div class="ext-files">
                <h4>THIS PROJECT NEEDS</h4>
                <ul class="sf-grid">
                  ${requiredFiles().map((f) => `<li class="sf-item" data-rel="${esc(f.rel)}" title="View the starter contents"><code>${esc(f.path)}</code>${f.location ? ` <span class="dim">in <code>${esc(f.location)}/</code></span>` : ""}<span class="ext-fdesc">${esc(f.desc)}</span><span class="sf-view">${ico("eye")} view starter code</span></li>`).join("")}
                </ul>
                <p class="dim">Placed in your folder when you chose it. Missing any, or want them fresh? Use <b>PLACE STARTER FILES</b>.</p>
              </div>`}
            </div>
          </div>` : `
          <div id="file-tabs"></div>
          <div id="editor-host"></div>`}
          <div id="term">
            <div class="term-head"><span>THE SPEAKING STONE</span><button class="btn quiet" id="b-clear" style="height:22px;padding:0 8px;font-size:10px">WIPE</button></div>
            <div class="term-stdin">
              <span class="stdin-label">WHISPER (STDIN)</span>
              <input type="text" id="stdin-box" placeholder="whispered to your spell as it runs — separate lines with \\n  (e.g.  hello\\nquit)" spellcheck="false">
            </div>
            <pre id="term-out">The speaking stone is set into the desk. CAST THE SPELL runs your work via ${esc(runLabel())}; the stone repeats what it says.</pre>
          </div>
        </div>
        <div id="fs-right">
          <h3>THE COMMISSION</h3>
          <div class="fs-brief">${sec.freestyle.brief.replace(/<ul>[\s\S]*?<\/ul>/, "")}</div>
          ${requirements.length ? `<h3 style="margin-top:18px">PUBLIC REQUIREMENTS</h3><ol class="working-requirements">${requirements.map(
            (requirement) => `<li data-essential="${requirement.essential !== false}"><code>${esc(requirement.id)}</code><span>${esc(requirement.text)}</span>${requirement.essential !== false ? "<b>ESSENTIAL</b>" : ""}</li>`).join("")}</ol>`
            : (sec.freestyle.brief.match(/<ul>[\s\S]*?<\/ul>/) || []).map((u) =>
              `<h3 style="margin-top:18px">IT MUST</h3><div class="fs-brief">${u}</div>`).join("")}
          <h3 style="margin-top:18px">THE JUDGEMENT CHART <span class="dim" style="letter-spacing:0;font-style:italic">(${esc(persona())} weighs against exactly this)</span></h3>
          <table class="rubric-table">
            ${sec.freestyle.rubric.map((r) => `<tr><td class="rw num">${r.weight}%</td><td><b>${esc(r.criterion)}</b>${r.essential ? ` <span class="tag warn">ESSENTIAL · ${r.minimumScore || 6}/10</span>` : ""}<span class="rubric-desc">${esc(r.desc)}</span></td></tr>`).join("")}
          </table>
          ${!evidenceMode && (sec.freestyle.verification || []).length ? `<h3 style="margin-top:18px">HARNESS VERIFICATION</h3>
            <div class="assessment-standard">${sec.freestyle.verification.map((item) =>
              `<span><b>${esc(item.label || item.id || item.command)}</b> · ${item.required === false ? "advisory" : "must pass"} · sandboxed command <code>${esc(item.command)}</code></span>`).join("")}</div>` : ""}
          ${evidenceMode ? `<h3 style="margin-top:18px">EVIDENCE STANDARD</h3>
            <div class="assessment-standard"><b>Every essential scenario must pass.</b><span>80/B or better is required. Deterministic build and behavior evidence appears before qualitative feedback.</span><span>A supported result can resolve work, but only an eligible submission counts as independent evidence.</span></div>
            ${performance?.rationaleRequired ? `<label class="rationale-field"><span>RATIONALE / DEFENSE</span><textarea id="fs-rationale" rows="5" placeholder="Explain the decisions and tradeoffs in your implementation."></textarea></label>` : ""}`
            : `<h3 style="margin-top:18px">PAYMENT</h3><div style="font-size:12.5px" class="dim">
              Base <span class="num">${sec.freestyle.reward}</span>${gp()} scaled by the judgement. An S pays <span class="num">${Math.round(sec.freestyle.reward * SRANK_MULT)}</span>${gp()}.
              A C (70+) presses the <b>${esc(sec.freestyle.badge.name)}</b> sigil. A D (60+) unseals the next chapter only when every essential rubric and required harness verification also passes.
              Presenting again pays only the improvement over your best.</div>`}
          ${sec.freestyle.xray ? (xrayOn
            ? `<h3 style="margin-top:18px">SCRYING LENS <span class="tag warn">HELD TO THE PAGE</span></h3><p style="font-size:12.5px" class="dim">${sec.freestyle.xray}</p>`
            : `<button class="btn quiet" id="b-xray" style="margin-top:16px">${ico("eye")} RAISE THE SCRYING LENS (${getState().inv.xray || 0} owned)</button>`) : ""}
        </div>
      </div>
    </div>`;

  $("[data-nav=sec]", v).onclick = () => go("section", sid);
  wireReview(v);

  // xray
  const bx = $("#b-xray", v);
  if (bx) bx.onclick = () => {
    if ((getState().inv.xray || 0) < 1) { toast("You carry no Scrying Lens. The peddler grinds them.", "bad"); return; }
    modal(`<h2>RAISE THE SCRYING LENS?</h2><p class="dim">The lens shatters after one use — but ${esc(persona())}'s private judging notes for this working stay revealed forever.</p>`,
      [["LOWER IT", "quiet"], ["LOOK THROUGH", "", () => { getState().inv.xray--; (getState().fs[sid] = getState().fs[sid] || {}).xray = true; save(); renderFreestyle(sid); }]]);
  };

  // external-editor mode: no built-in editor. The student edits in their own IDE
  // and CAST/PRESENT operate on their folder — the server resolves the directory,
  // so we send no buffers (collectFiles() is [] with no models, never clobbering it).
  if (externalMode()) {
    workingSession.dispose();
    // a required-external course starts with no folder chosen — CAST/PRESENT
    // must send the student to pick one, never run against the scaffolded dir.
    const needFolder = () => { if (externalDir()) return false; toast("Choose your project folder first.", "warn"); externalEditorModal(sid); return true; };
    $("#b-run", v).onclick = () => { if (!needFolder()) runProject(); };
    $("#b-submit", v).onclick = () => { if (!needFolder()) submitForGrading(); };
    $("#b-clear", v).onclick = () => { $("#term-out").textContent = ""; };
    const be = $("#b-extern", v); if (be) be.onclick = () => externalEditorModal(sid);
    const be2 = $("#b-extern2", v); if (be2) be2.onclick = () => externalEditorModal(sid);
    const bc = $("#b-choose", v); if (bc) bc.onclick = () => externalEditorModal(sid);
    const bo = $("#b-openext", v); if (bo) bo.onclick = () => openExternalFolder(externalDir());
    const bs = $("#b-seed", v); if (bs) bs.onclick = () => seedWorkspace(externalDir(), "");
    const bb = $("#b-builtin", v); if (bb) bb.onclick = () => {
      getState().workspace = { enabled: false, dir: (getState().workspace && getState().workspace.dir) || "" };
      save(); renderFreestyle(sid);
    };
    v.querySelectorAll(".sf-item").forEach((li) => li.onclick = () => openStarterFile(li.dataset.rel));
    paintSubmitBtn();
    return;
  }

  // load workspace + editor
  await window.GhostEditor.monacoReady;
  const host = $("#editor-host", v);
  host.innerHTML = "";
  workingSession.dispose();
  workingSession.editor = window.GhostEditor.create(host, getState().theme);

  let files = [];
  try {
    const r = await apiFetch("/api/workspace");
    const data = await r.json();
    if (!data.exists) {
      termPrint(`No workshop yet — laying out a fresh one for ${projName()}...`);
      const sr = await apiFetch("/api/scaffold", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
      const sd = await sr.json();
      termPrint(sd.ok ? `The workshop stands: ${projName()} (${entryFile()} is yours to inscribe).` : "THE SCAFFOLDING COLLAPSED: " + (sd.error || ""), !sd.ok);
      const r2 = await apiFetch("/api/workspace");
      files = (await r2.json()).files || [];
    } else files = data.files || [];
  } catch (err) { termPrint("Could not reach server: " + err, true); }

  // merge crash-recovered buffers over disk state
  const byPath = {};
  for (const f of files) byPath[f.path] = f.content;
  for (const [p2, c] of Object.entries(getState().buffers)) byPath[p2] = c;
  if (!Object.keys(byPath).length) byPath[entryFile()] = (J().runtime && J().runtime.starterCode) || 'Console.WriteLine("Verisearch v0.1");\n';

  window.GhostEditor._getAllBuffers = () => {
    const out = {};
    for (const [p2, m] of workingSession.models) out[p2] = m.getValue();
    return out;
  };

  for (const [p2, content] of Object.entries(byPath)) addFileModel(p2, content);
  const paths = [...workingSession.models.keys()];
  const first = paths.find((p2) => p2.endsWith(newFileExt())) || paths[0];
  switchFile(first);
  renderTabs();
  scheduleDiagnostics();

  // actions
  $("#b-save", v).onclick = () => saveWorkspace(true);
  $("#b-clear", v).onclick = () => { $("#term-out").textContent = ""; }; // (stone tap + chips come from the material delegate in init)
  $("#b-run", v).onclick = runProject;
  $("#b-submit", v).onclick = submitForGrading;
  if ($("#b-pkg", v)) $("#b-pkg", v).onclick = () => packageModal(sec);
  if ($("#b-extern", v)) $("#b-extern", v).onclick = () => externalEditorModal(sid);
  paintSubmitBtn(); // a grade may still be in flight from before a re-render
}

function addFileModel(path, content) {
  const lang = path.endsWith(newFileExt()) ? editorLang() : path.endsWith(".csproj") ? "xml" : path.endsWith(".json") ? "json" : path.match(/\.ya?ml$/) ? "yaml" : "plaintext";
  const m = monaco.editor.createModel(content, lang);
  m.onDidChangeContent(() => {
    getState().buffers[path] = m.getValue();
    save();
    const tab = document.querySelector(`.ftab[data-path="${CSS.escape(path)}"] .dirty`);
    if (tab) tab.classList.remove("hidden");
    if (path.endsWith(newFileExt()) || path.endsWith(".csproj")) scheduleDiagnostics();
  });
  workingSession.models.set(path, m);
}

// real compiler squiggles: on idle, build the workspace server-side and mark CS errors/warnings
let diagTimer = null, diagBusy = false, diagAgain = false;
function scheduleDiagnostics() {
  clearTimeout(diagTimer);
  diagTimer = setTimeout(runDiagnostics, 1500);
}
async function runDiagnostics() {
  const live = [...workingSession.models].filter(([, m]) => !m.isDisposed());
  if (!window.monaco || !live.length) return;
  if (diagBusy) { diagAgain = true; return; }
  diagBusy = true;
  let data = null;
  try {
    const r = await apiFetch("/api/diagnostics", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ files: live.map(([path, m]) => ({ path, content: m.getValue() })) }),
    });
    data = await r.json();
  } catch { /* server hiccup — keep existing markers */ }
  diagBusy = false;
  if (diagAgain) { diagAgain = false; scheduleDiagnostics(); }
  if (!data || !data.ok) return;
  const byFile = {};
  for (const d of data.diags || []) (byFile[d.file] = byFile[d.file] || []).push(d);
  for (const [path, m] of live) {
    if (m.isDisposed()) continue;
    monaco.editor.setModelMarkers(m, "ghostdiag", (byFile[path] || []).map((d) => {
      const w = m.getWordAtPosition({ lineNumber: d.line, column: d.col });
      return {
        severity: d.sev === "error" ? monaco.MarkerSeverity.Error : monaco.MarkerSeverity.Warning,
        message: `${d.code}: ${d.msg}`,
        startLineNumber: d.line, startColumn: d.col,
        endLineNumber: d.line, endColumn: w ? w.endColumn : d.col + 1,
      };
    }));
  }
}

function renderTabs() {
  const tabs = $("#file-tabs");
  if (!tabs) return;
  tabs.innerHTML = "";
  for (const p2 of [...workingSession.models.keys()].sort()) {
    const t = document.createElement("button");
    t.className = "ftab" + (p2 === workingSession.activePath ? " active" : "");
    t.dataset.path = p2;
    t.innerHTML = `${esc(p2)}<span class="dirty ${getState().buffers[p2] !== undefined ? "" : "hidden"}"></span>`;
    t.onclick = () => switchFile(p2);
    tabs.appendChild(t);
  }
  const plus = document.createElement("button");
  plus.className = "ftab-new"; plus.textContent = "+"; plus.title = "New file";
  plus.onclick = () => {
    modal(`<h2>A FRESH LEAF</h2><p class="dim">Its name within the ${esc(projName())} folio, e.g. <code>module${esc(newFileExt())}</code></p><input type="text" id="nf-name" style="width:100%" placeholder="MyFile${esc(newFileExt())}">`,
      [["LEAVE IT", "quiet"], ["CUT THE LEAF", "", null]]);
    const nfBtn = document.querySelectorAll("#modal-root .modal-actions .btn")[1];
    nfBtn.onclick = () => {
      const name = $("#nf-name").value.trim();
      closeModal(() => {
        if (!name || workingSession.models.has(name)) return;
        addFileModel(name, name.endsWith(".cs") ? `namespace ${projName()};\n\n` : "");
        getState().buffers[name] = workingSession.models.get(name).getValue();
        switchFile(name); save();
      });
    };
    setTimeout(() => { const f = $("#nf-name"); if (f) f.focus(); }, 50);
  };
  tabs.appendChild(plus);
}

function switchFile(path) {
  if (!workingSession.models.has(path)) return;
  workingSession.activePath = path;
  workingSession.editor.setModel(workingSession.models.get(path));
  renderTabs();
  workingSession.editor.focus();
}

export function collectFiles() {
  return workingSession.files();
}

export async function saveWorkspace(announce) {
  try {
    await apiFetch("/api/workspace", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ files: collectFiles() }) });
    getState().buffers = {}; save();
    document.querySelectorAll(".ftab .dirty").forEach((d) => d.classList.add("hidden"));
    if (announce) { toast("The ink is dry — your pages are safe on disk."); sfx("saved"); }
  } catch (err) { toast("The ink would not take: " + err, "bad"); }
}

function termPrint(text, isErr) {
  const out = $("#term-out");
  if (!out) return;
  const span = document.createElement("span");
  span.className = isErr ? "t-err" : "";
  span.textContent = text + "\n";
  out.appendChild(span);
  out.scrollTop = out.scrollHeight;
}

async function runProject() {
  const btn = $("#b-run"), sub = $("#b-submit");
  let running = true;
  // the button stays clickable: hovering it flips it into a CANCEL control while the run is live.
  // mousemove (not just mouseenter) because the pointer is already ON the button right after clicking it.
  const started = Date.now();
  btn.textContent = "CASTING...";
  const showCancel = () => { if (running && Date.now() - started > 700) btn.textContent = "BREAK THE CHANT?"; };
  btn.onmouseenter = showCancel;
  btn.onmousemove = showCancel;
  btn.onmouseleave = () => { if (running) btn.textContent = "CASTING..."; };
  btn.onclick = () => { if (running) apiFetch("/api/runcancel", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" }); };
  if (sub) sub.disabled = true;
  clearTimeout(diagTimer); // don't let a queued diagnostics build contend with this run
  termPrint("$ " + runLabel() + "    // " + new Date().toLocaleTimeString());
  getState().stats.runs++; save();
  try {
    const stdin = ($("#stdin-box").value || "").replace(/\\n/g, "\n");
    const r = await apiFetch("/api/run", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ files: collectFiles(), stdin }),
    });
    const data = await r.json();
    getState().buffers = {}; save();
    document.querySelectorAll(".ftab .dirty").forEach((d) => d.classList.add("hidden"));
    termPrint(data.output || "(the stone stays silent)", !data.ok);
    termPrint(data.ok ? "── the spell completed, exit 0 ──" : "── the casting failed ──", !data.ok);
    castSigil(null, data.ok); // the workbench run earns the full drawn sigil
  } catch (err) { termPrint("THE STONE CANNOT REACH THE FORGE: " + err, true); }
  running = false;
  btn.onmouseenter = btn.onmousemove = btn.onmouseleave = null;
  btn.onclick = runProject;
  btn.innerHTML = `${ico("play")} CAST THE SPELL`;
  paintSubmitBtn(); // re-enable only if no grade job is in flight
  scheduleDiagnostics(); // the run just built everything — refresh squiggles off the warm cache
}

function packageModal(sec) {
  const suggested = sec.freestyle.packages || [];
  modal(`<h2>REAGENTS (NUGET PACKAGES)</h2>
    <p class="dim">Rarer components, measured into your ${esc(projName())} folio via <code>dotnet add package</code>.</p>
    ${suggested.length ? `<p style="font-size:12.5px">The commission calls for: ${suggested.map((p2) => `<code>${esc(p2)}</code>`).join(" ")}</p>` : ""}
    <input type="text" id="pkg-name" style="width:100%" placeholder="${suggested[0] || "Package.Name"}" value="${suggested[0] || ""}">
    <pre id="pkg-out" class="dim" style="font-family:var(--mono);font-size:11px;max-height:160px;overflow:auto;margin-top:10px"></pre>`,
    [["CLOSE THE CABINET", "quiet"]]);
  const actions = $(".modal-actions");
  const installBtn = document.createElement("button");
  installBtn.className = "btn"; installBtn.textContent = "MEASURE IT IN";
  installBtn.onclick = async () => {
    const name = $("#pkg-name").value.trim();
    if (!name) return;
    installBtn.disabled = true; installBtn.textContent = "DECANTING...";
    try {
      const r = await apiFetch("/api/addpackage", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ package: name }) });
      const data = await r.json();
      $("#pkg-out").textContent = data.output || "";
      toast(data.ok ? `Reagent <b>${esc(name)}</b> is in the folio.` : "The reagent refused the flask — read the residue.", data.ok ? "" : "bad");
    } catch (err) { $("#pkg-out").textContent = String(err); }
    installBtn.disabled = false; installBtn.textContent = "MEASURE IT IN";
  };
  actions.prepend(installBtn);
}
