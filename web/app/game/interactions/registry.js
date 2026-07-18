export class InteractionRegistry {
  constructor() { this.entries = new Map(); }

  register(name, definition) {
    if (this.entries.has(name)) throw new Error(`duplicate interaction renderer: ${name}`);
    if (!definition || typeof definition.create !== "function") {
      throw new TypeError(`interaction renderer ${name} needs create(context)`);
    }
    if (!Number.isInteger(definition.version) || definition.version < 1) {
      throw new TypeError(`interaction renderer ${name} needs a positive integer version`);
    }
    if (!Array.isArray(definition.capabilities) || !definition.capabilities.length
        || definition.capabilities.some((item) => typeof item !== "string" || !item)) {
      throw new TypeError(`interaction renderer ${name} needs declared capabilities`);
    }
    this.entries.set(name, Object.freeze({ ...definition, id: name }));
    return this;
  }

  get(name) {
    const entry = this.entries.get(name);
    if (!entry) throw new Error(`unsupported interaction renderer: ${name}`);
    return entry;
  }

  names() { return [...this.entries.keys()]; }
}
