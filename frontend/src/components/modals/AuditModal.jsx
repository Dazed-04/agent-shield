import { X } from "lucide-react";

export default function AuditModal({
  category,
  logs,
  loading,
  onClose,
  getBadge,
}) {
  if (!category) return null;

  return (
    <div className="fixed inset-0 bg-black/75 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <div className="bg-[#141b2a] border border-slate-700 rounded-2xl w-full max-w-2xl max-h-[80vh] flex flex-col shadow-2xl overflow-hidden animate-in fade-in zoom-in-95 duration-150">
        <div className="flex justify-between items-center p-4 border-b border-slate-800 bg-slate-900/60">
          <div className="flex items-center gap-2">
            <span
              className={`px-2 py-0.5 rounded text-xs font-bold font-mono border ${getBadge(category).bg}`}
            >
              {category} QUEUE
            </span>
            <span className="text-xs text-slate-400">
              Historical Security Logs
            </span>
          </div>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-slate-200 cursor-pointer"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-4 space-y-2.5">
          {loading ? (
            <div className="text-center text-xs text-slate-500 py-10">
              Fetching logs...
            </div>
          ) : logs.length === 0 ? (
            <div className="text-center text-xs text-slate-500 py-10">
              No records found for category {category}.
            </div>
          ) : (
            logs.map((log) => (
              <div
                key={log.id}
                className="p-3 bg-slate-900/80 rounded-xl border border-slate-800 text-xs space-y-1.5"
              >
                <div className="flex justify-between items-center font-mono text-[10px] text-slate-400">
                  <span>Audit #{log.id}</span>
                  <span className="text-sky-400">
                    Risk: {log.risk_score} / 100
                  </span>
                  <span>{log.status}</span>
                </div>
                <div className="text-slate-200 font-medium text-[11px] line-clamp-2">
                  "{log.prompt}"
                </div>
                <div className="text-[10px] text-slate-400 italic">
                  {log.justification}
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
