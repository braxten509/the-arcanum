import { $ } from "../../core/dom.js";
import { firstDiff } from "../code.js";

export const copyInteraction = {
  version: 1, capabilities: ["code-input", "exact-copy-validation", "paste-blocking"],
  label: "COPYING DRILL", buttonLabel: "CAST", noDecay: true, repetitions: true,
  create({ exercise, input, wrap, toast }) {
    input.innerHTML = `<textarea class="drill-box" data-nopaste="1" rows="${Math.max(2, (exercise.code || "").split("\n").length + 1)}" spellcheck="false" placeholder="copy it out by hand — the hand remembers what the eye forgets; conjured paste is barred"></textarea>`;
    const box = $("textarea", input);
    box.addEventListener("paste", (event) => { event.preventDefault(); toast("No pasting by sorcery. The quill only, apprentice.", "warn"); });
    box.addEventListener("drop", (event) => event.preventDefault());
    box.addEventListener("keydown", (event) => {
      if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) { event.preventDefault(); $(".b-check", wrap).click(); }
      if (event.key === "Tab") { event.preventDefault(); box.setRangeText("    ", box.selectionStart, box.selectionEnd, "end"); }
    });
    return {
      getAnswer: () => box.value,
      validate(answer) {
        const difference = firstDiff(answer, exercise.code);
        return difference ? { passed: false, message: `LINE ${difference.line}: expected «${difference.expected}» got «${difference.got}»${difference.hint}` }
          : { passed: true };
      },
    };
  },
};
