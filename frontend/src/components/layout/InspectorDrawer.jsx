import {
  ChevronRight,
  Package,
  ShieldAlert,
  FileArchive,
  ImageIcon,
  Code,
  FileText,
  Check,
  Terminal,
} from "lucide-react";
import Tooltip from "../ui/Tooltip";
import CustomDropdown from "../ui/CustomDropdown";

export default function InspectorDrawer({
  isOpen,
  onClose,
  availableModels,
  selectedModel,
  onModelChange,
  activeTab,
  onTabChange,
  artifacts,
  onSelectArtifact,
  onDownloadAllArtifacts,
  pendingApprovals,
  onSelectApproval,
}) {
  return (
    <aside
      className={`border-l border-slate-800/80 bg-[#101625] flex flex-col transition-all duration-300 ease-in-out overflow-hidden z-20 flex-shrink-0 ${
        isOpen ? "w-80 p-4" : "w-0 p-0 border-none"
      }`}
    >
      <div className="flex items-center justify-between pb-3 border-b border-slate-800 min-w-[280px]">
        <span className="text-xs font-bold text-white uppercase tracking-wider">
          Workspace Inspector
        </span>
        <Tooltip>
          <button
            onClick={onClose}
            className="p-1 text-slate-400 hover:text-slate-200 rounded-lg hover:bg-slate-800/60 cursor-pointer"
          >
            <ChevronRight className="w-4 h-4" />
          </button>
        </Tooltip>
      </div>

      {availableModels.length > 0 && (
        <div className="mt-3 min-w-[280px] space-y-1">
          <span className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider px-1">
            Active AI Provider
          </span>
          <div className="w-full">
            <CustomDropdown
              value={selectedModel}
              options={availableModels.map((m) => ({
                value: m.id,
                label: m.name,
              }))}
              onChange={onModelChange}
              tooltipText="Select active LLM Provider"
            />
          </div>
        </div>
      )}

      <div className="flex bg-slate-900/90 p-1 rounded-xl border border-slate-800 gap-1 my-3 min-w-[280px]">
        <button
          onClick={() => onTabChange("artifacts")}
          className={`flex-1 flex items-center justify-center gap-1.5 py-1.5 text-xs font-semibold rounded-lg transition cursor-pointer ${
            activeTab === "artifacts"
              ? "bg-slate-800 text-sky-300 shadow-sm"
              : "text-slate-400 hover:text-slate-200"
          }`}
        >
          <Package className="w-3.5 h-3.5" />
          <span>Artifacts</span>
          {artifacts.length > 0 && (
            <span className="px-1.5 py-0.2 rounded-full bg-slate-700 text-slate-300 text-[10px] font-mono">
              {artifacts.length}
            </span>
          )}
        </button>

        <button
          onClick={() => onTabChange("review")}
          className={`flex-1 flex items-center justify-center gap-1.5 py-1.5 text-xs font-semibold rounded-lg transition cursor-pointer ${
            activeTab === "review"
              ? "bg-slate-800 text-orange-300 shadow-sm"
              : "text-slate-400 hover:text-slate-200"
          }`}
        >
          <ShieldAlert className="w-3.5 h-3.5" />
          <span>Review Queue</span>
          {pendingApprovals.length > 0 && (
            <span className="px-1.5 py-0.2 rounded-full bg-orange-500/30 text-orange-200 text-[10px] font-mono font-bold animate-pulse">
              {pendingApprovals.length}
            </span>
          )}
        </button>
      </div>

      {activeTab === "artifacts" && (
        <div className="flex-1 overflow-y-auto min-w-[280px] space-y-3">
          <div className="flex justify-between items-center px-1">
            <span className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider">
              Session Files
            </span>
            {artifacts.length > 0 && (
              <button
                onClick={onDownloadAllArtifacts}
                className="flex items-center gap-1 text-[10px] text-sky-400 hover:text-sky-300 font-medium cursor-pointer"
              >
                <FileArchive className="w-3 h-3" />
                <span>Download All</span>
              </button>
            )}
          </div>

          {artifacts.length === 0 ? (
            <div className="text-center text-slate-500 text-xs py-16 px-4">
              <Package className="w-7 h-7 mx-auto mb-2 text-slate-600 opacity-60" />
              No artifacts or code snippets generated yet.
            </div>
          ) : (
            <div className="grid grid-cols-2 gap-2.5">
              {artifacts.map((art) => (
                <div
                  key={art.id}
                  onClick={() => onSelectArtifact(art)}
                  className="p-3 bg-slate-900/90 hover:bg-slate-850 rounded-xl border border-slate-800 hover:border-sky-500/50 cursor-pointer transition flex flex-col items-center justify-center text-center space-y-2 group shadow-sm"
                  title={`Click to inspect ${art.name}`}
                >
                  <div className="p-2.5 rounded-xl bg-slate-950 border border-slate-800 group-hover:scale-105 transition">
                    {art.type === "image" ? (
                      <ImageIcon className="w-6 h-6 text-purple-400" />
                    ) : art.type.includes("python") ||
                      art.name.endsWith(".py") ? (
                      <Code className="w-6 h-6 text-emerald-400" />
                    ) : (
                      <FileText className="w-6 h-6 text-sky-400" />
                    )}
                  </div>
                  <span className="text-[11px] font-medium text-slate-300 group-hover:text-sky-300 truncate w-full px-1">
                    {art.name}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {activeTab === "review" && (
        <div className="flex-1 overflow-y-auto space-y-2 min-w-[280px]">
          <div className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider px-1">
            Pending Actions
          </div>
          {pendingApprovals.length === 0 ? (
            <div className="text-center text-slate-500 text-xs py-16 px-4">
              <Check className="w-6 h-6 mx-auto mb-2 text-slate-600" />
              No actions currently held for review.
            </div>
          ) : (
            pendingApprovals.map((item) => {
              const toolName =
                item.tool_calls_attempted?.[0]?.name || "Privileged Tool";
              return (
                <div
                  key={item.id}
                  onClick={() => onSelectApproval(item)}
                  className="p-2.5 bg-slate-900/90 hover:bg-slate-850 rounded-xl border border-orange-500/30 hover:border-orange-500/60 transition cursor-pointer text-xs space-y-1 shadow-sm group"
                >
                  <div className="flex justify-between items-center font-mono text-[10px]">
                    <span className="text-slate-400">Audit #{item.id}</span>
                    <span className="text-orange-400 font-bold bg-orange-500/10 px-1.5 py-0.5 rounded border border-orange-500/20">
                      Risk: {item.risk_score}
                    </span>
                  </div>
                  <div className="font-semibold text-slate-200 group-hover:text-sky-300 flex items-center gap-1.5 text-xs truncate">
                    <Terminal className="w-3.5 h-3.5 text-orange-400 flex-shrink-0" />
                    <span>{toolName}</span>
                  </div>
                  <div className="flex justify-between items-center text-[10px] text-slate-500 pt-0.5">
                    <span>Click to inspect</span>
                    <span className="group-hover:text-sky-400 font-mono">
                      Review ↗
                    </span>
                  </div>
                </div>
              );
            })
          )}
        </div>
      )}
    </aside>
  );
}
