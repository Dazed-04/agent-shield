import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { AXIS, GRID, TOOLTIP_STYLE, fmtInt, fmtMs, fmtRate } from "./format";

export const SYSTEM_LABELS = {
  prompt_scanner: "Prompt scanner (rules)",
  jailbreak_detector: "Jailbreak detector",
  combined: "Combined (risk engine)",
};
const OP_LABELS = {
  alert: "Alert (> ALLOW)",
  intervene: "Intervene (> WARN)",
  block: "Block (> APPROVE)",
  calibrated: "Calibrated on dev",
};

function Section({ title, note, children }) {
  return (
    <section className="p-3 bg-slate-900/50 border border-slate-800 rounded-xl">
      <h3 className="text-xs font-semibold text-slate-300">{title}</h3>
      {note && <p className="text-[10px] text-slate-500 mb-2">{note}</p>}
      <div className="overflow-x-auto">{children}</div>
    </section>
  );
}

const th = "font-medium py-1 px-2 text-left text-slate-500";
const td = "py-1.5 px-2 border-t border-slate-800";

export default function DetectorReport({ report }) {
  const group = report.groups["split:test"] || report.groups.all;
  const usingTest = Boolean(report.groups["split:test"]);
  const ops = [...Object.keys(report.operating_points), ...(Object.keys(report.calibrated_thresholds || {}).length ? ["calibrated"] : [])];
  const systems = Object.keys(group.systems);
  const sources = Object.keys(report.groups)
    .filter((k) => k.startsWith("source:") && k.endsWith("|split:test"))
    .map((k) => k.slice(7, -11));
  const roc = (report.roc_combined_test || []).map((p) => ({ fpr: p.fpr, tpr: p.tpr }));
  const cats = Object.entries(report.attack_detection_by_category || {});
  const latency = Object.entries(report.latency_ms || {});

  return (
    <div className="space-y-3">
      {!usingTest && (
        <div className="p-2.5 text-[11px] text-amber-300 bg-amber-950/20 border border-amber-900/40 rounded-lg">
          This run has no held-out test split; the tables below use all samples, including data the thresholds may have
          been tuned on.
        </div>
      )}

      <Section
        title={usingTest ? "Detector ablation — held-out test split" : "Detector ablation — all samples"}
        note={`${fmtInt(group.n_attacks)} attacks · ${fmtInt(group.n_benign)} benign. Rates with 95% Wilson interval [lo, hi] in %.`}
      >
        <table className="w-full text-[11px] font-mono">
          <thead>
            <tr>
              <th className={th}>System</th>
              <th className={th}>AUC [95% CI]</th>
              {ops.map((o) => (
                <th key={o} className={th}>
                  {OP_LABELS[o] || o}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="text-slate-300">
            {systems.map((s) => {
              const b = group.systems[s];
              return (
                <tr key={s} className={s === "combined" ? "text-slate-100" : ""}>
                  <td className={`${td} font-sans`}>{SYSTEM_LABELS[s] || s}</td>
                  <td className={td}>
                    {b.auc == null ? "–" : b.auc.toFixed(3)}
                    {b.auc_ci ? ` [${b.auc_ci[0].toFixed(3)}, ${b.auc_ci[1].toFixed(3)}]` : ""}
                  </td>
                  {ops.map((o) => {
                    const p = b.operating_points[o];
                    return (
                      <td key={o} className={td}>
                        {p ? (
                          <>
                            <div>TPR {fmtRate(p.tpr, p.tpr_ci)}</div>
                            <div className="text-slate-500">FPR {fmtRate(p.fpr, p.fpr_ci)}</div>
                          </>
                        ) : (
                          "–"
                        )}
                      </td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </Section>

      <div className="grid md:grid-cols-2 gap-3">
        <Section title="ROC — combined, test split" note="True-positive vs false-positive rate across every score cut-off.">
          <ResponsiveContainer width="100%" height={230}>
            <LineChart data={roc} margin={{ top: 8, right: 12, left: -8, bottom: 14 }}>
              <CartesianGrid stroke={GRID} />
              <XAxis type="number" dataKey="fpr" domain={[0, 1]} stroke={AXIS} fontSize={10} label={{ value: "FPR", position: "insideBottom", offset: -8, fill: AXIS, fontSize: 10 }} />
              <YAxis type="number" domain={[0, 1]} stroke={AXIS} fontSize={10} label={{ value: "TPR", angle: -90, position: "insideLeft", fill: AXIS, fontSize: 10 }} />
              <Tooltip {...TOOLTIP_STYLE} formatter={(v) => Number(v).toFixed(3)} />
              <ReferenceLine segment={[{ x: 0, y: 0 }, { x: 1, y: 1 }]} stroke="#475569" strokeDasharray="4 4" />
              <Line type="linear" dataKey="tpr" stroke="#38bdf8" dot={false} strokeWidth={2} isAnimationActive={false} />
            </LineChart>
          </ResponsiveContainer>
        </Section>

        <Section title="Combined system by source — test split" note="One row per dataset; the paper's macro average weights each equally.">
          <table className="w-full text-[11px] font-mono">
            <thead>
              <tr>
                <th className={th}>Source</th>
                <th className={th}>n</th>
                <th className={th}>Intervene TPR</th>
                <th className={th}>Intervene FPR</th>
              </tr>
            </thead>
            <tbody className="text-slate-300">
              {sources.map((s) => {
                const g = report.groups[`source:${s}|split:test`];
                const p = g.systems.combined.operating_points.intervene;
                return (
                  <tr key={s}>
                    <td className={`${td} font-sans`}>{s}</td>
                    <td className={td}>{fmtInt(g.n)}</td>
                    <td className={td}>{fmtRate(p.tpr, p.tpr_ci)}</td>
                    <td className={td}>{fmtRate(p.fpr, p.fpr_ci)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </Section>
      </div>

      <Section title="Attack detection by category" note="Share of attack samples (all splits) the combined score put above the alert / intervene thresholds.">
        <table className="w-full text-[11px] font-mono">
          <thead>
            <tr>
              <th className={th}>Source / category</th>
              <th className={th}>n</th>
              <th className={th}>Alert</th>
              <th className={th}>Intervene</th>
            </tr>
          </thead>
          <tbody className="text-slate-300">
            {cats.map(([k, v]) => (
              <tr key={k}>
                <td className={`${td} font-sans`}>{k}</td>
                <td className={td}>{fmtInt(v.n)}</td>
                <td className={td}>{fmtRate(v.alert / v.n)}</td>
                <td className={td}>{fmtRate(v.intervene / v.n)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Section>

      <div className="grid md:grid-cols-2 gap-3">
        <Section title="Latency per stage" note="Milliseconds per sample on the machine that ran the scan.">
          <table className="w-full text-[11px] font-mono">
            <thead>
              <tr>
                <th className={th}>Stage</th>
                <th className={th}>p50</th>
                <th className={th}>p95</th>
                <th className={th}>p99</th>
              </tr>
            </thead>
            <tbody className="text-slate-300">
              {latency.map(([k, v]) => (
                <tr key={k}>
                  <td className={`${td} font-sans`}>{k}</td>
                  <td className={td}>{fmtMs(v.p50)}</td>
                  <td className={td}>{fmtMs(v.p95)}</td>
                  <td className={td}>{fmtMs(v.p99)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Section>

        <Section title="Errors to inspect (dev split only)" note="Test-split errors are deliberately not shown, so detectors are never tuned on held-out data.">
          <div className="grid grid-cols-2 gap-3 text-[11px]">
            {[
              ["False positives", report.false_positives],
              ["False negatives", report.false_negatives],
            ].map(([title, rows]) => (
              <div key={title}>
                <div className="text-slate-400 mb-1">
                  {title} ({rows.length})
                </div>
                <ul className="space-y-0.5 font-mono text-slate-300 max-h-40 overflow-y-auto">
                  {rows.map((r) => (
                    <li key={r.id} className="truncate" title={`${r.id} · ${r.source}/${r.category}`}>
                      {r.score} · {r.id}
                    </li>
                  ))}
                  {rows.length === 0 && <li className="text-slate-500">none</li>}
                </ul>
              </div>
            ))}
          </div>
        </Section>
      </div>
    </div>
  );
}
