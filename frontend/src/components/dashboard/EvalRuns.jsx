import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { AlertTriangle, RefreshCw } from "lucide-react";
import DetectorReport from "./DetectorReport";
import { fmtInt } from "./format";

const API_BASE = "/api";

function Pill({ children, tone = "slate" }) {
  const tones = {
    slate: "bg-slate-800 text-slate-300 border-slate-700",
    amber: "bg-amber-500/10 text-amber-300 border-amber-500/30",
    sky: "bg-sky-500/10 text-sky-300 border-sky-500/30",
  };
  return <span className={`px-1.5 py-0.5 rounded border text-[10px] font-mono ${tones[tone]}`}>{children}</span>;
}

export default function EvalRuns() {
  const [runs, setRuns] = useState(null);
  const [selected, setSelected] = useState(null);
  const [detail, setDetail] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const loadRuns = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const data = (await axios.get(`${API_BASE}/eval/runs`)).data;
      setRuns(data);
      setSelected((cur) => cur ?? data.find((r) => r.has_report)?.run_id ?? null);
    } catch (e) {
      setRuns(null);
      setError(
        e.response?.status === 403
          ? "Evaluation results are visible to administrators only."
          : e.response?.data?.detail || "Could not load evaluation runs.",
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadRuns();
  }, [loadRuns]);

  useEffect(() => {
    if (!selected) {
      setDetail(null);
      return;
    }
    let cancelled = false;
    setDetail(null);
    axios
      .get(`${API_BASE}/eval/runs/${encodeURIComponent(selected)}`)
      .then((r) => !cancelled && setDetail(r.data))
      .catch((e) => !cancelled && setError(e.response?.data?.detail || "Could not load this run."));
    return () => {
      cancelled = true;
    };
  }, [selected]);

  if (error)
    return <div className="p-3 text-xs text-rose-300 bg-rose-950/30 border border-rose-900/50 rounded-lg">{error}</div>;

  if (runs && runs.length === 0)
    return (
      <div className="text-xs text-slate-400 space-y-2 py-8 text-center">
        <div>No evaluation runs on this server yet.</div>
        <code className="block text-[11px] text-slate-300 bg-slate-900 border border-slate-800 rounded p-2 w-fit mx-auto">
          python -m evaluation scan &amp;&amp; python -m evaluation report &lt;run&gt;
        </code>
      </div>
    );

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <select
          value={selected ?? ""}
          onChange={(e) => setSelected(e.target.value || null)}
          className="flex-1 bg-slate-900 border border-slate-700 rounded-md text-[11px] text-slate-200 p-1.5 font-mono"
        >
          {(runs || []).map((r) => (
            <option key={r.run_id} value={r.run_id} disabled={!r.has_report}>
              {r.run_id}
              {r.has_report ? "" : "  (no report yet)"}
            </option>
          ))}
        </select>
        <button onClick={loadRuns} className="text-slate-400 hover:text-sky-400 cursor-pointer" title="Refresh">
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
        </button>
      </div>

      {detail && (
        <>
          <div className="flex flex-wrap gap-1.5">
            <Pill tone="sky">{detail.kind === "agent" ? "end-to-end" : "detector-level"}</Pill>
            {detail.git_sha && <Pill>commit {detail.git_sha.slice(0, 8)}</Pill>}
            {detail.git_dirty && <Pill tone="amber">uncommitted changes</Pill>}
            {detail.jailbreak_mode && (
              <Pill tone={detail.jailbreak_mode === "semantic" ? "slate" : "amber"}>{detail.jailbreak_mode} mode</Pill>
            )}
            {detail.n_samples != null && <Pill>{fmtInt(detail.n_samples)} samples</Pill>}
            {detail.llm && <Pill tone={detail.synthetic ? "amber" : "slate"}>{detail.llm}</Pill>}
          </div>

          {detail.jailbreak_mode === "heuristic" && (
            <div className="flex gap-2 p-2.5 text-[11px] text-amber-300 bg-amber-950/20 border border-amber-900/40 rounded-lg">
              <AlertTriangle className="w-3.5 h-3.5 shrink-0 mt-0.5" />
              This run used the keyword fallback, not the semantic model. Re-run with embeddings enabled before quoting
              these numbers.
            </div>
          )}

          {detail.kind === "detector" && <DetectorReport report={detail.report} />}
        </>
      )}
    </div>
  );
}
