/* Keep physical desk props proportional to the 2560x1440 composition without
   shrinking the readable application UI. Artwork and fitted hitboxes share
   each prop's .obj-art wrapper, so one scale always moves them together. */
(() => {
  const table = document.getElementById("table");
  const fit = () => {
    if (!table) return;
    const scale = Math.min(table.clientWidth / 2560, table.clientHeight / 1388);
    if (!Number.isFinite(scale) || scale <= 0) return;
    table.style.setProperty("--desk-scale", scale);
  };

  fit();
  if (table && "ResizeObserver" in window) new ResizeObserver(fit).observe(table);
  addEventListener("resize", fit, { passive: true });
})();
