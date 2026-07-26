/* Keep physical desk props proportional to the 2560x1440 composition without
   shrinking the readable application UI. Artwork and fitted hitboxes share
   each prop's .obj-art wrapper, so one scale always moves them together. */
(() => {
  const table = document.getElementById("table");
  const fit = () => {
    if (!table) return;
    // Geometric mean of the two ratios: the scene keeps its share of the desk's
    // area on any proportion. `contain` (the min) starved a 21:9 desk — props
    // sized to the short edge, marooned around a huge page — and `cover` (the
    // max) would swell them over the reading margin on a 4:3 one.
    const scale = Math.sqrt((table.clientWidth / 2560) * (table.clientHeight / 1388));
    if (!Number.isFinite(scale) || scale <= 0) return;
    table.style.setProperty("--desk-scale", scale);
  };

  fit();
  if (table && "ResizeObserver" in window) new ResizeObserver(fit).observe(table);
  addEventListener("resize", fit, { passive: true });
})();
