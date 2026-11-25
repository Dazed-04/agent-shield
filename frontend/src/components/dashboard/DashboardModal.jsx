import { X } from "lucide-react";
import LiveMetrics from "./LiveMetrics";

export default function DashboardModal({ open, onClose }) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 bg-black/75 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <div className="bg-[#141b2a] border border-slate-700 rounded-2xl w-full max-w-5xl max-h-[90vh] flex flex-col shadow-2xl overflow-hidden">
        <div className="flex justify-between items-center p-4 border-b border-slate-800 bg-slate-900/60">
          <div>
            <div className="text-sm font-semibold text-slate-100">Security Dashboard</div>
            <div className="text-[11px] text-slate-500">Metrics from the gateway audit log</div>
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-200 cursor-pointer" aria-label="Close">
            <X className="w-4 h-4" />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-4">
          <LiveMetrics />
        </div>
      </div>
    </div>
  );
}
