import { $, esc } from "../../core/dom.js";

export const choiceInteraction = {
  version: 1, capabilities: ["choice-input", "local-validation"],
  label: "CHOOSE WISELY", buttonLabel: "CAST",
  create({ exercise, input, wrap }) {
    input.innerHTML = `<div class="choices">${exercise.choices.map((choice, index) =>
      `<label class="choice"><input type="radio" name="${esc(exercise.id)}" value="${index}"><span>${esc(choice)}</span></label>`).join("")}</div>`;
    input.querySelectorAll(".choice").forEach((choice) => choice.addEventListener("click", () => {
      input.querySelectorAll(".choice").forEach((item) => item.classList.remove("sel"));
      choice.classList.add("sel");
    }));
    return {
      getAnswer: () => { const selected = input.querySelector("input:checked"); return selected ? Number(selected.value) : -1; },
      validate: (answer) => ({ passed: answer === exercise.answer }),
      onIncorrect: () => {
        const selected = $(".choice.sel", wrap);
        if (selected) { selected.classList.add("wrong"); setTimeout(() => selected.classList.remove("wrong"), 900); }
      },
    };
  },
};
