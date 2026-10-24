import {
  ChevronRight,
  ChevronLeft,
  Pencil,
  Check,
  X,
  UserCheck,
  Info,
  Shield,
} from "lucide-react";
import Tooltip from "../ui/Tooltip";
import CustomDropdown from "../ui/CustomDropdown";

export default function Header({
  isLeftOpen,
  onOpenLeft,
  isRightOpen,
  onOpenRight,
  activeSession,
  isEditingTitle,
  titleInput,
  onStartRename,
  onSaveRename,
  onCancelRename,
  onTitleInputChange,
  serverMode,
  selectedRole,
  onRoleChange,
  totalTokensUsed,
  currentSessionBlockedCount,
  pendingApprovalsCount,
}) {
  return (
    <header className="w-full flex items-center justify-between px-4 md:px-6 py-2.5 border-b border-slate-800/60 text-xs flex-shrink-0 z-10 bg-[#0b0f19]">
      {/* 1. Left Side: Navigation Expand + Inline Chat Title */}
      <div className="flex items-center gap-2 pl-8 md:pl-0">
        {!isLeftOpen && (
          <Tooltip text="Expand Navigation" position="right">
            <button
              onClick={onOpenLeft}
              className="p-1.5 rounded-lg border border-slate-800 hover:border-slate-700 bg-slate-900 text-slate-400 hover:text-white shadow-sm transition cursor-pointer mr-1"
            >
              <ChevronRight className="w-4 h-4 text-sky-400" />
            </button>
          </Tooltip>
        )}

        {isEditingTitle ? (
          <div className="flex items-center gap-1.5">
            <input
              type="text"
              value={titleInput}
              onChange={(e) => onTitleInputChange(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") onSaveRename();
                if (e.key === "Escape") onCancelRename();
              }}
              autoFocus
              className="bg-slate-900 border border-sky-500/60 rounded-md px-2 py-0.5 text-xs text-slate-200 focus:outline-none w-48 font-medium"
            />
            <button
              onClick={onSaveRename}
              className="p-1 text-emerald-400 hover:text-emerald-300 cursor-pointer"
            >
              <Check className="w-3.5 h-3.5" />
            </button>
            <button
              onClick={onCancelRename}
              className="p-1 text-slate-400 hover:text-rose-400 cursor-pointer"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
        ) : (
          <div className="flex items-center gap-1.5 group/title">
            <span className="text-slate-300 font-medium truncate max-w-sm">
              {activeSession?.title || "Conversation"}
            </span>
            <Tooltip text="Rename Chat" position="bottom">
              <button
                onClick={onStartRename}
                className="opacity-0 group-hover/title:opacity-100 p-1 text-slate-500 hover:text-sky-400 transition cursor-pointer"
              >
                <Pencil className="w-3 h-3" />
              </button>
            </Tooltip>
          </div>
        )}
      </div>

      {/* 2. Right Side: All Telemetry, Role Controls & Drawer Toggle Grouped Together */}
      <div className="flex items-center gap-2.5">
        {/* Cumulative Tokens */}
        <Tooltip text="Cumulative API tokens processed" position="bottom">
          <div className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-slate-900/90 border border-slate-800 text-slate-400 font-mono text-[11px] select-none">
            <Info className="w-3.5 h-3.5 text-slate-400" />
            <span>{totalTokensUsed.toLocaleString()} Tokens</span>
          </div>
        </Tooltip>

        {/* Blocked Threats (Current Session) */}
        <Tooltip text="Threats blocked in this session" position="bottom">
          <div className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-slate-900/90 border border-slate-800 text-slate-400 font-mono text-[11px] select-none">
            <Shield className="w-3.5 h-3.5 text-slate-500" />
            <span className="text-slate-300 font-bold">
              {currentSessionBlockedCount}
            </span>
          </div>
        </Tooltip>

        {/* Role Switcher: Next to Shield, switchable in DEV mode, locked in PROD */}
        {serverMode === "development" ? (
          <CustomDropdown
            icon={UserCheck}
            value={selectedRole}
            options={[
              { value: "Standard Users", label: "Standard Users" },
              { value: "Data Science", label: "Data Science" },
              { value: "Domain Admins", label: "Domain Admins" },
            ]}
            onChange={onRoleChange}
            tooltipText="Dev Mode: Switch Role"
          />
        ) : (
          <Tooltip text="Production: Server-Enforced Role" position="bottom">
            <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-slate-900/80 border border-slate-800 text-slate-400 font-mono text-[11px] select-none">
              <UserCheck className="w-3.5 h-3.5 text-slate-500" />
              <span>{selectedRole}</span>
            </div>
          </Tooltip>
        )}

        {/* Single Right Edge Toggle (<) */}
        {!isRightOpen && (
          <Tooltip
            text="Open Workspace Inspector"
            position="bottom"
            align="right"
          >
            <button
              onClick={onOpenRight}
              className={`p-1.5 rounded-lg border transition flex items-center justify-center relative cursor-pointer ${
                pendingApprovalsCount > 0
                  ? "bg-orange-500/20 border-orange-500/50 text-orange-300 shadow-lg shadow-orange-500/20"
                  : "bg-slate-900 border-slate-800 text-slate-400 hover:text-slate-200"
              }`}
            >
              {pendingApprovalsCount > 0 && (
                <span className="relative flex h-2 w-2 mr-1">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-orange-400 opacity-75" />
                  <span className="relative inline-flex rounded-full h-2 w-2 bg-orange-500" />
                </span>
              )}
              <ChevronLeft className="w-4 h-4 text-sky-400" />
              {pendingApprovalsCount > 0 && (
                <span className="ml-1 px-1 py-0.2 rounded-full bg-orange-500/30 text-orange-200 font-mono text-[10px]">
                  {pendingApprovalsCount}
                </span>
              )}
            </button>
          </Tooltip>
        )}
      </div>
    </header>
  );
}
