import { ShieldAlert, X, Check } from "lucide-react";

export default function ApprovalModal({
  approval,
  onClose,
  onResolve,
  onGrantLease,
}) {
  if (!approval) return null;

  return (
    <div className="fixed inset-0 bg-black/75 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <div className="bg-[#141b2a] border border-slate-700 rounded-2xl w-full max-w-lg shadow-2xl overflow-hidden animate-in fade-in zoom-in-95 duration-150">
        <div className="flex justify-between items-center p-4 border-b border-slate-800 bg-slate-900/50">
          <div className="flex items-center gap-2 text-sm font-semibold text-slate-100">
            <ShieldAlert className="w-4 h-4 text-orange-400" />
            <span>Security Inspection: Audit #{approval.id}</span>
          </div>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-slate-200 cursor-pointer"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="p-5 space-y-4 text-xs">
          <div>
            <label className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider">
              Original User Prompt
            </label>
            <div className="mt-1 p-2.5 bg-slate-900 rounded-lg border border-slate-800 text-slate-200 font-mono text-[11px]">
              "{approval.prompt}"
            </div>
          </div>

          <div>
            <label className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider">
              Intercepted Tool Call & Payload
            </label>
            <pre className="mt-1 p-2.5 bg-slate-950 rounded-lg border border-slate-800 text-sky-300 font-mono text-[11px] overflow-x-auto">
              {JSON.stringify(approval.tool_calls_attempted, null, 2)}
            </pre>
          </div>

          <div className="flex gap-4">
            <div className="flex-1">
              <label className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider">
                Threat Justification
              </label>
              <p className="mt-1 text-amber-300/90 text-[11px] leading-relaxed">
                {approval.justification}
              </p>
            </div>
            <div className="text-right">
              <label className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider">
                Calculated Risk
              </label>
              <div className="mt-1 text-lg font-bold text-orange-400 font-mono">
                {approval.risk_score} / 100
              </div>
            </div>
          </div>
        </div>

        <div className="flex justify-end gap-2 p-4 border-t border-slate-800 bg-slate-900/50">
          <button
            onClick={onClose}
            className="px-3 py-1.5 rounded-lg border border-slate-700 text-slate-300 text-xs font-medium cursor-pointer hover:bg-slate-850"
          >
            Cancel
          </button>
          <button
            onClick={() => onResolve(approval.id, "REJECT")}
            className="flex items-center gap-1.5 bg-rose-600 hover:bg-rose-700 text-white px-3 py-1.5 rounded-lg text-xs font-semibold cursor-pointer"
          >
            <X className="w-3.5 h-3.5" /> Deny
          </button>
          <button
            onClick={() => onResolve(approval.id, "APPROVE")}
            className="flex items-center gap-1.5 bg-slate-700 hover:bg-slate-600 text-white px-3 py-1.5 rounded-lg text-xs font-semibold cursor-pointer"
          >
            Authorize Once
          </button>
          <button
            onClick={() => onGrantLease(approval)}
            className="flex items-center gap-1.5 bg-emerald-600 hover:bg-emerald-700 text-white px-3.5 py-1.5 rounded-lg text-xs font-semibold shadow-md cursor-pointer"
          >
            <Check className="w-3.5 h-3.5" /> Authorize Session (3 Uses)
          </button>
        </div>
      </div>
    </div>
  );
}
