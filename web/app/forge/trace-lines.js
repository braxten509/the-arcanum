const DURABLE_LINE = /^((?:(?:VALIDATOR COMMAND|AI VALIDATOR CALL) (?:START|COMPLETE|FAILED)|(?:AI API-EQUIVALENT COST COMPLETE|GPT API-EQUIVALENT COST COMPLETE)))\s+\[([0-9]+(?:\.[0-9]+)?)\](.*)$/;
const GPT_COST_LINE = /^(?:AI API-EQUIVALENT COST COMPLETE|GPT API-EQUIVALENT COST COMPLETE) \[([0-9]+(?:\.[0-9]+)?)\] › PHASE ([1-8]) (?:(?:SECTION ([A-Za-z0-9_-]+))|TOTAL)\b/;
const CLOCK_LINE = /^(\d{2}):(\d{2}):(\d{2})\b/;
const MERGED_TRACE_LINES = 600;
const WEEKLY_USAGE_USD_PER_PERCENT = 1.4;

function localClock(milliseconds) {
  const date = new Date(milliseconds);
  return [date.getHours(), date.getMinutes(), date.getSeconds()]
    .map((part) => String(part).padStart(2, "0")).join(":");
}

function clockNear(line, anchor) {
  const match = String(line).match(CLOCK_LINE);
  if (!match) return null;
  const date = new Date(anchor);
  date.setHours(Number(match[1]), Number(match[2]), Number(match[3]), 0);
  // A 23:xx event viewed just after midnight belongs to the preceding day.
  if (date.getTime() > anchor + 5 * 60 * 1000) date.setDate(date.getDate() - 1);
  return date.getTime();
}

function durableEntry(line) {
  const match = String(line).match(DURABLE_LINE);
  if (!match) return null;
  const at = Number(match[2]) * 1000;
  if (!Number.isFinite(at)) return null;
  return { at, line: `${localClock(at)}  ${match[1]}${match[3]}` };
}

function formatCostConversationText(text) {
  let visible = String(text || "")
    .replace(/ \[[0-9]+(?:\.[0-9]+)?\](?=\s*›)/, "")
    .replace(/^(?:AI API-EQUIVALENT COST COMPLETE|GPT API-EQUIVALENT COST COMPLETE)\b\s*›\s*/i, "")
    .replace(/^PHASE ([1-8]) SECTION ([A-Za-z0-9_-]+)\b/, "Phase $1 section $2")
    .replace(/^PHASE ([1-8]) TOTAL\b/, "Phase $1 total")
    .replace(/· SUM OF ([0-9]+) SECTIONS?\b/, (_match, count) =>
      `· sum of ${count} ${count === "1" ? "section" : "sections"}`)
    .replace(/\bUNAVAILABLE\b/, "Unavailable")
    .replace(/· PARTIAL: ([0-9]+) (?:AI|GPT) TURNS? LACKED TOKEN USAGE\b/, (_match, count) =>
      `· Partial: ${count} AI ${count === "1" ? "turn" : "turns"} lacked token usage`);
  if (/\([^)]*weekly usage\)/i.test(visible)) return visible;
  const amount = visible.match(/\$([0-9]+(?:\.[0-9]+)?)(\+)?(?=\s|$)/);
  if (amount) {
    const weekly = formatForgeWeeklyUsage({ displayUsd: Number(amount[1]), gptPricedTurns: 1 });
    visible = visible.replace(amount[0], `${amount[0]} ${weekly}`);
  } else if (/›\s*Unavailable\b/.test(visible)) {
    visible = visible.replace(/\bUnavailable\b/, "Unavailable (weekly usage unavailable)");
  }
  return visible;
}

function costConversationEntry(line) {
  const match = String(line).match(GPT_COST_LINE);
  if (!match) return null;
  const at = Number(match[1]);
  if (!Number.isFinite(at)) return null;
  return { at, kind: "harness", text: formatCostConversationText(line),
    eventKey: `gpt-cost:${match[2]}:${match[3] || "total"}` };
}

function normalizeCostConversationRow(row) {
  if (!String(row?.eventKey || "").startsWith("gpt-cost:")) return row;
  const text = formatCostConversationText(row?.text);
  return text === row?.text ? row : { ...row, text };
}

/** Return the visual result state only for explicit harness validation verdicts. */
export function forgeHarnessValidationState(row) {
  if (String(row?.kind || "").toLowerCase() !== "harness"
      || String(row?.eventKey || "").startsWith("gpt-cost:")) return "";
  const text = String(row?.text || "").trimStart();
  if (/^Validation passed\b/i.test(text)) return "pass";
  if (/^Validation failed\b/i.test(text)) return "fail";
  return "";
}

/** Add GPT completion totals to the same chronological conversation the operator watches. */
export function mergeForgeConversationCosts(conversation, logtail) {
  const costs = String(logtail || "").split("\n")
    .map(costConversationEntry).filter(Boolean);
  const costKeys = new Set(costs.map((row) => row.eventKey));
  const rows = (Array.isArray(conversation) ? conversation : [])
    .filter((row) => !costKeys.has(row?.eventKey))
    .map((row, index) => ({ row: normalizeCostConversationRow(row), index }));
  costs.forEach((row, offset) => rows.push({ row, index: rows.length + offset }));
  rows.sort((left, right) => Number(left.row?.at || 0) - Number(right.row?.at || 0)
    || left.index - right.index);
  return rows.slice(-160).map(({ row }) => row);
}

function visibleCostUnit(row) {
  const key = String(row?.eventKey || "");
  if (!/^gpt-cost:[1-8]:(?:total|[A-Za-z0-9_-]+)$/.test(key)) return null;
  const amount = String(row?.text || "").match(/›\s*\$([0-9]+(?:\.[0-9]+)?)(\+)?(?:\s|$)/);
  const unavailable = /›\s*Unavailable\b/i.test(String(row?.text || ""));
  if (!amount && !unavailable) return null;
  const [, phase, unit] = key.split(":");
  return { key, phase: Number(phase), unit,
    cents: amount ? Math.round(Number(amount[1]) * 100) : 0,
    priced: Boolean(amount), partial: Boolean(amount?.[2]) || unavailable };
}

/** Old-server fallback: sum durable completion events until structured status is available. */
export function fallbackForgeRunningCost(conversation, logtail) {
  const latest = new Map();
  mergeForgeConversationCosts(conversation, logtail).forEach((row) => {
    const unit = visibleCostUnit(row);
    if (unit) latest.set(unit.key, unit);
  });
  const selected = [];
  for (let phase = 1; phase <= 8; phase += 1) {
    const total = latest.get(`gpt-cost:${phase}:total`);
    if (phase !== 3) { if (total) selected.push(total); continue; }
    if (total) selected.push(total);
    else selected.push(...[...latest.values()].filter((row) => row.phase === 3));
  }
  if (!selected.length) return null;
  const priced = selected.some((row) => row.priced);
  const partial = selected.some((row) => row.partial);
  return {
    gptTurnCount: priced && partial ? 2 : 1,
    gptPricedTurns: priced ? 1 : 0,
    gptUnpricedTurns: partial ? 1 : 0,
    gptPricingComplete: !partial,
    displayUsd: selected.reduce((sum, row) => sum + row.cents, 0) / 100,
    completionEventFallback: true,
  };
}

export function formatForgeRunningCost(report) {
  if (!report || Number(report.gptPricedTurns || 0) <= 0) return "UNAVAILABLE";
  const amount = Number(report.displayUsd || 0);
  return `$${Number.isFinite(amount) ? amount.toFixed(2) : "0.00"}`;
}

export function formatForgeWeeklyUsage(report) {
  if (!report || Number(report.gptPricedTurns || 0) <= 0) {
    return "(weekly usage unavailable)";
  }
  const amount = Number(report.displayUsd || 0);
  const percent = Number.isFinite(amount) ? amount / WEEKLY_USAGE_USD_PER_PERCENT : 0;
  return `(${percent.toFixed(2)}% weekly usage)`;
}

/** Merge provider tool calls and durable harness events into one chronological terminal feed. */
export function mergeForgeTraceLines(toolLines, logtail, anchor = Date.now()) {
  const durableLines = String(logtail || "").split("\n")
    .filter((line) => /^(?:(?:VALIDATOR COMMAND|AI VALIDATOR CALL) (?:START|COMPLETE|FAILED)|(?:AI API-EQUIVALENT COST COMPLETE|GPT API-EQUIVALENT COST COMPLETE))\b/.test(line));
  const rows = [...(Array.isArray(toolLines) ? toolLines : []), ...durableLines]
    .map((line, index) => {
      const durable = durableEntry(line);
      return { index, line: durable?.line || String(line),
        at: durable?.at ?? clockNear(line, anchor) };
    });
  rows.sort((left, right) => {
    if (left.at == null && right.at == null) return left.index - right.index;
    if (left.at == null) return 1;
    if (right.at == null) return -1;
    return left.at - right.at || left.index - right.index;
  });
  // The provider contributes up to 80 tool rows while the durable harness contributes
  // up to 500 status rows. Keep both budgets so author traffic cannot evict validators or costs.
  return rows.slice(-MERGED_TRACE_LINES).map((row) => row.line);
}
