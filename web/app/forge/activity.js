// Compact, human-readable activity for the live forge card. The harness keeps a
// diagnostic log; this module turns its trusted status signals into one rotating line.
const FORGE_STATUS_RE = /^(?:>\s*Phase\s+\d+\s+—|===\s*Phase\s+0\b|·\s*(?:AI access Phase 0|forecast:|reset tomes\/|split-sections:|Phase 3 (?:full gate|resume)|(?:authoring|resuming)\s+warm batch|(?:authoring|resuming|section)\s+s\d+|shrinkage justified|renamed tomes\/|liveness ping)|ok(?:\s{2,}|\s+(?:plan\b|validate_tome\b|section\b))|FAIL\s+|!\s*(?:runner|worker|section|warm batch|Phase|naming)\b|x\s*(?:gates failed|Phase|section|warm batch)\b|⇒\s+|↻\s+|~\s*(?:student verdict|Phase 8)\b|⏸\s*phase\b|==\s*all phases complete\b|AI ACCESS PHASE 0 FAILED\b|->\s*wrote\b)/;

const PHASE_ACTIVITY = [
  ["Recording the course brief", "Checking the gate answers"],
  ["Mapping the course arc", "Checking the learning progression", "Planning the final project path"],
  ["Building the lesson skeleton", "Setting the narrative voice", "Checking the project structure"],
  ["Writing lessons and exercises", "Checking continuity between sections", "Advancing the course project"],
  ["Designing the minigames", "Binding challenges to lesson skills"],
  ["Balancing rewards and costs", "Checking the progression curve"],
  ["Crafting badges and themes", "Matching cosmetics to mastery"],
  ["Running structural validation", "Repairing validation findings"],
  ["Reviewing the tome as a student", "Checking clarity and completeness", "Repairing review findings"],
];

export function forgeStatusLines(raw) {
  return String(raw || "").split("\n").map((line) => line.trim())
    .filter((line) => FORGE_STATUS_RE.test(line)).slice(-40);
}

export function forgeStatusTail(raw) {
  return forgeStatusLines(raw).join("\n");
}

export function forgeTraceLines(raw) {
  const values = Array.isArray(raw) ? raw : String(raw || "").split("\n");
  return values.map((line) => String(line).trim()).filter(Boolean).slice(-3);
}

export function forgeTraceSectionProgress(st = {}) {
  const totalMatch = String(st.sections || "").match(/\/(\d+)\b/)
    || String(st.logtail || "").match(/forecast:\s*(\d+)\s+sections\b/i);
  const total = totalMatch ? Number(totalMatch[1]) : 0;
  if (Number(st.phase) !== 3 || total < 1) return null;

  const writesSection = /\b(?:write|edit|patch|apply_patch|write_file|replace|replace_file_content|multi_replace_file_content)\s*›[\s\S]*?[\\/]sections[\\/](s\d+)\b/i;
  const lines = forgeTraceLines(st.toolTrace);
  for (let i = lines.length - 1; i >= 0; i -= 1) {
    const match = lines[i].match(writesSection);
    if (!match) continue;
    const section = match[1].toLowerCase();
    const index = Number(section.slice(1));
    if (index >= 1 && index <= total)
      return { section, index, total, state: "authoring", inferred: true };
  }
  return null;
}

function latestPhaseStatus(raw, phase) {
  const lines = forgeStatusLines(raw);
  const phaseHeader = new RegExp(`^>\\s*Phase\\s+${Number(phase) || 0}\\b`);
  let start = -1;
  lines.forEach((line, i) => { if (phaseHeader.test(line)) start = i; });
  const current = start >= 0 ? lines.slice(start) : lines;
  return current[current.length - 1] || "";
}

function runnerLabel(runner) {
  return String(runner || "")
    .replace(/^(?:claude|codex|antigravity|opencode)-cli\s+/, "")
    .replace(/\s+@\w+$/, "")
    .trim();
}

export function describeForgeStatus(line, st = {}) {
  if (!line) return "";
  const phase = Number(st.phase) || 0;
  let m;
  if ((m = line.match(/^>\s*Phase\s+\d+\s+—\s*(.+?)(?:\s+\[runner|$)/)))
    return `Beginning ${m[1].trim()}`;
  if ((m = line.match(/^x\s*gates failed.*?attempt\s+(\d+)/)))
    return `The gates found issues — repairing phase ${phase} (attempt ${m[1]})`;
  if (/^ok\s+validate_tome:\s*clean/.test(line))
    return "Validation is clean — preparing the next phase";
  if (/^ok\s+plan Arc written/.test(line))
    return "The course arc is written — checking it";
  if ((m = line.match(/^·\s*(authoring|resuming)\s+(s\d+)\s+\[(\d+)\/(\d+)\]/)))
    return `${m[1] === "resuming" ? "Resuming" : "Authoring"} ${m[2]} — section ${m[3]} of ${m[4]}`;
  if ((m = line.match(/^·\s*(authoring|resuming)\s+warm batch\s+(\d+)\/(\d+)\s+\[(\d+)-(\d+)\/(\d+)\]/)))
    return `${m[1] === "resuming" ? "Resuming" : "Authoring"} warm batch ${m[2]} of ${m[3]} — sections ${m[4]}–${m[5]} of ${m[6]}`;
  if ((m = line.match(/^·\s*section\s+(s\d+)\s+\[(\d+)\/(\d+)\].*already authored/)))
    return `${m[1]} is already complete — moving to section ${m[2]} of ${m[3]}`;
  if (/^·\s*split-sections:/.test(line))
    return "Preparing bounded warm section batches";
  if (/^·\s*Phase 3 full gate is clean/.test(line))
    return "The complete course gate is clean — skipping reconciliation";
  if (/^·\s*Phase 3 resume gate is already clean/.test(line))
    return "The saved Phase 3 gate is clean — no replacement worker needed";
  if ((m = line.match(/^·\s*Phase 3 resume:\s*(\d+) incomplete section/)))
    return `Resuming only ${m[1]} incomplete section${m[1] === "1" ? "" : "s"}`;
  if (/^·\s*Phase 3 resume is final-gate repair only/.test(line))
    return "Sections are complete — repairing only the final course gate";
  if (/^·\s*renamed tomes\//.test(line))
    return "Naming and filing the new tome";
  if (/^·\s*AI access Phase 0:\s*checking/.test(line))
    return "Checking access to the selected models";
  if (/^·\s*AI access Phase 0:\s*all selected endpoints answer/.test(line))
    return "All selected models answered — beginning the work";
  if (/^FAIL\s+/.test(line) || /^AI ACCESS PHASE 0 FAILED/.test(line))
    return "A selected model did not answer";
  if (/^ok\s{2,}/.test(line))
    return "A selected model answered";
  if (/^->\s*wrote\b/.test(line))
    return "The course brief is recorded";
  if (/^===\s*Phase 0\b/.test(line))
    return "Recording the course brief";
  if (/^⇒\s+/.test(line))
    return "Switching hands and resuming this phase";
  if (/^↻\s+/.test(line))
    return "Resuming this phase with more repair attempts";
  if (/^⏸\s*phase\b/.test(line))
    return "Waiting for you to choose a new hand";
  if (/^!\s*(?:runner|worker|section|warm batch)\b/.test(line))
    return "The current hand stopped — preparing recovery";
  if (/^·\s*liveness ping/.test(line))
    return "Checking that the current hand is responsive";
  if (/^~\s*student verdict/.test(line))
    return "Student review found gaps — beginning another pass";
  if (/^~\s*Phase 8/.test(line))
    return "Changes were made — scheduling a fresh review";
  if (/^x\s*section\b/.test(line))
    return "Section checks found issues — repairing them";
  if (/^x\s*warm batch\b/.test(line))
    return "Batch checks found issues — repairing only the failed sections";
  if (/^!\s*Phase\b/.test(line) || /^x\s*Phase\b/.test(line))
    return `Phase ${phase} needs another repair pass`;
  if (/^·\s*forecast:/.test(line))
    return "Measuring the authored course";
  if (/^·\s*shrinkage justified/.test(line))
    return "Checking an intentional content revision";
  return "";
}

export function forgeActivityKey(st = {}) {
  const latest = latestPhaseStatus(st.logtail, st.phase);
  const progress = st.sectionProgress || {};
  return [st.phase, st.sections || "", st.runner || "", st.awaitingRunner ? "waiting" : "",
    progress.section || "", progress.index || "", progress.total || "", progress.state || "",
    latest].join("\u0000");
}

export function forgeActivityOptions(st = {}) {
  if (st.awaitingRunner) return ["Waiting for you to choose a new hand"];

  const options = [];
  const progress = st.sectionProgress || {};
  if (Number(st.phase) === 3 && progress.section && progress.index && progress.total) {
    const action = ({ authoring: "Authoring", repairing: "Repairing", validating: "Validating",
      complete: "Completed" })[progress.state] || "Working on";
    options.push(`${action} ${progress.section} — section ${progress.index} of ${progress.total}`);
  }
  const latest = describeForgeStatus(latestPhaseStatus(st.logtail, st.phase), st);
  if (latest) options.push(latest);

  const phase = Math.max(0, Math.min(PHASE_ACTIVITY.length - 1, Number(st.phase) || 0));
  if (phase === 3 && st.sections && !progress.section) options.push(`Authoring section ${st.sections}`);
  options.push(...PHASE_ACTIVITY[phase]);

  const hand = runnerLabel(st.runner);
  if (hand) options.push(`${hand} is still working`);
  return [...new Set(options.filter(Boolean))];
}

export function forgeActivityLine(st = {}, index = 0) {
  const options = forgeActivityOptions(st);
  const activity = options[index % Math.max(1, options.length)] || "The bindery is working";
  const phase = Number.isFinite(Number(st.phase)) ? Number(st.phase) : 0;
  const total = Number(st.totalPhases) || 9;
  return `Phase ${phase} / ${total} — ${activity}`;
}
