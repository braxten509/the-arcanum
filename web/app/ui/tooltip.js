/* ---- global tooltips: every [title] becomes a themed parchment scrap ---- */
const tip = document.createElement("div");
tip.id = "tip";
document.body.appendChild(tip);
let timer = 0, current = null, armed = null;

// Move title -> data-tip so the native tooltip never appears; re-reads on every
// hover, so code that reassigns el.title keeps working untouched.
const text = (el) => {
  if (el.hasAttribute("title")) {
    const t = el.getAttribute("title");
    el.dataset.tip = t;
    el.removeAttribute("title");
    if (!el.hasAttribute("aria-label") && !el.textContent.trim()) el.setAttribute("aria-label", t);
  }
  return el.dataset.tip || "";
};

function show(el) {
  const t = text(el);
  if (!t) return;
  current = el;
  tip.textContent = t;
  tip.classList.remove("below", "show");
  tip.style.left = "0px"; tip.style.top = "0px"; // measure unclamped
  const r = el.getBoundingClientRect();
  const w = tip.offsetWidth, h = tip.offsetHeight;
  const cx = r.left + r.width / 2;
  const x = Math.max(8, Math.min(cx - w / 2, innerWidth - w - 8));
  let y = r.top - h - 9;
  if (y < 8) { y = r.bottom + 9; tip.classList.add("below"); }
  tip.style.left = x + "px"; tip.style.top = y + "px";
  tip.style.setProperty("--tip-x", Math.max(10, Math.min(cx - x, w - 10)) + "px");
  tip.classList.add("show");
}

function hide() {
  clearTimeout(timer);
  current = armed = null;
  tip.classList.remove("show");
}

document.addEventListener("mouseover", (e) => {
  const el = e.target.closest("[title], [data-tip]");
  if (!el || el === current || el === armed) return;
  clearTimeout(timer);
  armed = el;
  timer = setTimeout(() => show(el), 350);
});
document.addEventListener("mouseout", (e) => {
  const el = e.target.closest("[title], [data-tip]");
  if (el && !el.contains(e.relatedTarget)) hide();
});
document.addEventListener("focusin", (e) => {
  const el = e.target.closest("[title], [data-tip]");
  if (el) show(el);
});
document.addEventListener("focusout", hide);
document.addEventListener("mousedown", hide);
document.addEventListener("keydown", (e) => { if (e.key === "Escape") hide(); });
addEventListener("scroll", hide, true);
