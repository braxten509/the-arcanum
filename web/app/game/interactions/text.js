import { $ } from "../../core/dom.js";

const normalize = (value) => String(value).trim().toLowerCase().replace(/\s+/g, " ")
  .replace(/;$/, "").replace(/^["']|["']$/g, "");

export const textInteraction = {
  version: 1, capabilities: ["text-input", "local-validation"],
  label: "SPEAK THE WORD", buttonLabel: "CAST",
  create({ exercise, input, wrap }) {
    input.innerHTML = `<div class="ex-answer-row"><input type="text" placeholder="${exercise.type === "fill" ? "what completes the rune?" : "write your answer"}" spellcheck="false"></div>`;
    const field = $("input", input);
    field.addEventListener("keydown", (event) => {
      if (event.key === "Enter") $(".b-check", wrap).click();
    });
    return {
      getAnswer: () => field.value,
      validate(answer) {
        const targets = [exercise.answer].concat(exercise.accept || []).map(normalize);
        return { passed: targets.includes(normalize(answer)) };
      },
    };
  },
};

export const fillInteraction = { ...textInteraction, label: "COMPLETE THE RUNE" };
