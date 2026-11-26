import { AlertTriangle } from "lucide-react";
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { AXIS, GRID, TOOLTIP_STYLE, fmtInt, fmtMs, fmtRate } from "./format";

const th = "font-medium py-1 px-2 text-left text-slate-500";
const td = "py-1.5 px-2 border-t border-slate-800";

function Section({ title, note, children }) {
  return (
    <section className="p-3 bg-slate-900/50 border border-slate-800 rounded-xl">
      <h3 className="text-xs font-semibold text-slate-300">{title}</h3>
      {note && <p className="text-[10px] text-slate-500 mb-2">{note}</p>}
      <div className="overflow-x-auto">{children}</div>
    </section>
  );
}

const label = (key) => {
  const [system, role] = key.split("|");
  return role && role !== "n/a" ? `${system} · ${role}` : system;
};
const pct = (r) => (r.rate == null ? null : Math.round(1000 * r.rate) / 10);

function Matrix({ report, dim, title }) {
  const keys = Object.keys(report.breakdown).filter((k) => k.startsWith(`${dim}|`));
  const cols = [...new Set(keys.flatMap((k) => Object.keys(report.breakdown[k])))].sort();
  if (!cols.length) return null;
  return (
    <Section title={title} note="Share of attack scenarios whose goal was achieved, 95% Wilson interval [lo, hi] in %.">
      <table className="w-full text-[11px] font-mono">
        <thead>
          <tr>
            <th className={th}>System</th>
            {cols.map((c) => (
              <th key={c} className={th}>
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="text-slate-300">
          {keys.map((k) => (
            <tr key={k}>
              <td className={`${td} font-sans`}>{label(k.slice(dim.length + 1))}</td>
              {cols.map((c) => {
                const v = report.breakdown[k][c];
                return (
                  <td key={c} className={td}>
                    {v ? fmtRate(v.rate, v.ci) : "–"}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </Section>
  );
}

export default function AgentReport({ report }) {
  const meta = report.meta || {};
  const entries = Object.entries(report.systems);
  const unreliable = (b) => b.reliable === false; // reports written before this flag existed are treated as reliable
  const chart = entries.map(([k, b]) => ({
    name: label(k),
    attempted: unreliable(b) ? null : pct(b.asr_attempted),
    executed: unreliable(b) ? null : pct(b.asr_executed),
  }));
  const incomplete = meta.complete === false || entries.some(([, b]) => unreliable(b));
  const synthetic = String(meta.llm || "").startsWith("scripted");

  return (
    <div className="space-y-3">
      {synthetic && (
        <div className="flex gap-2 p-2.5 text-[11px] text-amber-300 bg-amber-950/20 border border-amber-900/40 rounded-lg">
          <AlertTriangle className="w-3.5 h-3.5 shrink-0 mt-0.5" />
          Synthetic run ({meta.llm}): a scripted stand-in for the model, not a real LLM. It validates the harness only;
          do not report these numbers as results.
        </div>
      )}

      {incomplete && (
        <div className="flex gap-2 p-2.5 text-[11px] text-rose-300 bg-rose-950/20 border border-rose-900/40 rounded-lg">
          <AlertTriangle className="w-3.5 h-3.5 shrink-0 mt-0.5" />
          Incomplete run: do not quote these numbers.
          {meta.complete === false && meta.stopped_reason ? ` It stopped early (${meta.stopped_reason}).` : ""} Systems with many
          provider errors are marked INCOMPLETE below. Continue with <code>agent-scan --resume {meta.run_id}</code>.
        </div>
      )}

      <Section
        title="Attack success and utility"
        note={`${fmtInt(meta.n_scenarios)} scenarios × ${fmtInt(meta.repeats)} repeat(s). ASR = attacker's goal actually achieved; 'attempted' = the model emitted the attacker's tool call. 95% Wilson intervals [lo, hi] in %.`}
      >
        <table className="w-full text-[11px] font-mono">
          <thead>
            <tr>
              <th className={th}>System</th>
              <th className={th}>Attacks</th>
              <th className={th}>Attempted</th>
              <th className={th}>ASR (executed)</th>
              <th className={th}>Utility (clean)</th>
              <th className={th}>Utility (attack)</th>
              <th className={th}>Stopped by shield</th>
              <th className={th}>Errors</th>
            </tr>
          </thead>
          <tbody className="text-slate-300">
            {entries.map(([k, b]) => unreliable(b) ? (
              <tr key={k}>
                <td className={`${td} font-sans`}>{label(k)}</td>
                <td className={td}>{fmtInt(b.attacks)}</td>
                <td className={`${td} text-rose-300 font-semibold`} colSpan={5}>INCOMPLETE</td>
                <td className={td}>{fmtInt(b.errors)} of {fmtInt(b.runs)}</td>
              </tr>
            ) : (
              <tr key={k}>
                <td className={`${td} font-sans`}>{label(k)}</td>
                <td className={td}>{fmtInt(b.attacks)}</td>
                <td className={td}>{fmtRate(b.asr_attempted.rate, b.asr_attempted.ci)}</td>
                <td className={`${td} text-rose-300 font-semibold`}>{fmtRate(b.asr_executed.rate, b.asr_executed.ci)}</td>
                <td className={td}>{fmtRate(b.utility_clean.rate, b.utility_clean.ci)}</td>
                <td className={td}>{fmtRate(b.utility_under_attack.rate, b.utility_under_attack.ci)}</td>
                <td className={td}>{fmtRate(b.stopped_by_shield.rate, b.stopped_by_shield.ci)}</td>
                <td className={td}>{fmtInt(b.errors)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Section>

      <Section title="Attempted vs executed attacks" note="The gap between the bars is what the defences stopped after the model was already fooled.">
        <ResponsiveContainer width="100%" height={entries.length * 44 + 50}>
          <BarChart data={chart} layout="vertical" margin={{ top: 4, right: 16, left: 8, bottom: 0 }}>
            <CartesianGrid stroke={GRID} horizontal={false} />
            <XAxis type="number" domain={[0, 100]} stroke={AXIS} fontSize={10} unit="%" />
            <YAxis type="category" dataKey="name" stroke={AXIS} fontSize={10} width={190} />
            <Tooltip {...TOOLTIP_STYLE} formatter={(v) => (v == null ? "–" : `${v}%`)} />
            <Legend wrapperStyle={{ fontSize: 11 }} itemSorter={null} />
            <Bar dataKey="attempted" name="Attempted" fill="#fbbf24" radius={[0, 3, 3, 0]} />
            <Bar dataKey="executed" name="Executed (ASR)" fill="#fb7185" radius={[0, 3, 3, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </Section>

      <Matrix report={report} dim="goal" title="ASR (executed) by attacker goal" />
      <Matrix report={report} dim="style" title="ASR (executed) by injection style" />

      <Section title="Latency per run" note="Whole agent run, including model calls.">
        <table className="w-full text-[11px] font-mono">
          <thead>
            <tr>
              <th className={th}>System</th>
              <th className={th}>p50</th>
              <th className={th}>p95</th>
              <th className={th}>p99</th>
            </tr>
          </thead>
          <tbody className="text-slate-300">
            {entries.map(([k, b]) => (
              <tr key={k}>
                <td className={`${td} font-sans`}>{label(k)}</td>
                <td className={td}>{fmtMs(b.latency_ms?.p50)}</td>
                <td className={td}>{fmtMs(b.latency_ms?.p95)}</td>
                <td className={td}>{fmtMs(b.latency_ms?.p99)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Section>
    </div>
  );
}
