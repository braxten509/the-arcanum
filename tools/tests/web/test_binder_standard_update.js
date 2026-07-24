// Binder "Update to Standard" UI and request wiring.
//   node tools/tests/web/test_binder_standard_update.js
const fs = require("fs");
const assert = require("assert");
const path = require("path");

const root = path.join(__dirname, "..", "..", "..");
const source = [
  path.join(root, "web", "app", "forge", "binder.js"),
  path.join(root, "web", "app", "forge", "binder", "view.js"),
].map((file) => fs.readFileSync(file, "utf8")).join("\n");

const broadAt = source.indexOf('id="bd-broad"');
const standardAt = source.indexOf('id="bd-standard"');
const reviewAt = source.indexOf('id="bd-review"');
assert(broadAt >= 0 && standardAt > broadAt && reviewAt > standardAt,
  "Update to Standard must sit immediately after Broad change");
assert(/class="forge-check hidden" id="bd-standard-wrap"/.test(source),
  "Update to Standard must be hidden until Broad change is selected");
assert(/standardWrap\.classList\.toggle\("hidden", !bd\.checked\)/.test(source),
  "Broad change must control Update to Standard visibility");
assert(/if \(!bd\.checked\) \{ standard\.checked = false;/.test(source),
  "leaving Broad change must clear Update to Standard");
assert(/updateStandard: standard\.checked/.test(source),
  "the Binder request must carry the Update to Standard choice");
assert(/!q && !standard\.checked && !it\.checked && !rv\.checked/.test(source),
  "Update to Standard must be able to run without a typed request");

console.log("Binder Update to Standard UI wiring: OK");
