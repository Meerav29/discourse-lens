import * as d3 from 'd3';

// Distinct palette tuned for dark backgrounds
const PALETTE = [
  '#5a7fff', '#ff6b6b', '#ffd93d', '#6bcb77', '#ff9671',
  '#a78bfa', '#38bdf8', '#fb923c', '#34d399', '#f472b6',
];

export function getClusterColor(clusterId) {
  return PALETTE[((clusterId ?? 0) % PALETTE.length + PALETTE.length) % PALETTE.length];
}

export function getNodeRadius(wordCount) {
  return d3.scaleSqrt().domain([0, 5000]).range([3, 11]).clamp(true)(wordCount || 500);
}

export function formatMonth(dateStr) {
  if (!dateStr) return null;
  try {
    const d = new Date((dateStr.length <= 7 ? dateStr + '-01' : dateStr));
    if (isNaN(d)) return null;
    return d.toLocaleDateString('en-US', { year: 'numeric', month: 'short' });
  } catch { return null; }
}
