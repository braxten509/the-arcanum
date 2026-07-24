// Binder working view must consume filtered activity, never stream its raw log.
const fs = require("fs");
const assert = require("assert");
const path = require("path");

const root = path.join(__dirname, "..", "..", "..");
const source = [
  path.join(root, "web", "app", "forge", "binder.js"),
  path.join(root, "web", "app", "forge", "binder", "view.js"),
].map((file) => fs.readFileSync(file, "utf8")).join("\n");
const activityCss = fs.readFileSync(path.join(
  root, "web", "css", "overlay", "bindery", "binder-activity.css"), "utf8");
const amenderSource = [
  path.join(root, "arcanum", "authoring", "amender.py"),
  path.join(root, "arcanum", "authoring", "amendment", "runner.py"),
].map((file) => fs.readFileSync(file, "utf8")).join("\n");

assert(/(?:const|function) binderActivity(?: = \(rows\)|\(rows\))/.test(source),
  "Binder needs a dedicated filtered activity renderer");
assert(/st\.activity != null/.test(source),
  "Binder polling must render the filtered activity stream");
assert(!/mdLite\(st\.logtail/.test(source),
  "Binder must not stream raw CLI/tool output into the working view");
assert(!/st\.error \|\| st\.logtail/.test(source),
  "Binder failures must use the summarized error, not fall back to raw output");
assert(/row\.kind === "tool"/.test(source) && /HARNESS/.test(source) && /BINDER/.test(source),
  "Binder activity must distinguish calls from conversation");
assert(/(?:const|function) binderStamp(?: = \(value\)|\(value\))/.test(source) && /<time datetime=/.test(source),
  "Binder and Harness conversation cards must render upper-right timestamps");
assert(/(?:const|function) binderCost(?: = \(estimate\)|\(estimate\))/.test(source),
  "Binder completion view needs an API-equivalent cost renderer");
assert((source.match(/binderCost\(st\.apiCostEstimate\)/g) || []).length === 2,
  "both review and amendment completion views must display the estimate");
assert(/CLI charge not included/.test(source) && /actualCharge/.test(amenderSource),
  "the estimate must not be presented as an actual CLI charge");
assert(/historyBtn\.textContent = "PAST REVIEWS"/.test(source),
  "Binder actions need a Past Reviews button");
assert(/actions\.prepend\(sendBtn, historyBtn\)/.test(source),
  "Past Reviews must sit immediately to the right of Send to the Binder");
assert(/apiFetch\("\/api\/amend\/reviews/.test(source)
  && /lastReview = review\.path/.test(source)
  && /binderCost\(review\.apiCostEstimate\)/.test(source),
  "opening a past review must load its report, select it for fixes, and show cost");
assert((source.match(/out\.classList\.add\("binder-review-mode"\)/g) || []).length === 2,
  "both review-history views must opt out of the output pane's preformatted whitespace");
assert(/const REVIEW_FIX_REQUEST = "Implement the selected review's complete Recommendation/.test(source),
  "a selected review needs an explicit default remediation request");
assert(/const q = typedRequest \|\| \(lastReview \? REVIEW_FIX_REQUEST : ""\)/.test(source),
  "Send must treat a selected review as actionable when the textarea is empty");
assert(/if \(!qBox\.value\.trim\(\)\) qBox\.value = REVIEW_FIX_REQUEST/.test(source),
  "opening a review must make the default Send action visible");
assert(/id="bd-review-wrap"/.test(source)
  && (source.match(/root\.classList\.add\("binder-past-review-mode"\)/g) || []).length === 2,
  "past-review list and detail views need a focused control mode");
assert(/rv\.checked = false;[\s\S]*it\.checked = false;[\s\S]*syncDesc\(\); persist\(\)/.test(source),
  "entering Past Reviews must clear the hidden Review and Iterate workflows");
for (const id of ["#bd-review-wrap", "#bd-iterate-wrap", "#bd-rebuild"]) {
  assert(activityCss.includes(`.binder-past-review-mode ${id}`),
    `past-review mode must hide unrelated control ${id}`);
}
assert(/const setReviewApplication = \(on\)/.test(source)
  && /bd\.checked = true;[\s\S]*standard\.checked = true;[\s\S]*it\.checked = false/.test(source)
  && /bd\.disabled = on;[\s\S]*standard\.disabled = on/.test(source),
  "review application must lock Broad and Update to Standard on while disabling Iterate");

console.log("Binder filtered activity UI: OK");
