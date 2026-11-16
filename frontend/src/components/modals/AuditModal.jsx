import { useState } from "react";
import axios from "axios";
import { X, Flag, Check } from "lucide-react";

const API_BASE = "http://127.0.0.1:8000/api";

export default function AuditModal({
  category,
  logs,
  loading,
  onClose,
  getBadge,
}) {
  const [flaggedIds, setFlaggedIds] = useState({});

  if (!category) return null;

  const handleFlagAsThreat = async (logId, promptText) => {
    try {
      await axios.post(`${API_BASE}/threats/learn`, {
        threat_text: promptText,
      });
      setFlaggedIds((prev) => ({ ...prev, [logId]: true }));
    } catch (err) {
      console.error("Failed to vectorize threat:", err);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/75 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <div className="bg-[#141b2a] border border-slate-700 rounded-2xl w-full max-w-2xl max-h-[80vh] flex flex-col shadow-2xl overflow-hidden animate-in fade-in zoom-in-95 duration-150">
        {/* Header */}
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

        {/* Log Entries */}
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
                className="p-3 bg-slate-900/80 rounded-xl border border-slate-800 text-xs space-y-2 shadow-sm"
              >
                <div className="flex justify-between items-center font-mono text-[10px] text-slate-400">
                  <span>Audit #{log.id}</span>
                  <span className="text-sky-400 font-semibold">
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

                {/* Card Action Footer */}
                <div className="flex justify-between items-center pt-2 border-t border-slate-800/60 mt-1">
                  <span className="text-[10px] text-slate-500 font-mono">
                    {log.timestamp
                      ? new Date(log.timestamp).toLocaleTimeString([], {
                          hour: "2-digit",
                          minute: "2-digit",
                        })
                      : ""}
                  </span>
                  <button
                    onClick={() => handleFlagAsThreat(log.id, log.prompt)}
                    disabled={flaggedIds[log.id]}
                    className={`flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[10px] font-medium transition cursor-pointer ${
                      flaggedIds[log.id]
                        ? "bg-amber-500/20 text-amber-300 border border-amber-500/40"
                        : "bg-slate-800 hover:bg-slate-750 text-slate-300 hover:text-white border border-slate-700/80"
                    }`}
                    title="Add this prompt to the persistent threat vector store"
                  >
                    {flaggedIds[log.id] ? (
                      <>
                        <Check className="w-3 h-3 text-amber-400" />
                        <span>Vectorized</span>
                      </>
                    ) : (
                      <>
                        <Flag className="w-3 h-3 text-amber-400" />
                        <span>Flag as Threat</span>
                      </>
                    )}
                  </button>
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
