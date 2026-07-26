/* MARGINALIA — what the reader writes in the margin about the tome itself:
   a wrong answer, a lesson that skipped a step, a phrasing to change. Kept beside
   the repository (notes/<tome>.jsonl), not in the save file, so a note outlives
   the progress reset that usually follows finding the problem. */
import { $, esc, modal, toast } from "../core/dom.js";
import { apiJson, postJson } from "../core/api-client.js";
import { oracleContext } from "../bench/oracle.js";

const stamp = (at) => new Date((at || 0) * 1000).toLocaleString();

function noteRow(n) {
  return `<div class="marg-note">
    <div class="marg-head">
      <span class="marg-where">${esc(n.where || "THE TOME AT LARGE")}</span>
      <time>${esc(stamp(n.at))}</time>
      <button type="button" class="marg-strike" data-strike="${esc(n.id)}"
        title="Strike this note from the margin">STRIKE</button>
    </div>
    ${n.quote ? `<blockquote>${esc(n.quote)}</blockquote>` : ""}
    <p>${esc(n.text)}</p>
  </div>`;
}

const asText = (notes) => notes.map((n) =>
  `- [${n.where || "the tome at large"} // ${stamp(n.at)}] ${n.text}`
  + (n.quote ? `\n    quoted: ${n.quote}` : "")).join("\n");

export async function showTomeNotes(quote = "") {
  // oracleContext calls the whole-tome case "global", which is the Oracle's word for a
  // question with no lesson attached. In the margin it reads as a stray debug string.
  const context = oracleContext().label;
  const where = context === "global" ? "THE TOME AT LARGE" : context;
  let notes = [], reachable = true;
  try {
    notes = (await apiJson("/api/notes")).notes || [];
  } catch {
    reachable = false;
  }
  const painted = () => notes.length
    ? notes.map(noteRow).join("")
    : '<p class="dim">The margin is clean. Write the first note above.</p>';

  modal(`<h2>MARGINALIA</h2>
    <p class="dim">Notes on the tome itself — what is wrong, what should change. They are
      kept beside the book, not in your progress, and survive a reset.</p>
    <div class="marg-write">
      <label for="marg-text">${esc(where)}</label>
      ${quote ? `<blockquote id="marg-quote">${esc(quote)}</blockquote>` : ""}
      <textarea id="marg-text" rows="4" spellcheck="true"
        placeholder="What should change here?"></textarea>
    </div>
    ${reachable ? "" : '<p class="marg-cold">The study cannot reach the shelf where notes are kept — nothing written now will be saved.</p>'}
    <div class="marg-list" id="marg-list">${painted()}</div>`,
    [["CLOSE THE MARGIN", "quiet"], ["COPY ALL", "quiet", null], ["INSCRIBE", "", null]],
    { sticky: true });

  const list = $("#marg-list");
  const repaint = () => { list.innerHTML = painted(); };
  const [, copyBtn, inscribeBtn] = document.querySelectorAll("#modal-root .modal-actions .btn");

  copyBtn.disabled = !notes.length;
  copyBtn.onclick = async () => {
    try {
      await navigator.clipboard.writeText(asText(notes));
      toast(`${notes.length} NOTE${notes.length === 1 ? "" : "S"} COPIED // hand them to the Binder`);
    } catch {
      toast("The browser guards its clipboard — select the notes and copy by hand.", "warn");
    }
  };

  inscribeBtn.onclick = async () => {
    const field = $("#marg-text");
    const text = field.value.trim();
    if (!text) return field.focus();
    inscribeBtn.disabled = true;
    inscribeBtn.textContent = "INKING…";
    try {
      // The modal stays open: one sitting usually produces several notes, and closing
      // it would throw away the quote the reader right-clicked to get here with.
      const saved = await postJson("/api/notes", { text, where, quote });
      notes.unshift(saved);
      field.value = "";
      repaint();
      copyBtn.disabled = false;
      toast("NOTED IN THE MARGIN");
    } catch (e) {
      toast(`THE MARGIN REFUSED THE NOTE // ${esc(String(e.message || e))}`, "bad");
    } finally {
      inscribeBtn.disabled = false;
      inscribeBtn.textContent = "INSCRIBE";
      field.focus();
    }
  };

  list.onclick = async (ev) => {
    const id = ev.target.closest("[data-strike]")?.dataset.strike;
    if (!id) return;
    try {
      await postJson("/api/notes/remove", { id });
      notes = notes.filter((n) => n.id !== id);
      repaint();
      copyBtn.disabled = !notes.length;
    } catch (e) {
      toast(`THE NOTE WOULD NOT LIFT // ${esc(String(e.message || e))}`, "bad");
    }
  };

  setTimeout(() => { const f = $("#marg-text"); if (f) f.focus(); }, 50);
}
