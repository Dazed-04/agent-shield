import { useState } from "react";
import { X } from "lucide-react";
import LiveMetrics from "./LiveMetrics";
import EvalRuns from "./EvalRuns";

const TABS = [
  { id: "live", label: "Live metrics" },
  { id: "eval", label: "Evaluation runs" },
];

export default function DashboardModal({ open, onClose }) {
  const [tab, setTab] = useState("live");
  if (!open) return null;
  return (
    <div className="fixed inset-0 bg-black/75 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <div className="bg-[#141b2a] border border-slate-700 rounded-2xl w-full max-w-5xl max-h-[90vh] flex flex-col shadow-2xl overflow-hidden">
        <div className="flex justify-between items-center p-4 border-b border-slate-800 bg-slate-900/60">
          <div>
            <div className="text-sm font-semibold text-slate-100">Security Dashboard</div>
            <div className="text-[11px] text-slate-500">Gateway audit log and saved evaluation runs</div>
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-200 cursor-pointer" aria-label="Close">
            <X className="w-4 h-4" />
          </button>
        </div>
        <div className="flex gap-1 px-4 pt-3 border-b border-slate-800">
          {TABS.map((t) => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={`px-3 py-1.5 text-xs rounded-t-md border-b-2 cursor-pointer transition ${
                tab === t.id ? "text-sky-300 border-sky-400" : "text-slate-400 border-transparent hover:text-slate-200"
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>
        <div className="flex-1 overflow-y-auto p-4">{tab === "live" ? <LiveMetrics /> : <EvalRuns />}</div>
      </div>
    </div>
  );
}
