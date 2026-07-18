import { apiJson } from "../../core/api-client.js";
import { $, esc } from "../../core/dom.js";
import { runLabel } from "../../core/config.js";
import { codePad, firstDiff, normCode } from "../code.js";

export const runnableInteraction = {
  version: 1, capabilities: ["code-input", "runtime-execution", "output-validation"],
  label: "INSCRIPTION", buttonLabel: "INSCRIBE + CAST", noDecay: true, fullSigil: true,
  create({ exercise, input, wrap }) {
    input.innerHTML = `<div class="code-pad"></div>
      ${exercise.stdin ? `<div class="faint" style="font-size:11px;margin-top:4px">STDIN fed to your program: <code>${esc(exercise.stdin.replace(/\n/g, "\\n"))}</code></div>` : ""}
      <pre class="lab-out hidden"></pre>`;
    let editor = null;
    window.GhostEditor.monacoReady.then(() => {
      editor = codePad($(".code-pad", input), exercise.starter || "",
        () => $(".b-check", wrap)?.click());
    });
    return {
      getAnswer: () => editor ? editor.getValue() : "",
      async validate(answer) {
        const button = $(".b-check", wrap), output = $(".lab-out", wrap);
        button.disabled = true; button.textContent = "INSCRIBING…";
        output.classList.remove("hidden");
        output.textContent = runLabel() + " — the forge takes your inscription…";
        let data;
        try { data = await apiJson("/api/runsnippet", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ code: answer, stdin: exercise.stdin || "" }) }); }
        catch (error) { data = { ok: false, output: "server error: " + (error.message || error) }; }
        button.disabled = false; button.textContent = "INSCRIBE + CAST";
        output.textContent = data.output || "(the stone stays silent)";
        if (!data.ok) return { passed: false, message: "THE FORGE REJECTED IT — read its complaint, mend the inscription, cast again (no penalty)" };
        const passed = exercise.expectRe ? new RegExp(exercise.expectRe, "m").test(data.output)
          : normCode(data.output) === normCode(exercise.expect || "");
        if (passed) return { passed: true };
        const difference = exercise.expectRe ? null : firstDiff(data.output, exercise.expect || "");
        return { passed: false, message: difference
          ? `IT CASTS, BUT LINE ${difference.line} differs: expected «${difference.expected}» got «${difference.got}»${difference.hint}`
          : "IT CASTS, BUT THE UTTERANCE DOES NOT MATCH THE TARGET" };
      },
    };
  },
};
