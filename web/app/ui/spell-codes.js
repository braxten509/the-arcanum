/* Pure spell-code parsing, kept separate so command syntax stays deterministic and testable. */
export function parseSpellCode(raw) {
  const code = String(raw || "").trim().toLowerCase();
  if (code === "unlock-all") return { kind: "unlock-all" };
  if (code === "lock-all") return { kind: "lock-all" };
  if (code === "disable-hex") return { kind: "disable-hex" };
  if (code === "enable-hex") return { kind: "enable-hex" };
  if (code === "reset-progress") return { kind: "reset-progress" };

  const gold = code.match(/^gold-(\d+)$/);
  if (gold) {
    const amount = Number(gold[1]);
    if (Number.isSafeInteger(amount) && amount > 0) return { kind: "gold", amount };
  }
  return { kind: "unknown" };
}
