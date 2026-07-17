const VALIDATOR_LINE = /^((?:VALIDATOR COMMAND|AI VALIDATOR CALL) (?:START|COMPLETE|FAILED))\s+\[([0-9]+(?:\.[0-9]+)?)\](.*)$/;
const CLOCK_LINE = /^(\d{2}):(\d{2}):(\d{2})\b/;

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

function validatorEntry(line) {
  const match = String(line).match(VALIDATOR_LINE);
  if (!match) return null;
  const at = Number(match[2]) * 1000;
  if (!Number.isFinite(at)) return null;
  return { at, line: `${localClock(at)}  ${match[1]}${match[3]}` };
}

/** Merge provider tool calls and harness validators into one chronological terminal feed. */
export function mergeForgeTraceLines(toolLines, logtail, anchor = Date.now()) {
  const validatorLines = String(logtail || "").split("\n")
    .filter((line) => /^(?:VALIDATOR COMMAND|AI VALIDATOR CALL) (?:START|COMPLETE|FAILED)\b/.test(line));
  const rows = [...(Array.isArray(toolLines) ? toolLines : []), ...validatorLines]
    .map((line, index) => {
      const validator = validatorEntry(line);
      return { index, line: validator?.line || String(line),
        at: validator?.at ?? clockNear(line, anchor) };
    });
  rows.sort((left, right) => {
    if (left.at == null && right.at == null) return left.index - right.index;
    if (left.at == null) return 1;
    if (right.at == null) return -1;
    return left.at - right.at || left.index - right.index;
  });
  return rows.slice(-80).map((row) => row.line);
}
