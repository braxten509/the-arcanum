/* The student's own folder: seeding starter files, previewing them, and choosing the path. */
import { externalDir } from "../core/config.js";
import { $, closeModal, esc, modal, sfx, toast } from "../core/dom.js";
import { S, save } from "../core/state.js";
import { renderFreestyle } from "./workbench.js";

// seed the tome's starter files into the student's own folder. mode: "" checks first
// (seeds silently if nothing is there, else prompts), "missing" adds only absent files,
// "force" overwrites. Returns true if anything was placed.
export async function seedWorkspace(dir, mode) {
  if (!dir) return false;
  let d;
  try {
    const r = await fetch("/api/seedworkspace", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ dir, mode: mode || "" }),
    });
    d = await r.json();
  } catch (e) { toast("Could not reach the forge to place files: " + e, "bad"); return false; }
  if (d.ok) {
    const placed = d.seeded || [];
    if (placed.length) { toast(`Starter files placed: ${placed.map((f) => `<code>${esc(f)}</code>`).join(" ")}`); sfx("saved"); }
    else toast("Your folder already has every starter file.");
    return true;
  }
  if (d.conflicts && d.conflicts.length) {
    const present = d.conflicts, missing = d.missing || [];
    const list = (arr) => `<ul style="margin:6px 0 0;padding-left:18px;font-family:var(--mono);font-size:12.5px">${arr.map((f) => `<li>${esc(f)}</li>`).join("")}</ul>`;
    return await new Promise((resolve) => {
      const actions = [["KEEP MINE", "quiet", () => resolve(false)]];
      if (missing.length) actions.push(["ADD MISSING", "", () => { seedWorkspace(dir, "missing").then(resolve); }]);
      actions.push(["OVERWRITE", missing.length ? "quiet" : "", () => { seedWorkspace(dir, "force").then(resolve); }]);
      modal(`<h2>FILES ALREADY IN YOUR FOLDER</h2>
        <p class="dim">Your folder already holds ${present.length === 1 ? "this starter file" : "these starter files"}:</p>
        ${list(present)}
        ${missing.length ? `<p class="dim" style="margin-top:12px">Your folder is still missing:</p>${list(missing)}` : ""}
        <p class="dim" style="margin-top:12px">${missing.length
          ? "<b>Add missing</b> writes only what's absent and leaves your files alone. <b>Overwrite</b> replaces them all with the tome's fresh starter files."
          : "Overwrite them with the tome's fresh starter files, or keep your own?"}</p>`,
        actions);
    });
  }
  toast("Could not place starter files: " + (d.error || "unknown"), "bad");
  return false;
}

// show the starter contents of one required file, with a copy button
export async function openStarterFile(rel) {
  if (!rel) return;
  modal(`<h2>${esc(rel)}</h2>
    <p class="dim">The starter contents for this file — copy it into your own editor.</p>
    <pre id="sf-pre" style="max-height:749px;overflow:auto;margin:10px 0 0;padding:12px 14px;border:1px solid var(--line-hi);border-radius:var(--rad);background:var(--bg2);font-family:var(--mono);font-size:12.5px;white-space:pre"><code>loading…</code></pre>`,
    [["CLOSE", "quiet"]]);
  const copyBtn = document.createElement("button");
  copyBtn.className = "btn"; copyBtn.textContent = "COPY";
  const actions = $("#modal-root .modal-actions"); if (actions) actions.prepend(copyBtn);
  let content = "";
  try {
    const r = await fetch("/api/starterfile?path=" + encodeURIComponent(rel));
    const j = await r.json();
    content = j.ok ? (j.content || "(this file has no starter content)") : ("(" + (j.error || "could not load") + ")");
  } catch (e) { content = "(could not load: " + e + ")"; }
  const code = $("#modal-root #sf-pre code"); if (code) code.textContent = content;
  copyBtn.onclick = () => {
    navigator.clipboard.writeText(content)
      .then(() => { copyBtn.textContent = "COPIED ✓"; setTimeout(() => { copyBtn.textContent = "COPY"; }, 1200); })
      .catch(() => toast("The browser blocked the clipboard — select and copy manually.", "warn"));
  };
}

// open the external project folder in the OS file explorer (server runs on the same machine)
export async function openExternalFolder(dir) {
  if (!dir) return;
  try {
    const r = await fetch("/api/openpath", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ dir }) });
    const d = await r.json();
    if (!d.ok) toast("Could not open the folder: " + (d.error || "unknown"), "bad");
  } catch (e) { toast("Could not open the folder: " + e, "bad"); }
}

// pick a folder the student builds in with their own editor; validated server-side
export function externalEditorModal(sid) {
  const cur = (S.workspace && S.workspace.dir) || externalDir() || "";
  modal(`<h2>USE YOUR OWN EDITOR</h2>
    <p class="dim">Point the workbench at a folder you build in your own IDE (IntelliJ, VS Code, a real project). <b>CAST</b> and <b>PRESENT</b> then run and grade that folder instead of the built-in editor — the engine only reads it, and never edits, scaffolds, or resets your project.</p>
    <input type="text" id="ext-dir" style="width:100%" placeholder="/home/you/projects/MyBuild" value="${esc(cur)}" spellcheck="false">
    <div id="ext-msg" class="dim" style="font-size:12px;margin-top:8px">An absolute path to a folder that already exists.</div>`,
    [["CANCEL", "quiet"], ["USE THIS FOLDER", "", null]]);
  const btns = document.querySelectorAll("#modal-root .modal-actions .btn");
  const useBtn = btns[btns.length - 1];
  useBtn.onclick = async () => {
    const dir = $("#ext-dir").value.trim();
    const msg = $("#ext-msg");
    if (!dir) { msg.textContent = "Enter a folder path."; return; }
    msg.textContent = "checking the path...";
    try {
      const r = await fetch("/api/checkdir?path=" + encodeURIComponent(dir));
      const d = await r.json();
      if (!d.abs) { msg.textContent = "Use an ABSOLUTE path (it must start with / )."; return; }
      if (!d.isdir) { msg.textContent = "No folder exists there — create it first, or fix the path."; return; }
    } catch (e) { msg.textContent = "Could not check the path: " + e; return; }
    S.workspace = { enabled: true, dir };
    save();
    closeModal(() => { renderFreestyle(sid); seedWorkspace(dir, ""); });
  };
  setTimeout(() => { const f = $("#ext-dir"); if (f) f.focus(); }, 50);
}
