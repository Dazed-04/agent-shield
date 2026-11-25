import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { AlertTriangle, RefreshCw } from "lucide-react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  AXIS,
  DECISIONS,
  DECISION_COLORS,
  GRID,
  TOOLTIP_STYLE,
  bucketLabel,
  fmtInt,
  fmtMs,
  fmtPct,
} from "./format";

const API_BASE = "/api";
const WINDOWS = [
  { days: 1, label: "24 h" },
  { days: 7, label: "7 days" },
  { days: 30, label: "30 days" },
];

function Stat({ label, value, sub }) {
  return (
    <div className="p-3 bg-slate-900/70 border border-slate-800 rounded-xl">
      <div className="text-[10px] uppercase tracking-wider text-slate-500">{label}</div>
      <div className="text-xl font-semibold text-slate-100 mt-0.5">{value}</div>
      {sub && <div className="text-[10px] text-slate-500 mt-0.5">{sub}</div>}
    </div>
  );
}

function Panel({ title, note, children }) {
  return (
    <section className="p-3 bg-slate-900/50 border border-slate-800 rounded-xl">
      <h3 className="text-xs font-semibold text-slate-300">{title}</h3>
      {note && <p className="text-[10px] text-slate-500 mb-2">{note}</p>}
      <div className={note ? "" : "mt-2"}>{children}</div>
    </section>
  );
}

export default function LiveMetrics() {
  const [days, setDays] = useState(7);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setData((await axios.get(`${API_BASE}/analytics/metrics`, { params: { days } })).data);
    } catch (e) {
      setData(null);
      setError(e.response?.data?.detail || "Could not load metrics.");
    } finally {
      setLoading(false);
    }
  }, [days]);

  useEffect(() => {
    load();
  }, [load]);

  const mix = data ? DECISIONS.map((d) => ({ name: d, count: data.decision_mix[d] })) : [];
  const series = data
    ? data.timeseries.map((p) => ({ ...p, label: bucketLabel(p.t, data.window.bucket) }))
    : [];
  // Colour each bin by the decision band its midpoint falls in, using the server's real thresholds.
  const th = data?.thresholds || { allow_max: 25, warn_max: 55, approve_max: 80 };
  const histColor = (from) => {
    const mid = from + 5;
    return mid <= th.allow_max
      ? DECISION_COLORS.ALLOW
      : mid <= th.warn_max
        ? DECISION_COLORS.WARN
        : mid <= th.approve_max
          ? DECISION_COLORS.APPROVE
          : DECISION_COLORS.BLOCK;
  };
  const hist = data ? data.score_histogram.map((b) => ({ ...b, label: `${b.from}–${b.to}` })) : [];
  const blocked = data && data.n ? data.decision_mix.BLOCK / data.n : null;
  const heuristic = data?.jailbreak_mode?.heuristic || 0;

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex gap-1">
          {WINDOWS.map((w) => (
            <button
              key={w.days}
              onClick={() => setDays(w.days)}
              className={`px-2.5 py-1 rounded-md text-[11px] border cursor-pointer transition ${
                days === w.days
                  ? "bg-sky-500/15 text-sky-300 border-sky-500/40"
                  : "text-slate-400 border-slate-700 hover:text-slate-200"
              }`}
            >
              {w.label}
            </button>
          ))}
        </div>
        <button onClick={load} className="text-slate-400 hover:text-sky-400 cursor-pointer" title="Refresh">
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
        </button>
      </div>

      {error && (
        <div className="p-3 text-xs text-rose-300 bg-rose-950/30 border border-rose-900/50 rounded-lg">{error}</div>
      )}

      {data && data.truncated && (
        <div className="flex gap-2 p-2.5 text-[11px] text-amber-300 bg-amber-950/20 border border-amber-900/40 rounded-lg">
          <AlertTriangle className="w-3.5 h-3.5 shrink-0 mt-0.5" />
          Only the most recent 50,000 requests in this window are included.
        </div>
      )}

      {data && heuristic > 0 && (
        <div className="flex gap-2 p-2.5 text-[11px] text-amber-300 bg-amber-950/20 border border-amber-900/40 rounded-lg">
          <AlertTriangle className="w-3.5 h-3.5 shrink-0 mt-0.5" />
          {fmtInt(heuristic)} of {fmtInt(data.n)} requests were scored by the keyword fallback, not the semantic
          model. Detection quality in this window is lower than with the semantic detector.
        </div>
      )}

      {data && data.n === 0 && !error && (
        <div className="text-center text-xs text-slate-500 py-12">No requests in this window yet.</div>
      )}

      {data && data.n > 0 && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
            <Stat label="Requests" value={fmtInt(data.n)} sub={`${fmtInt(data.with_tool_calls)} attempted a tool call`} />
            <Stat label="Blocked" value={fmtPct(blocked)} sub={`${fmtInt(data.decision_mix.BLOCK)} requests`} />
            <Stat label="Median latency" value={fmtMs(data.latency_ms.total.p50)} sub={`p95 ${fmtMs(data.latency_ms.total.p95)}`} />
            <Stat
              label="Detector mode"
              value={heuristic ? "mixed" : "semantic"}
              sub={Object.entries(data.jailbreak_mode).map(([k, v]) => `${k}: ${fmtInt(v)}`).join(" · ") || "no data"}
            />
          </div>

          <div className="grid md:grid-cols-2 gap-3">
            <Panel title="Decisions" note="Final action taken on each request in the window.">
              <ResponsiveContainer width="100%" height={200}>
                <BarChart data={mix} margin={{ top: 8, right: 8, left: -12, bottom: 0 }}>
                  <CartesianGrid stroke={GRID} vertical={false} />
                  <XAxis dataKey="name" stroke={AXIS} fontSize={11} />
                  <YAxis stroke={AXIS} fontSize={11} allowDecimals={false} />
                  <Tooltip {...TOOLTIP_STYLE} />
                  <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                    {mix.map((m) => (
                      <Cell key={m.name} fill={DECISION_COLORS[m.name]} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </Panel>

            <Panel title="Risk score distribution" note={`Coloured by decision band (ALLOW ≤ ${th.allow_max}, WARN ≤ ${th.warn_max}, APPROVE ≤ ${th.approve_max}, else BLOCK).`}>
              <ResponsiveContainer width="100%" height={200}>
                <BarChart data={hist} margin={{ top: 8, right: 8, left: -12, bottom: 0 }}>
                  <CartesianGrid stroke={GRID} vertical={false} />
                  <XAxis dataKey="label" stroke={AXIS} fontSize={10} />
                  <YAxis stroke={AXIS} fontSize={11} allowDecimals={false} />
                  <Tooltip {...TOOLTIP_STYLE} />
                  <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                    {hist.map((b) => (
                      <Cell key={b.from} fill={histColor(b.from)} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </Panel>
          </div>

          <Panel title="Requests over time" note={`Per ${data.window.bucket}, stacked by decision.`}>
            <ResponsiveContainer width="100%" height={210}>
              <BarChart data={series} margin={{ top: 8, right: 8, left: -12, bottom: 0 }}>
                <CartesianGrid stroke={GRID} vertical={false} />
                <XAxis dataKey="label" stroke={AXIS} fontSize={10} />
                <YAxis stroke={AXIS} fontSize={11} allowDecimals={false} />
                <Tooltip {...TOOLTIP_STYLE} />
                <Legend wrapperStyle={{ fontSize: 11 }} itemSorter={null} />
                {DECISIONS.map((d) => (
                  <Bar key={d} dataKey={d} stackId="a" fill={DECISION_COLORS[d]} />
                ))}
              </BarChart>
            </ResponsiveContainer>
          </Panel>

          <div className="grid md:grid-cols-2 gap-3">
            <Panel title="Detector hit rates" note="Share of requests each detector scored above the ALLOW threshold.">
              <table className="w-full text-[11px]">
                <thead className="text-slate-500 text-left">
                  <tr>
                    <th className="font-medium py-1">Detector</th>
                    <th className="font-medium text-right">Flagged</th>
                    <th className="font-medium text-right">Rate</th>
                    <th className="font-medium text-right">Mean score</th>
                  </tr>
                </thead>
                <tbody className="text-slate-300 font-mono">
                  {Object.entries(data.detector_hits).map(([name, v]) => (
                    <tr key={name} className="border-t border-slate-800">
                      <td className="py-1.5">{name}</td>
                      <td className="text-right">{fmtInt(v.flagged)}</td>
                      <td className="text-right">{fmtPct(v.flag_rate)}</td>
                      <td className="text-right">{v.mean_score ?? "–"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Panel>

            <Panel title="Latency by stage" note="Pipeline stages recorded per request. 'agent' is the model and tool loop.">
              <table className="w-full text-[11px]">
                <thead className="text-slate-500 text-left">
                  <tr>
                    <th className="font-medium py-1">Stage</th>
                    <th className="font-medium text-right">p50</th>
                    <th className="font-medium text-right">p95</th>
                    <th className="font-medium text-right">p99</th>
                  </tr>
                </thead>
                <tbody className="text-slate-300 font-mono">
                  {[...Object.entries(data.latency_ms.stages), ["total", data.latency_ms.total]].map(([name, v]) => (
                    <tr key={name} className={`border-t border-slate-800 ${name === "total" ? "text-slate-100 font-semibold" : ""}`}>
                      <td className="py-1.5">{name}</td>
                      <td className="text-right">{fmtMs(v.p50)}</td>
                      <td className="text-right">{fmtMs(v.p95)}</td>
                      <td className="text-right">{fmtMs(v.p99)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Panel>
          </div>
        </>
      )}
    </div>
  );
}
