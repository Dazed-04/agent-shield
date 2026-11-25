export const DECISIONS = ["ALLOW", "WARN", "APPROVE", "BLOCK"];

// Same hues as the decision badges in the chat UI.
export const DECISION_COLORS = {
  ALLOW: "#34d399",
  WARN: "#fbbf24",
  APPROVE: "#fb923c",
  BLOCK: "#fb7185",
};

export const AXIS = "#94a3b8";
export const GRID = "#1e293b";
export const TOOLTIP_STYLE = {
  contentStyle: {
    background: "#0b1220",
    border: "1px solid #334155",
    borderRadius: 8,
    fontSize: 11,
    color: "#e2e8f0",
  },
  labelStyle: { color: "#94a3b8" },
  cursor: { fill: "rgba(148,163,184,0.08)" },
};

export const fmtInt = (n) => (n == null ? "–" : Number(n).toLocaleString());

export const fmtMs = (v) => {
  if (v == null) return "–";
  return v >= 1000 ? `${(v / 1000).toFixed(2)} s` : `${v.toFixed(v < 10 ? 2 : 0)} ms`;
};

/** 0..1 -> "12.3%" ; null stays a dash so "no data" is never shown as 0%. */
export const fmtPct = (v, digits = 1) => (v == null ? "–" : `${(100 * v).toFixed(digits)}%`);

/** "12.3% [8, 17]" for a rate with a [lo, hi] interval in 0..1. */
export const fmtRate = (rate, ci) => {
  if (rate == null) return "–";
  const base = fmtPct(rate);
  return ci ? `${base} [${(100 * ci[0]).toFixed(0)}, ${(100 * ci[1]).toFixed(0)}]` : base;
};

/** Short x-axis label for a timeseries bucket (ISO timestamp from the API). */
export const bucketLabel = (iso, bucket) =>
  bucket === "hour" ? `${iso.slice(11, 13)}:00` : iso.slice(5, 10);
