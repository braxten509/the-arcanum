import { esc } from "../../core/dom.js";

export function fieldHead(label, help) {
  return `<div class="forge-lbl"><label>${label}</label><button type="button" class="forge-help"
    aria-label="About ${esc(label)}">i<span class="forge-tip">${help}</span></button></div>`;
}

/** "" = resume, "3" = whole phase, "3:s05" = one Phase-3 section onward. */
export function restartPoint(value) {
  const [phase, section] = String(value || "").split(":");
  return { phase: Number(phase) || 0, section: section || "" };
}
