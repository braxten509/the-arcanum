/* Inline monaco pads and the code comparison used by drills, labs, hexes and duels. */
import { S } from "../core/state.js";

// normalize code for typing-drill / lab-output comparison:
// trims line ends, collapses internal whitespace runs, drops blank lines
export function normCode(s2) {
  return String(s2).split("\n").map((l) => l.trim().replace(/\s+/g, " ")).filter((l) => l !== "").join("\n");
}
export function firstDiff(a, b) {
  const A = normCode(a).split("\n"), B = normCode(b).split("\n");
  for (let i = 0; i < Math.max(A.length, B.length); i++) {
    if (A[i] !== B[i]) {
      const got = A[i] || "(missing line)", expected = B[i] || "(nothing — extra line)";
      let col = 0;
      while (col < Math.min(got.length, expected.length) && got[col] === expected[col]) col++;
      const name = (c) => c === undefined ? "(end of line)" : c === "0" ? "'0' (zero)" : c === "O" ? "'O' (letter O)" : c === "l" ? "'l' (lowercase L)" : c === "1" ? "'1' (one)" : `'${c}'`;
      return { line: i + 1, expected, got, hint: A[i] && B[i] ? ` — first difference at char ${col + 1}: expected ${name(expected[col])} got ${name(got[col])}` : "" };
    }
  }
  return null;
}

// ---- inline monaco pads: full C# intellisense anywhere code is typed (labs, intrusion defense).
// the completion provider in editor.js is registered per-language, so every pad gets it free.
const pads = [];
export function codePad(host, value, onCtrlEnter) {
  for (let i = pads.length - 1; i >= 0; i--) // sweep editors whose DOM is gone
    if (!pads[i].host.isConnected) { pads[i].ed.dispose(); pads.splice(i, 1); }
  host.style.height = Math.min(30, Math.max(12, value.split("\n").length + 4)) * 22 + 26 + "px";
  const pe = window.GhostEditor.create(host, S.theme);
  pe.setValue(value);
  if (onCtrlEnter) pe.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.Enter, onCtrlEnter);
  pads.push({ host, ed: pe });

  // real compiler squiggles: on idle, build the snippet server-side and underline errors/warnings
  let timer = null, busy = false, again = false;
  const diag = async () => {
    if (busy) { again = true; return; }
    busy = true;
    let data = null;
    try {
      const r = await fetch("/api/snippetdiag", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ code: pe.getValue() }),
      });
      data = await r.json();
    } catch { /* server hiccup — keep existing markers */ }
    busy = false;
    if (again) { again = false; timer = setTimeout(diag, 200); return; }
    const m = pe.getModel();
    if (!data || !data.ok || !m || m.isDisposed()) return;
    monaco.editor.setModelMarkers(m, "paddiag", (data.diags || []).map((d) => {
      const w = m.getWordAtPosition({ lineNumber: d.line, column: d.col });
      return {
        severity: d.sev === "error" ? monaco.MarkerSeverity.Error : monaco.MarkerSeverity.Warning,
        message: `${d.code}: ${d.msg}`,
        startLineNumber: d.line, startColumn: d.col,
        endLineNumber: d.line, endColumn: w ? w.endColumn : d.col + 1,
      };
    }));
  };
  pe.getModel().onDidChangeContent(() => { clearTimeout(timer); timer = setTimeout(diag, 1500); });
  return pe;
}
