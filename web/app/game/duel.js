/* Hexes hurled at your study, and the spell duels you pick yourself. */
import { ATK_STAGE_AT, ATK_STAKE_PER, ATK_TIME, ATK_WIN_PER, BLACKICE_CAP, BLACKICE_N, EARNED_THEME, INTRUSION_TIERS, coin, gp, roman, runLabel } from "../core/config.js";
import { $, esc, modal, sfx, toast } from "../core/dom.js";
import { codePad, firstDiff, normCode } from "./code.js";
import { addCredits, grantBadge, lessonDone, sectionPassed, updateHud } from "./progress.js";
import { castSigil } from "./sigil.js";
import { getState, save } from "../core/store.js";
import { sections } from "../core/bootstrap.js";
import { apiFetch } from "../core/api-client.js";

// ------------------------------------------------------------ HEX DEFENSE
// random hexes: inscribe a real working counter-spell against the sandglass or bleed coin.
// stdlib-only challenges — the snippet sandbox has no packages.
export function intrusionEligible() {
  return getState().booted && !$("#modal-root").firstChild && !document.querySelector(".grade-overlay")
    && sections().some((sec) => sec.lessons.some(lessonDone));
}

export function startIntrusion() {
  const passed = sections().filter(sectionPassed).length;
  const unlocked = INTRUSION_TIERS.filter((t) => t.min <= passed);
  if (!unlocked.length) return;
  const tier = Math.random() < 0.7 ? unlocked[unlocked.length - 1] : unlocked[Math.floor(Math.random() * unlocked.length)];
  const ch = tier.pool[Math.floor(Math.random() * tier.pool.length)];
  sfx("hex"); // the rival's blast streaks in (the alarm toll stands in until the sample decodes)

  const overlay = document.createElement("div");
  overlay.className = "grade-overlay";
  overlay.innerHTML = `<div class="grade-card" style="border-color:var(--bad,#8e2f23)">
    <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:20px">
      <div>
        <div class="faint" style="font-size:11px;letter-spacing:.2em;color:var(--bad,#8e2f23)">✦ A HEX STREAKS TOWARD YOUR STUDY // COUNTER-SPELL REQUIRED</div>
        <h2 style="margin:6px 0 0">${esc(ch.t)}</h2>
        <div class="dim" style="font-size:12.5px;margin-top:4px">${esc(ch.brief)} Inscribe a working counter-spell before the sandglass empties or bleed ${coin()}.</div>
      </div>
      <div class="num" id="hk-clock" style="font-size:26px;font-weight:700"></div>
    </div>
    <div class="lab-expect" style="margin-top:12px"><span class="faint" style="font-size:10.5px;letter-spacing:.14em">THE COUNTER-SPELL MUST UTTER, EXACTLY</span><pre><code></code></pre></div>
    <div class="code-pad"></div>
    <pre class="lab-out hidden"></pre>
    <div class="modal-actions">
      <button class="btn quiet" id="hk-abandon">YIELD (TAKE THE HIT)</button>
      <button class="btn" id="hk-submit">INSCRIBE + CAST</button>
    </div>
  </div>`;
  $(".lab-expect pre code", overlay).textContent = ch.expect;
  document.body.appendChild(overlay);
  let hkEd = null;
  window.GhostEditor.monacoReady.then(() => {
    hkEd = codePad($(".code-pad", overlay), ch.starter, () => $("#hk-submit", overlay).click());
    hkEd.focus();
  });

  const endAt = Date.now() + tier.time * 1000;
  let inFlight = false, expired = false, done = false;
  const clock = $("#hk-clock", overlay);
  const tick = setInterval(() => {
    const left = Math.max(0, endAt - Date.now());
    const s2 = Math.ceil(left / 1000);
    clock.textContent = `${Math.floor(s2 / 60)}:${String(s2 % 60).padStart(2, "0")}`;
    if (s2 <= 10) clock.style.color = "var(--bad, #f43)";
    if (left <= 0) {
      clearInterval(tick);
      expired = true;
      // ponytail: submission in flight at the buzzer still counts — dotnet latency isn't the player's fault
      if (inFlight) clock.textContent = "VERIFYING";
      else finish(false);
    }
  }, 250);

  function finish(won) {
    if (done) return;
    done = true;
    clearInterval(tick);
    castSigil($(".grade-card", overlay) || overlay, won);
    overlay.remove();
    if (won) {
      getState().stats.intrusionW = (getState().stats.intrusionW || 0) + 1;
      sfx("grade");
      toast(`THE HEX SHATTERS ON YOUR DOORSTEP // <b>+${tier.bounty}</b> ${coin()} bounty.`);
      addCredits(tier.bounty, true);
      grantBadge("first-defense");
    } else {
      getState().stats.intrusionL = (getState().stats.intrusionL || 0) + 1;
      if (getState().inv.firewall > 0) {
        getState().inv.firewall--;
        toast(`STRUCK — YOUR WARD ABSORBED IT (${getState().inv.firewall} charges left)`, "warn");
      } else {
        const loss = Math.min(getState().credits, Math.max(5, Math.round(getState().credits * 0.10)));
        getState().credits -= loss;
        getState().stats.streak = 0;
        updateHud();
        toast(`THE HEX LANDS // <b>-${loss}</b> ${coin()} torn from your purse. Your chant is broken.`, "bad");
      }
      save();
    }
  }

  $("#hk-abandon", overlay).onclick = () => finish(false);
  const bSub = $("#hk-submit", overlay);
  bSub.onclick = async () => {
    if (inFlight || done || (expired && !inFlight)) return;
    inFlight = true;
    bSub.disabled = true; bSub.textContent = "INSCRIBING...";
    const out = $(".lab-out", overlay);
    out.classList.remove("hidden");
    out.textContent = runLabel() + " — the counter-spell takes shape...";
    let data;
    try {
      const r = await apiFetch("/api/runsnippet", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ code: hkEd ? hkEd.getValue() : "", stdin: "" }),
      });
      data = await r.json();
    } catch (err) { data = { ok: false, output: "server error: " + err }; }
    inFlight = false;
    bSub.disabled = false; bSub.textContent = "INSCRIBE + CAST";
    if (done) return;
    const pass = data.ok && normCode(data.output) === normCode(ch.expect);
    if (pass) { finish(true); return; }
    if (expired) { finish(false); return; }
    out.textContent = data.output || "(the stone stays silent)";
    const d = data.ok ? firstDiff(data.output, ch.expect) : null;
    toast(d ? `LINE ${d.line}: expected «${esc(d.expected)}» got «${esc(d.got)}»` : "THE FORGE REJECTED IT — read its complaint, mend, cast again", "warn");
  };
}

// ------------------------------------------------------------ SPELL DUEL
// player-initiated duel: 3:00 sandglass, further demands arm at 1:00 and 2:00, judged
// against whatever was armed when submit was clicked. No coin for winning — wins bank
// toward the exclusive earned theme (10 qualifying: max 2 per circle, final circle uncapped).
// Losing/yielding/timing out forfeits a 20×circle stake and breaks the chant.
const attackDiff = () => Math.min(window.ATTACK_TIERS.length, sections().filter(sectionPassed).length);

export function atkQualifying() {
  let q = 0;
  for (const [d, w] of Object.entries(getState().stats.atkWins || {}))
    q += (+d === window.ATTACK_TIERS.length ? w : Math.min(BLACKICE_CAP, w)); // per-difficulty cap, final difficulty uncapped
  return q;
}

export function initiateAttack() {
  if (document.querySelector(".grade-overlay") || $("#modal-root").firstChild) return;
  const d = attackDiff();
  if (d < 1) { toast("THE WAND STAYS COLD // seal your first chapter before challenging a rival.", "bad"); return; }
  const stake = Math.min(getState().credits, ATK_STAKE_PER * d);
  const earnedUnlocked = EARNED_THEME && getState().themes[EARNED_THEME.id];
  const prize = (!EARNED_THEME || earnedUnlocked)
    ? `every 2nd victory at this circle pays <b>${ATK_WIN_PER * d}</b> ${coin()}`
    : `${BLACKICE_N} qualifying victories win the <b>${EARNED_THEME.name}</b> ink (${atkQualifying()}/${BLACKICE_N}, at most ${BLACKICE_CAP} counted per circle)`;
  modal(`<h2 style="color:var(--bad)">SPELL DUEL // A RIVAL OF THE ${roman(d)} CIRCLE</h2>
    <p class="dim">3:00 in the sandglass. The rival's first hex strikes at once — two more hexes arm at
    1:00 and 2:00, and your counter is judged against whatever hex is live when you cast. Win: no purse, but
    ${prize}. Lose, yield, or let the glass run out: a <b class="num" style="color:var(--bad)">-${stake}</b> ${coin()} stake
    and your chant breaks. Wards give no shelter in a duel. Once wands are drawn, there is no walking away.</p>`,
    [["DECLINE", "quiet", null], ["DRAW YOUR WAND", "danger", () => startAttack(d, stake)]]);
}

function startAttack(d, stake) {
  const tier = window.ATTACK_TIERS[d - 1];
  const ch = tier.pool[Math.floor(Math.random() * tier.pool.length)];
  sfx("hex"); // the rival opens with a hex hurled at your study

  const overlay = document.createElement("div");
  overlay.className = "grade-overlay";
  overlay.innerHTML = `<div class="grade-card" style="border-color:var(--bad,#8e2f23)">
    <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:20px">
      <div>
        <div class="faint" style="font-size:11px;letter-spacing:.2em;color:var(--bad,#8e2f23)">✦ WANDS DRAWN // THE ${roman(d)} CIRCLE // STAKE ${stake}${gp()}</div>
        <h2 style="margin:6px 0 0">${esc(ch.t)}</h2>
        <ol id="atk-objs" class="dim" style="font-size:12.5px;margin:6px 0 0;padding-left:18px">
          <li>${esc(ch.stages[0].brief)}</li>
          <li class="faint">SEALED HEX — arms at T+1:00</li>
          <li class="faint">SEALED HEX — arms at T+2:00</li>
        </ol>
      </div>
      <div class="num" id="atk-clock" style="font-size:26px;font-weight:700"></div>
    </div>
    <div class="lab-expect" style="margin-top:12px"><span class="faint" style="font-size:10.5px;letter-spacing:.14em">THE RIVAL'S HEX — CAST THIS EXACT COUNTER TO TURN IT (CURRENTLY ARMED)</span><pre><code></code></pre></div>
    <div class="code-pad"></div>
    <pre class="lab-out hidden"></pre>
    <div class="modal-actions">
      <button class="btn quiet" id="atk-abandon">YIELD (FORFEIT THE STAKE)</button>
      <button class="btn" id="atk-submit">INSCRIBE + CAST</button>
    </div>
  </div>`;
  const expectEl = $(".lab-expect pre code", overlay);
  expectEl.textContent = ch.stages[0].expect;
  document.body.appendChild(overlay);
  let atkEd = null;
  window.GhostEditor.monacoReady.then(() => {
    atkEd = codePad($(".code-pad", overlay), ch.starter, () => $("#atk-submit", overlay).click());
    atkEd.focus();
  });

  const startAt = Date.now();
  const endAt = startAt + ATK_TIME * 1000;
  const stageAt = (ms) => ms >= ATK_STAGE_AT[2] * 1000 ? 2 : ms >= ATK_STAGE_AT[1] * 1000 ? 1 : 0;
  let shownStage = 0, inFlight = false, expired = false, done = false;
  const clock = $("#atk-clock", overlay);
  const tick = setInterval(() => {
    const st = stageAt(Date.now() - startAt);
    if (st > shownStage) {
      shownStage = st;
      const li = $("#atk-objs", overlay).children[st];
      li.classList.remove("faint");
      li.textContent = ch.stages[st].brief;
      expectEl.textContent = ch.stages[st].expect;
      sfx("hex"); // the rival presses — another hex streaks in
      toast(`THE RIVAL PRESSES THE HEX // a ${st + 1}${st === 1 ? "nd" : "rd"} hex strikes — your counter must grow to turn it`, "warn");
    }
    const left = Math.max(0, endAt - Date.now());
    const s2 = Math.ceil(left / 1000);
    clock.textContent = `${Math.floor(s2 / 60)}:${String(s2 % 60).padStart(2, "0")}`;
    if (s2 <= 10) clock.style.color = "var(--bad, #f43)";
    if (left <= 0) {
      clearInterval(tick);
      expired = true;
      // submission in flight at the buzzer still counts — dotnet latency isn't the player's fault
      if (inFlight) clock.textContent = "VERIFYING";
      else finish(false);
    }
  }, 250);

  function finish(won) {
    if (done) return;
    done = true;
    clearInterval(tick);
    castSigil($(".grade-card", overlay) || overlay, won);
    overlay.remove();
    if (won) {
      getState().stats.atkW = (getState().stats.atkW || 0) + 1;
      getState().stats.atkWins = getState().stats.atkWins || {};
      getState().stats.atkWins[d] = (getState().stats.atkWins[d] || 0) + 1;
      sfx("grade");
      toast(`THE RIVAL LOWERS THEIR WAND // a duel of the ${roman(d)} circle is yours.`);
      const q = atkQualifying();
      if (q >= 1) grantBadge("atk-1");
      if (q >= 5) grantBadge("atk-5");
      if (q >= BLACKICE_N && EARNED_THEME && !getState().themes[EARNED_THEME.id]) {
        getState().themes[EARNED_THEME.id] = true;
        grantBadge("atk-ice");
        toast(`WON, NOT BOUGHT // <b>${EARNED_THEME.name}</b> — equip it at the peddler's table.`, "warn");
      } else if (EARNED_THEME && getState().themes[EARNED_THEME.id] && getState().stats.atkWins[d] % 2 === 0) {
        addCredits(ATK_WIN_PER * d); // post-theme trickle: every 2nd win at the current circle pays
      }
      save();
    } else {
      getState().stats.atkL = (getState().stats.atkL || 0) + 1;
      const loss = Math.min(getState().credits, stake);
      getState().credits -= loss;
      getState().stats.streak = 0;
      updateHud();
      toast(`THE DUEL IS LOST // your <b>-${loss}</b> ${coin()} stake is forfeit. Your chant is broken.`, "bad");
      save();
    }
  }

  $("#atk-abandon", overlay).onclick = () => finish(false);
  const bSub = $("#atk-submit", overlay);
  bSub.onclick = async () => {
    if (inFlight || done || (expired && !inFlight)) return;
    const lockedStage = stageAt(Date.now() - startAt); // judged against what was armed at cast time
    inFlight = true;
    bSub.disabled = true; bSub.textContent = "INSCRIBING...";
    const out = $(".lab-out", overlay);
    out.classList.remove("hidden");
    out.textContent = runLabel() + " — your riposte takes shape...";
    let data;
    try {
      const r = await apiFetch("/api/runsnippet", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ code: atkEd ? atkEd.getValue() : "", stdin: "" }),
      });
      data = await r.json();
    } catch (err) { data = { ok: false, output: "server error: " + err }; }
    inFlight = false;
    bSub.disabled = false; bSub.textContent = "INSCRIBE + CAST";
    if (done) return;
    const expect = ch.stages[lockedStage].expect;
    const pass = data.ok && normCode(data.output) === normCode(expect);
    if (pass) { finish(true); return; }
    if (expired) { finish(false); return; }
    out.textContent = data.output || "(the stone stays silent)";
    const df = data.ok ? firstDiff(data.output, expect) : null;
    toast(df ? `LINE ${df.line}: expected «${esc(df.expected)}» got «${esc(df.got)}»` : "THE FORGE REJECTED IT — read its complaint, mend, cast again", "warn");
  };
}
