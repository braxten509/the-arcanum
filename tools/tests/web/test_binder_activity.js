// Binder working view must consume filtered activity, never stream its raw log.
const fs = require("fs");
const assert = require("assert");
const path = require("path");

const root = path.join(__dirname, "..", "..", "..");
const source = [
  path.join(root, "web", "app", "forge", "binder.js"),
  path.join(root, "web", "app", "forge", "binder", "view.js"),
  path.join(root, "web", "app", "forge", "binder", "ledger.js"),
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
assert(/historyBtn\.textContent = "PAST RUNS"/.test(source),
  "Binder actions need a Past Runs button");
assert(/actions\.prepend\(sendBtn, historyBtn\)/.test(source),
  "Past Reviews must sit immediately to the right of Send to the Binder");
assert(/apiFetch\("\/api\/amend\/reviews/.test(source)
  && /lastReview = review\.path/.test(source)
  && /binderCost\(review\.apiCostEstimate\)/.test(source),
  "opening a past review must load its report, select it for fixes, and show cost");
assert(/const enterLedger = \(\) => \{[\s\S]*?out\.classList\.add\("binder-review-mode"\)/.test(source)
  && (source.match(/^\s*enterLedger\(\);$/gm) || []).length === 2,
  "both ledger views must opt out of the output pane's preformatted whitespace");
assert(/const REVIEW_FIX_REQUEST = "Implement the selected review's complete Recommendation/.test(source),
  "a selected review needs an explicit default remediation request");
assert(/const q = typedRequest \|\| \(ledger\.selected\(\) \? REVIEW_FIX_REQUEST : ""\)/.test(source),
  "Send must treat a selected review as actionable when the textarea is empty");
assert(/if \(!qBox\.value\.trim\(\)\) qBox\.value = REVIEW_FIX_REQUEST/.test(source),
  "opening a review must make the default Send action visible");
assert(/id="bd-review-wrap"/.test(source)
  && /const enterLedger = \(\) => \{[\s\S]*?root\.classList\.add\("binder-past-review-mode"\)/.test(source),
  "past-review list and detail views need a focused control mode");
// The ledger covers the entire output pane, including a finished run's cost line, so the
// button that opened it has to be the way back -- and the pane it covered comes back with it.
assert(/historyBtn\.textContent = "RETURN"/.test(source)
  && /historyBtn\.onclick = leaveLedger/.test(source)
  && /out\.innerHTML = benchOutput \|\| ""/.test(source),
  "Past Runs must become RETURN while the ledger is open and restore the working view");
assert(/rv\.checked = false;[\s\S]*it\.checked = false;[\s\S]*syncDesc\(\); persist\(\)/.test(source),
  "entering Past Reviews must clear the hidden Review and Iterate workflows");
for (const id of ["#bd-review-wrap", "#bd-iterate-wrap", "#bd-rebuild"]) {
  assert(activityCss.includes(`.binder-past-review-mode ${id}`),
    `past-review mode must hide unrelated control ${id}`);
}
// "Okay to reset progress" makes Iterate's append-only promise false: it may then renumber,
// move, and remove the very ids progress is keyed to. The summary has to say so.
assert(/const DESC_ITERATE = \(\) =>/.test(source)
  && /rs\.checked \? ITERATE_RESET : ITERATE_ADD/.test(source)
  && /will NOT survive/.test(source),
  "Iterate's summary must stop promising progress safety once reset is authorized");
assert(/const amending = pubOn \|\| bd\.checked \|\| standard\.checked \|\| it\.checked \|\| rs\.checked \|\| rv\.checked/
  .test(source) && /rebuild\.classList\.toggle\("hidden", amending\)/.test(source),
  "the destructive phase rewind must be hidden whenever any amendment box is checked");
assert(/standard\.addEventListener\("change", \(\) => \{ persist\(\); syncDesc\(\); \}\)/.test(source)
  && /rs\.addEventListener\("change", \(\) => \{ persist\(\); syncDesc\(\); \}\)/.test(source)
  && /pub\.addEventListener\("change", \(\) => \{ persist\(\); syncDesc\(\); \}\)/.test(source),
  "every checkbox must re-sync the summary, or the copy and the rewind door go stale");
// Make ready to publish is a loop of its own, not a modifier: it takes the bench alone, and
// every other mode is UNCHECKED as well as hidden. A box still ticked behind the panel would
// leave the server to be trusted to ignore it -- including the one that wipes progress.
assert(/id="bd-publish"/.test(source) && /Make ready to publish/.test(source),
  "the bench needs the publish checkbox");
assert(/const pubOn = pub\.checked;\s*\n\s*if \(pubOn\) \{ bd\.checked = false; rv\.checked = false; standard\.checked = false; it\.checked = false; rs\.checked = false; \}/
  .test(source), "publish must clear every other mode, not merely hide it");
for (const wrap of [/standardWrap[\s\S]{0,60}!bd\.checked \|\| pubOn/, /itWrap[\s\S]{0,60}!bd\.checked \|\| pubOn/,
                    /rsWrap[\s\S]{0,60}!bd\.checked \|\| pubOn/,
                    /bd\.parentElement[\s\S]{0,60}rv\.checked \|\| pubOn/,
                    /rv\.parentElement[\s\S]{0,60}bd\.checked \|\| pubOn/]) {
  assert(wrap.test(source), `publish must hide the control matched by ${wrap}`);
}
assert(/publish: pub\.checked/.test(source) && /const isBroad = pub\.checked \|\|/.test(source),
  "the publish flag must reach the server and be watched as a long unattended run");
assert(/!rv\.checked && !pub\.checked\) return;/.test(source),
  "publish needs no typed request, so an empty box must not silently do nothing");
assert(/pub\.checked = false;\s*\/\/ commissioning a review/.test(source)
  && /pub\.disabled = on;/.test(source),
  "applying a review's findings is an amendment, not a publish run");
assert(/const DESC_PUBLISH = /.test(source) && /up to 8 AI turns/.test(source)
  && /never touches your progress/.test(source),
  "the publish summary must state what a run costs and that progress is safe");
// The bench holds a typed request, a picked hand, and a selected review. A stray click on
// the backdrop used to discard all three, so it closes only through LEAVE THE BENCH.
assert(/modal\(binderTemplate\(\), \[\["LEAVE THE BENCH", "quiet"\]\], \{ sticky: true \}\)/
  .test(source), "the Binder bench must not close on an outside click");
// A run stopped by hand is the case where you most want the same request back.
assert(/offerResume\(\);/.test(source)
  && /function offerResume\(\)/.test(source)
  && /st\.status === "cancelled"[\s\S]{0,400}offerResume\(\)/.test(source),
  "stopping a run must offer to resume it, not just say the quill was stayed");
assert(/const setReviewApplication = \(on\)/.test(source)
  && /bd\.checked = true;[\s\S]*standard\.checked = true;[\s\S]*it\.checked = false/.test(source)
  && /bd\.disabled = on;[\s\S]*standard\.disabled = on/.test(source),
  "review application must lock Broad and Update to Standard on while disabling Iterate");

// The job store is in memory, so after a reload the ledger is the only surviving record
// of what a finished run changed and what it cost. The panel must list builds, not only
// reviews, and a build has no report file -- its row carries the record itself.
assert(/(?:const|function) binderHistory(?: = \(payload\)|\(payload\))/.test(source)
  && /Array\.isArray\(payload\.builds\)/.test(source),
  "the history panel must list past builds from the amend ledger");
assert(/PAST BUILDS/.test(source) && /binderCost\(build\.apiCostEstimate\)/.test(source),
  "every past build must show what it cost");
assert(/aria-expanded/.test(source) && /\.binder-build-row/.test(source)
  && /nextElementSibling\.classList\.toggle\("hidden"/.test(source),
  "a past build row must unfold its own record without a second fetch");
assert(activityCss.includes(".binder-build-detail")
  && activityCss.includes('.binder-build-row[aria-expanded="true"]'),
  "unfolded build rows need their own styling");
// A run that stopped is an offer: its record carries the feed it reached and the request
// that started it, so any row can be taken up again with any hand.
assert(/WHERE IT STOPPED/.test(source) && /binderActivity\(build\.activity\)/.test(source),
  "an unfinished build must show the feed it reached before it stopped");
assert(/\.binder-build-resume/.test(source)
  && /ctx\.resumeBuild\(\{ \.\.\.row\.setup, status: row\.status \}\)/.test(source)
  && /resumeBuild: \(setup\) => binderResume\(setup, true\)/.test(source),
  "RESUME on a past build must re-open the hand picker with that run's own request");
assert(/build\.setup \? "" : ` disabled/.test(source),
  "a run recorded before setups were kept cannot be resumed, and must say so");
// Deleting the one surviving record of a run that cost money is not undoable, and the
// bench is the app's only modal -- so the question is asked on a scrim card over it.
assert(/(?:const|function) confirmCard\(opts\)/.test(source)
  && /box\.querySelector\("\.rd-confirm"\)\.onclick = \(\) => \{ box\.remove\(\); opts\.onConfirm\(\); \}/
    .test(source) && /confirm: \(opts\) => confirmCard\(opts\)/.test(source),
  "a destructive ledger choice needs a confirmation card, not a replacement modal");
assert(/\.binder-build-forget/.test(source)
  && /ctx\.confirm\(\{[\s\S]*?apiFetch\("\/api\/amend\/forget"/.test(source)
  && /Your tome is not touched/.test(source),
  "DELETE must confirm first and only strike the ledger row");
assert(activityCss.includes(".binder-build-actions .btn")
  && activityCss.includes(".binder-build-section:not(:first-child)"),
  "the row's button pair must be sized as one, and lose its gap with no reviews above");

console.log("Binder filtered activity UI: OK");
