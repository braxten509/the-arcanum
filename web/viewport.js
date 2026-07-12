/* A single 2K design space for the whole study.
   The stage is uniformly fitted into any desktop viewport, so artwork, text,
   fixed overlays, pointer targets, and their coordinates always scale together. */
(() => {
  const width = 2560;
  const height = 1440;
  const stage = document.getElementById("app-stage");
  let scale = 1;

  const fit = () => {
    const nextScale = Math.min(innerWidth / width, innerHeight / height);
    if (!Number.isFinite(nextScale) || nextScale <= 0) return;
    scale = nextScale;
    const left = (innerWidth - width * scale) / 2;
    const top = (innerHeight - height * scale) / 2;
    stage.style.left = `${left}px`;
    stage.style.top = `${top}px`;
    stage.style.transform = `scale(${scale})`;
    document.documentElement.style.setProperty("--stage-scale", scale);
  };

  const point = (x, y) => {
    const bounds = stage.getBoundingClientRect();
    return { x: (x - bounds.left) / scale, y: (y - bounds.top) / scale };
  };

  const rect = (bounds) => {
    const topLeft = point(bounds.left, bounds.top);
    return {
      left: topLeft.x,
      top: topLeft.y,
      right: topLeft.x + bounds.width / scale,
      bottom: topLeft.y + bounds.height / scale,
      width: bounds.width / scale,
      height: bounds.height / scale,
    };
  };

  window.ArcanumViewport = {
    width,
    height,
    get scale() { return scale; },
    stage,
    fit,
    point,
    rect,
    length: (value) => value / scale,
    mount: (element) => stage.appendChild(element),
  };

  fit();
  addEventListener("resize", fit, { passive: true });
})();
