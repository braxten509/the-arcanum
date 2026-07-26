import { esc, mdLite } from "../../core/dom.js";

export const binderStamp = (value) => {
  const raw = Number(value);
  if (!Number.isFinite(raw)) return null;
  const date = new Date(raw < 1e12 ? raw * 1000 : raw);
  if (Number.isNaN(date.getTime())) return null;
  return {
    iso: date.toISOString(),
    label: date.toLocaleTimeString([], {
      hour: "2-digit", minute: "2-digit", second: "2-digit",
    }),
  };
};

export const binderActivity = (rows) => {
  const activity = Array.isArray(rows) ? rows : [];
  if (!activity.length)
    return `<div class="binder-activity-empty">Waiting for the Binder's first tool call…</div>`;
  return activity.map((row) => {
    const stamp = binderStamp(row.at);
    return row.kind === "tool"
      ? `<div class="binder-activity-tool">${esc(row.text || "")}</div>`
      : `<div class="binder-activity-chat ${esc(row.kind || "assistant")}">
        <div class="binder-activity-meta">
          <span class="binder-activity-role">${row.kind === "harness" ? "HARNESS" : "BINDER"}</span>
          ${stamp ? `<time datetime="${esc(stamp.iso)}">${esc(stamp.label)}</time>` : ""}
        </div>
        <div class="binder-activity-copy">${esc(row.text || "")}</div>
      </div>`;
  }).join("");
};

const costLabel = (estimate) => {
  const usd = Number(estimate?.usd);
  return Number.isFinite(usd)
    ? `$${usd > 0 && usd < .01 ? usd.toFixed(4) : usd.toFixed(2)} EST.`
    : "COST UNAVAILABLE";
};

export const binderCost = (estimate) => {
  const usd = Number(estimate?.usd);
  if (!Number.isFinite(usd) || usd < 0) return "";
  const usage = estimate.usage || {};
  const compact = (value) => Number(value || 0) >= 1000000
    ? `${(Number(value) / 1000000).toFixed(1)}M`
    : Number(value || 0) >= 1000
      ? `${(Number(value) / 1000).toFixed(1)}K`
      : String(Number(value || 0));
  const amount = usd > 0 && usd < .01 ? usd.toFixed(4) : usd.toFixed(2);
  const provider = estimate.provider === "claude-cli" ? "CLAUDE" : "CODEX";
  return `<div class="binder-cost" title="Estimated from reported CLI token usage and the shared ${esc(estimate.pricingVersion || "current")} API pricing table. This is not a charge from the CLI.">
    <span>API-EQUIVALENT ESTIMATE · ${provider} · ${esc(estimate.model || "")}</span>
    <b>$${amount}</b>
    <small>${compact(usage.freshInputTokens)} fresh · ${compact(usage.cachedInputTokens)} cached · ${compact(usage.cacheWriteTokens)} cache write · ${compact(usage.outputTokens)} output · CLI charge not included</small>
  </div>`;
};

export const reviewDate = (stamp) => {
  const value = String(stamp || "");
  if (!/^\d{14}$/.test(value)) return "UNDATED REVIEW";
  const date = new Date(
    `${value.slice(0, 4)}-${value.slice(4, 6)}-${value.slice(6, 8)}T`
    + `${value.slice(8, 10)}:${value.slice(10, 12)}:${value.slice(12, 14)}`);
  return Number.isNaN(date.getTime())
    ? "UNDATED REVIEW"
    : date.toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
};

export const buildDate = (seconds) => {
  const date = new Date(Number(seconds) * 1000);
  return Number.isNaN(date.getTime())
    ? "UNDATED BUILD"
    : date.toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
};

const listHead = (label, count, noun) =>
  `<div class="binder-review-list-head"><span>${label}</span>
    <b>${count} ${noun}${count === 1 ? "" : "S"}</b></div>`;

const buildRow = (build) => {
  const ok = build.status === "done" && build.validatorOk !== false;
  const line = [
    ok ? "" : String(build.status === "done" ? "flaws found" : build.status).toUpperCase(),
    (build.mode || "amend").toUpperCase(),
    (build.apiCostEstimate?.model || "model not recorded").toUpperCase(),
    build.continuations > 0
      ? `${build.continuations} CONTINUATION${build.continuations === 1 ? "" : "S"}` : "",
  ].filter(Boolean).join(" · ");
  // A run that never finished can be taken up again, so its record carries the feed it
  // reached and the request that started it. A finished run has neither: its edit is on
  // disk, and the ledger is the only proof of who made it.
  const feed = build.unfinished && Array.isArray(build.activity) && build.activity.length
    ? `<div class="binder-build-feed"><b>WHERE IT STOPPED</b>
        <div class="binder-build-feed-body">${binderActivity(build.activity)}</div></div>`
    : "";
  const job = esc(build.jobId || "");
  const actions = build.unfinished
    ? `<div class="binder-build-actions">
        <button class="btn quiet binder-build-forget" type="button" data-job="${job}"
          title="Remove this unfinished run from the ledger. The tome is not touched.">DELETE</button>
        <button class="btn binder-build-resume" type="button" data-job="${job}"${
          build.setup ? "" : ` disabled title="This run finished before the ledger recorded requests, so there is nothing to take up again."`}>RESUME</button>
      </div>`
    : "";
  return `<div class="binder-build${ok ? "" : " bad"}">
    <button class="binder-review-row binder-build-row" type="button" aria-expanded="false">
      <span><b>${esc(buildDate(build.finishedAt))}</b><small>${esc(line)}</small></span>
      <em>${esc(costLabel(build.apiCostEstimate))}</em>
    </button>
    <div class="binder-build-detail hidden">
      ${mdLite(build.summary || build.error || "(this build reported nothing)")}
      ${build.validator ? `<pre class="binder-build-validator">${esc(build.validator)}</pre>` : ""}
      ${feed}
      ${binderCost(build.apiCostEstimate)}
      ${actions}
    </div>
  </div>`;
};

export const binderHistory = (payload) => {
  const reviews = Array.isArray(payload.reviews) ? payload.reviews : [];
  const builds = Array.isArray(payload.builds) ? payload.builds : [];
  if (!reviews.length && !builds.length)
    return `<div class="binder-review-empty"><b>THE LEDGER IS EMPTY</b>
      <span>Run Review or commission a change once, and its report — with what it cost — will appear here.</span></div>`;
  return (reviews.length
    ? listHead("PAST REVIEWS", reviews.length, "REPORT")
      + `<div class="binder-review-list">${reviews.map((review) =>
        `<button class="binder-review-row" type="button" data-review-path="${esc(review.path)}">
          <span><b>${esc(reviewDate(review.createdAt))}</b><small>${esc(
            review.providerModel || "MODEL NOT RECORDED")}</small></span>
          <em>${esc(costLabel(review.apiCostEstimate))}</em>
        </button>`).join("")}</div>`
    : "")
    + (builds.length
      ? `<div class="binder-build-section">${listHead("PAST BUILDS", builds.length, "BUILD")}
        <div class="binder-review-list">${builds.map(buildRow).join("")}</div></div>`
      : "");
};

export function binderTemplate() {
  return `<h2>THE BINDER</h2>
    <p class="dim" id="binder-desc">Name one small flaw in this tome — a typo, a wrong color, a price, a missing line —
    and the Binder's spirit will re-ink the page. It edits the course itself, so be specific. Ask a question instead and it will just answer, with no edits made.</p>
    <div id="binder-inputs">
    <textarea id="binder-q" rows="3" style="width:100%" placeholder="e.g. the s02-l03 hint has a typo · make the signature theme's accent more copper · rename the SLAG SHIELD to CINDER WARD"></textarea>
    <div style="display:flex;align-items:center;gap:20px;margin-top:10px;flex-wrap:wrap">
      <label class="forge-check" id="bd-publish-wrap" style="margin:0" title="Rounds of independent survey and repair until the tome clears publisher.md — the publication bar — and the harness's own shipping gate together. It runs alone: no other option applies, and it never resets progress."><input type="checkbox" id="bd-publish"> Make ready to publish</label>
      <label class="forge-check" id="bd-broad-wrap" style="margin:0"><input type="checkbox" id="bd-broad"> Broad change</label>
      <label class="forge-check hidden" id="bd-standard-wrap" style="margin:0" title="Also align the tome with the repository's current validator and Markdown authoring instructions. The Binder cannot complete until strict validation passes; already-current files are left alone. A tome finished before the harness sealed build plans also has its plan, course map, and continuity handoffs adopted from what it already contains — that is what puts it under the full shipping gate."><input type="checkbox" id="bd-standard"> Update to Standard</label>
      <label class="forge-check" id="bd-review-wrap" style="margin:0" title="The Binder reads the tome without changing it and writes its findings to the reviews/ ledger."><input type="checkbox" id="bd-review"> Review</label>
      <label class="forge-check hidden" id="bd-iterate-wrap" style="margin:0"><input type="checkbox" id="bd-iterate"> Iterate</label>
      <label class="forge-check hidden" id="bd-reset-wrap" style="margin:0" title="Lets the Binder add, remove, reorder, or rename chapters and lessons — restructuring the tome. This RESETS all player progress for this tome."><input type="checkbox" id="bd-reset"> Okay to reset progress?</label>
    </div>
    <p class="hidden" id="bd-reset-warn" style="color:var(--bad,#c66);font-size:11.5px;margin:6px 0 0">⚠ The Binder may restructure this tome — every artificer's progress on it will be reset.</p>
    <div class="forge-field" style="margin-top:10px"><label>THE BINDER'S HAND</label>
      <div class="forge-ai-row">
        <div class="forge-ai-choice"><select id="bd-prov" class="cfg-select" aria-label="Binder agent CLI"><option value="">PICK A MODEL</option></select></div>
        <div class="forge-ai-choice"><select id="bd-model" class="cfg-select" aria-label="Binder model" disabled><option value="">—</option></select></div>
        <div class="forge-ai-choice"><select id="bd-eff" class="cfg-select" aria-label="Binder effort" disabled><option value="">—</option></select></div>
      </div></div>
    <details class="binder-rebuild" id="bd-rebuild">
      <summary><span>RESET THE BUILD TO A PHASE</span><b>DESTRUCTIVE</b></summary>
      <div class="binder-rebuild-body">
        <div class="binder-rebuild-pick">
          <label for="bd-phase">START THE REBUILD AT</label>
          <select id="bd-phase" class="cfg-select">
            <option value="">CHOOSE PHASE</option>
            <option value="1">1 · CONCEPT &amp; ARC</option>
            <option value="2">2 · SKELETON &amp; VOICE</option>
            <option value="3">3 · SECTIONS</option>
            <option value="4">4 · MINIGAMES</option>
            <option value="5">5 · ECONOMY</option>
            <option value="6">6 · COSMETICS</option>
            <option value="7">7 · VALIDATE</option>
            <option value="8">8 · STUDENT REVIEW</option>
          </select>
        </div>
        <div class="binder-rebuild-consequence hidden" id="bd-phase-warn" aria-live="polite"></div>
        <label class="binder-rebuild-ack hidden" id="bd-phase-ack-wrap">
          <input type="checkbox" id="bd-phase-ack">
          <span>I understand that learner progress and later tome work will be erased.</span>
        </label>
        <button class="btn danger binder-rebuild-go" id="bd-phase-go" type="button" disabled>RESET AND REBUILD</button>
        <div class="binder-rebuild-error hidden" id="bd-phase-error" role="alert"></div>
      </div>
    </details>
    </div>
    <div id="binder-a" class="hidden" style="margin-top:12px;padding:12px;border:1px solid var(--line-hi);border-left:2px solid var(--ac-dim);border-radius:3px;font-size:12.5px;white-space:pre-wrap;max-height:45vh;overflow-y:auto"></div>`;
}
