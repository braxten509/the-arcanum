/* Explicit UI command registry; composition owns wiring and feature modules stay acyclic. */
const handlers = new Map();

export function registerCommand(name, handler) {
  if (handlers.has(name)) throw new Error(`duplicate frontend command: ${name}`);
  if (typeof handler !== "function") throw new TypeError(`command ${name} needs a handler`);
  handlers.set(name, handler);
}

export function dispatchCommand(name, ...args) {
  const handler = handlers.get(name);
  if (!handler) throw new Error(`frontend command is not registered: ${name}`);
  return handler(...args);
}

export function resetCommandsForTest() {
  handlers.clear();
}
