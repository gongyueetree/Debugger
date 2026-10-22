// View coordinates are sample indexes, independent of the canvas pixel width.
export const MIN_WINDOW = 32;
const clamp = (n, lo, hi) => Math.max(lo, Math.min(hi, n));

export function formatSampleTime(seconds, resolution = 0) {
  const [scale, unit] = Math.abs(seconds) < 0.001 ? [1e6, 'µs'] : Math.abs(seconds) < 1 ? [1e3, 'ms'] : [1, 's'];
  const digits = resolution > 0 ? clamp(Math.ceil(-Math.log10(resolution * scale)), 2, 9) : 2;
  return (seconds * scale).toFixed(digits) + ' ' + unit;
}

export function normalizeView(total, view = {}) {
  if (!total) return {start: 0, size: 0};
  const size = clamp(Math.round(view.size ?? total), Math.min(MIN_WINDOW, total), total);
  return {start: clamp(Math.round(view.start || 0), 0, total - size), size};
}

export function resizeView(total, view, size, anchor = 0.5) {
  const old = normalizeView(total, view);
  const next = normalizeView(total, {size});
  // Keep the sample under the pointer stationary unless we reach a boundary.
  return normalizeView(total, {size: next.size, start: old.start + (old.size - next.size) * clamp(anchor, 0, 1)});
}
