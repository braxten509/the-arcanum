/* THE BINDER'S LEDGER — past runs: the review reports written to reviews/ and the
   finished builds recorded in the amendment log. The job store is in memory, so this
   is the only place a completed run's report and price survive a reload.

   It takes over the whole output pane, so the button that opened it is the only way
   back out — while it is open that button reads RETURN. */
import { $, esc, mdLite, toast } from "../../core/dom.js";
import { apiFetch } from "../../core/api-client.js";
import { binderCost, binderHistory, buildDate, reviewDate } from "./view.js";

export const REVIEW_FIX_REQUEST = "Implement the selected review's complete Recommendation and implementation order. Address every material remediation that is in scope, in dependency-aware order; do not substitute minor cleanup for critical work. Preserve existing progress-keyed IDs unless Okay to reset progress is selected. Run the required validator and report any genuinely out-of-scope release or migration work.";

const OPEN_LABEL = "PAST RUNS";

/* ctx: { root, out, historyBtn, qBox, setReviewApplication, showSend, clearModes,
          resumeBuild, confirm } */
export function binderLedger(ctx) {
  const { root, out, historyBtn, qBox } = ctx;
  let lastReview = "";     // selected survey, fed to the next commissioned change
  let benchOutput = null;  // the working view the ledger covered, given back on RETURN

  const enterLedger = () => {
    if (benchOutput === null)
      benchOutput = out.classList.contains("hidden") ? "" : out.innerHTML;
    out.classList.remove("hidden");
    // The working view is preformatted; a rendered report and a row list are not.
    out.classList.add("binder-review-mode");
    root.classList.add("binder-past-review-mode");
    // Nothing on the list is sendable — a finished build is a receipt, not a pending
    // request — so the quill goes away until either a review is picked or RETURN is used.
    ctx.showSend(false);
    historyBtn.textContent = "RETURN";
    historyBtn.onclick = leaveLedger;
  };

  const leaveLedger = () => {
    out.innerHTML = benchOutput || "";
    out.classList.toggle("hidden", !benchOutput);
    benchOutput = null;
    out.classList.remove("binder-review-mode");
    // A selected review keeps the focused controls: applying it is still the pending action.
    root.classList.toggle("binder-past-review-mode", !!lastReview);
    ctx.showSend(true);
    historyBtn.textContent = OPEN_LABEL;
    historyBtn.onclick = showReviewHistory;
    qBox.focus();
  };

  const showReview = async (path) => {
    enterLedger();
    out.innerHTML = `<div class="binder-activity-empty">Opening the review ledger…</div>`;
    try {
      const response = await apiFetch("/api/amend/reviews?path=" + encodeURIComponent(path));
      const review = await response.json();
      if (!response.ok || !review.content) throw new Error("that review could not be read");
      lastReview = review.path;
      ctx.setReviewApplication(true);
      ctx.showSend(true);   // a picked review IS a pending request; the quill comes back
      if (!qBox.value.trim()) qBox.value = REVIEW_FIX_REQUEST;
      out.innerHTML = `<div class="binder-review-selected">
          <div><span>PAST REVIEW SELECTED</span><b>${esc(reviewDate(review.createdAt))}</b></div>
          <p>The next Binder request will consult this report. Describe the fixes above; Broad change governs how far the quill reaches.</p>
          <button class="btn quiet binder-review-back" type="button">BACK TO REVIEWS</button>
        </div>
        <div class="binder-review-document">${mdLite(review.content)}</div>
        ${binderCost(review.apiCostEstimate)
          || `<div class="binder-cost-unavailable">API-equivalent cost unavailable for this older review.</div>`}`;
      $(".binder-review-back", out).onclick = () => showReviewHistory();
      out.scrollTop = 0;
      qBox.focus();
    } catch (error) {
      out.innerHTML = `<div class="binder-review-empty">Could not open that review: ${esc(String(error.message || error))}</div>`;
    }
  };

  // Only an unfinished run can be dropped, and only after a confirmation: the row is the
  // one surviving record of a run that cost real money, and it cannot be got back.
  const forgetBuild = (row) => {
    if (!row) return;
    ctx.confirm({
      tag: "THE BINDER // A RUN IS STRUCK FROM THE LEDGER",
      title: "Delete this unfinished run?",
      detail: `The ${row.status === "error" ? "failed" : "stopped"} ${row.mode || "amend"} run from ${buildDate(row.finishedAt)} will be struck from the ledger — its feed, its price, and the request that started it go with it, and it can no longer be resumed. Your tome is not touched.`,
      confirmLabel: "DELETE THE RECORD",
      onConfirm: async () => {
        try {
          const response = await apiFetch("/api/amend/forget", {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ id: row.jobId }),
          });
          const result = await response.json();
          if (!response.ok || !result.ok) throw new Error(result.error || "the server kept the record");
          showReviewHistory();
        } catch (error) {
          toast("Could not delete that run: " + esc(String(error.message || error)), "bad");
        }
      },
    });
  };

  const showReviewHistory = async () => {
    enterLedger();
    ctx.setReviewApplication(false);
    lastReview = "";
    ctx.clearModes();
    out.innerHTML = `<div class="binder-activity-empty">Reading the review ledger…</div>`;
    try {
      const response = await apiFetch("/api/amend/reviews");
      const payload = await response.json();
      if (!response.ok) throw new Error("the review ledger could not be read");
      out.innerHTML = binderHistory(payload);
      out.querySelectorAll("[data-review-path]").forEach((button) => {
        button.onclick = () => showReview(button.dataset.reviewPath);
      });
      // A build has no report file to open, so the row carries its own record: one
      // click unfolds what it changed and what the tokens would have cost.
      out.querySelectorAll(".binder-build-row").forEach((button) => {
        button.onclick = () => {
          const open = button.getAttribute("aria-expanded") === "true";
          button.setAttribute("aria-expanded", String(!open));
          button.nextElementSibling.classList.toggle("hidden", open);
        };
      });
      const build = (id) => (payload.builds || []).find((row) => row.jobId === id);
      out.querySelectorAll(".binder-build-resume").forEach((button) => {
        button.onclick = () => {
          const row = build(button.dataset.job);
          if (row && row.setup) ctx.resumeBuild({ ...row.setup, status: row.status });
        };
      });
      out.querySelectorAll(".binder-build-forget").forEach((button) => {
        button.onclick = () => forgetBuild(build(button.dataset.job));
      });
      out.scrollTop = 0;
    } catch (error) {
      out.innerHTML = `<div class="binder-review-empty">Could not read past reviews: ${esc(String(error.message || error))}</div>`;
    }
  };

  return {
    open: showReviewHistory,
    selected: () => lastReview,
    select: (path) => { lastReview = path || ""; },
    // A run's own output is the working view now, so the ledger lets go of all of it.
    reset: () => {
      benchOutput = null;
      out.classList.remove("binder-review-mode");
      root.classList.remove("binder-past-review-mode");
      ctx.showSend(true);
      historyBtn.textContent = OPEN_LABEL;
      historyBtn.onclick = showReviewHistory;
    },
  };
}
