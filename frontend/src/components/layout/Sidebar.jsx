import {
  Plus,
  Download,
  MessageSquare,
  Trash2,
  Pencil,
  ChevronLeft,
  RefreshCw,
} from "lucide-react";
import ModernLogo from "../ui/ModernLogo";
import Tooltip from "../ui/Tooltip";

export default function Sidebar({
  isOpen,
  onClose,
  sessions,
  currentSessionId,
  onSelectSession,
  onDeleteSession,
  onStartRename,
  onNewChat,
  onExportMarkdown,
  presets,
  onRunPreset,
  analytics,
  onRefreshTelemetry,
  onOpenCategoryLogs,
}) {
  return (
    <aside
      className={`border-r border-slate-800/80 bg-[#101625] flex flex-col transition-all duration-300 ease-in-out overflow-hidden z-20 flex-shrink-0 ${
        isOpen ? "w-72 p-4" : "w-0 p-0 border-none"
      }`}
    >
      <div className="flex items-center justify-between pb-3 border-b border-slate-800 min-w-[250px]">
        <div className="flex items-center gap-2.5">
          <ModernLogo />
          <div>
            <h1 className="text-xs font-bold text-white tracking-wider uppercase">
              Agent Shield
            </h1>
            <p className="text-[10px] text-sky-400 font-medium">
              Security Gateway
            </p>
          </div>
        </div>
        <Tooltip position="right">
          <button
            onClick={onClose}
            className="p-1.5 text-slate-400 hover:text-slate-200 rounded-lg hover:bg-slate-800/60 cursor-pointer"
          >
            <ChevronLeft className="w-4 h-4" />
          </button>
        </Tooltip>
      </div>

      <div className="flex gap-2 mt-3 min-w-[250px]">
        <button
          onClick={onNewChat}
          className="flex-1 flex items-center justify-center gap-1.5 py-1.5 px-3 rounded-lg bg-sky-500/10 hover:bg-sky-500/20 border border-sky-500/30 text-sky-300 text-xs font-semibold transition cursor-pointer"
        >
          <Plus className="w-3.5 h-3.5" /> New Chat
        </button>
        <Tooltip text="Export Markdown Report" position="bottom" align="right">
          <button
            onClick={onExportMarkdown}
            className="p-1.5 rounded-lg border border-slate-800 hover:border-slate-700 bg-slate-900 text-slate-400 hover:text-slate-200 transition cursor-pointer"
          >
            <Download className="w-4 h-4" />
          </button>
        </Tooltip>
      </div>

      <div className="mt-3 flex-1 overflow-y-auto space-y-1 pr-1 max-h-36 border-b border-slate-800/80 pb-2 min-w-[250px]">
        <div className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider px-1">
          Chats
        </div>
        {sessions.map((s) => (
          <div
            key={s.id}
            onClick={() => onSelectSession(s.id)}
            className={`flex items-center justify-between p-2 rounded-lg text-xs cursor-pointer transition group ${
              s.id === currentSessionId
                ? "bg-slate-800 text-sky-300 font-medium"
                : "text-slate-400 hover:bg-slate-900/60"
            }`}
          >
            <div className="flex items-center gap-2 truncate flex-1 mr-1">
              <MessageSquare className="w-3.5 h-3.5 flex-shrink-0" />
              <span className="truncate">{s.title || "Conversation"}</span>
            </div>
            <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition">
              <Tooltip text="Rename" position="bottom" align="right">
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    onStartRename(s);
                  }}
                  className="hover:text-sky-400 p-0.5 cursor-pointer"
                >
                  <Pencil className="w-3 h-3" />
                </button>
              </Tooltip>
              <Tooltip text="Delete" position="bottom" align="right">
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    onDeleteSession(s.id);
                  }}
                  className="hover:text-rose-400 p-0.5 cursor-pointer"
                >
                  <Trash2 className="w-3 h-3" />
                </button>
              </Tooltip>
            </div>
          </div>
        ))}
      </div>

      <div className="mt-3 flex-1 overflow-y-auto min-w-[250px]">
        <div className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider mb-2 px-1">
          Verification Scenarios
        </div>
        <div className="space-y-1.5">
          {presets.map((item, idx) => (
            <button
              key={idx}
              onClick={() => onRunPreset(item.prompt)}
              className="w-full text-left p-2 rounded-lg border border-slate-800/80 hover:border-sky-500/40 bg-slate-900/40 hover:bg-slate-800/60 transition group cursor-pointer"
            >
              <div className="text-xs font-medium text-slate-300 group-hover:text-sky-300 flex items-center justify-between">
                <span>{item.label}</span>
                <span className="text-[10px] text-slate-500 font-mono">
                  Run ↗
                </span>
              </div>
              <div className="text-[10px] text-slate-500 truncate mt-0.5">
                {item.prompt}
              </div>
            </button>
          ))}
        </div>
      </div>

      {analytics && (
        <div className="pt-3 border-t border-slate-800 text-xs min-w-[250px]">
          <div className="flex justify-between items-center text-slate-400 mb-2">
            <span className="text-[10px] font-semibold uppercase tracking-wider">
              Gateway Telemetry
            </span>
            <Tooltip text="Refresh Telemetry" position="top" align="right">
              <button
                onClick={onRefreshTelemetry}
                className="hover:text-sky-400 cursor-pointer"
              >
                <RefreshCw className="w-3 h-3" />
              </button>
            </Tooltip>
          </div>
          <div className="grid grid-cols-2 gap-1.5 text-center text-[10px] font-mono">
            <Tooltip text="Inspect ALLOW queue" position="top" align="left">
              <div
                onClick={() => onOpenCategoryLogs("ALLOW")}
                className="p-1.5 bg-emerald-950/20 hover:bg-emerald-900/40 border border-emerald-800/40 text-emerald-400 rounded cursor-pointer transition w-full"
              >
                ALLOW: {analytics.breakdown?.ALLOW || 0}
              </div>
            </Tooltip>
            <Tooltip text="Inspect WARN queue" position="top" align="right">
              <div
                onClick={() => onOpenCategoryLogs("WARN")}
                className="p-1.5 bg-amber-950/20 hover:bg-amber-900/40 border border-amber-800/40 text-amber-400 rounded cursor-pointer transition w-full"
              >
                WARN: {analytics.breakdown?.WARN || 0}
              </div>
            </Tooltip>
            <Tooltip text="Inspect APPROVE queue" position="top" align="left">
              <div
                onClick={() => onOpenCategoryLogs("APPROVE")}
                className="p-1.5 bg-orange-950/20 hover:bg-orange-900/40 border border-orange-800/40 text-orange-400 rounded cursor-pointer transition w-full"
              >
                APPROVE: {analytics.breakdown?.APPROVE || 0}
              </div>
            </Tooltip>
            <Tooltip text="Inspect BLOCK queue" position="top" align="right">
              <div
                onClick={() => onOpenCategoryLogs("BLOCK")}
                className="p-1.5 bg-rose-950/20 hover:bg-rose-900/40 border border-rose-800/40 text-rose-400 rounded cursor-pointer transition w-full"
              >
                BLOCK: {analytics.breakdown?.BLOCK || 0}
              </div>
            </Tooltip>
          </div>
        </div>
      )}
    </aside>
  );
}
