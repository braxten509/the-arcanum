/* The only browser transport adapter. Every API call is scoped to the active tome. */
import { tomeId } from "./bootstrap.js";

function scopedUrl(input) {
  if (typeof input !== "string" || !input.startsWith("/api/") || /[?&]tome=/.test(input)) {
    return input;
  }
  return input + (input.includes("?") ? "&" : "?") + "tome=" + encodeURIComponent(tomeId());
}

export function apiFetch(url, options) {
  return fetch(scopedUrl(url), options);
}

export async function apiJson(url, options) {
  const response = await apiFetch(url, options);
  const payload = await response.json();
  if (!response.ok) {
    const error = new Error(payload.error || payload.detail || `Request failed (${response.status})`);
    error.status = response.status;
    error.payload = payload;
    throw error;
  }
  return payload;
}

export function postJson(url, body = {}) {
  return apiJson(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}
