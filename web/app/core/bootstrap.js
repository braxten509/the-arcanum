/* One compatibility read of the classic tome-loader globals. */
let catalog = null;

export function bootstrapCatalog(source = window) {
  if (catalog) return catalog;
  const tome = source.TOME && typeof source.TOME === "object" ? source.TOME : {};
  const sections = Array.isArray(source.SECTIONS) ? source.SECTIONS : [];
  const id = typeof source.tid === "function" ? source.tid() : (tome.id || "verisearch");
  catalog = Object.freeze({
    tome,
    sections: Object.freeze(sections.slice()),
    id: String(id),
    tomes: Object.freeze((source.TOMES_LIST || []).slice()),
    activeTome: String(source.__ACTIVE_TOME || id),
  });
  return catalog;
}

export function getCatalog() {
  return catalog || bootstrapCatalog();
}

export const tome = () => getCatalog().tome;
export const sections = () => getCatalog().sections;
export const tomeId = () => getCatalog().id;
export const tomeList = () => getCatalog().tomes;
export const activeTome = () => getCatalog().activeTome;

export function installCatalogForTest(value) {
  catalog = Object.freeze({
    tome: value.tome || {},
    sections: Object.freeze((value.sections || []).slice()),
    id: String(value.id || "test"),
    tomes: Object.freeze((value.tomes || []).slice()),
    activeTome: String(value.activeTome || value.id || "test"),
  });
}
