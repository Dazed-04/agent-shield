import { FileText, X, Check, Copy, Download } from "lucide-react";
import Tooltip from "../ui/Tooltip";

export default function ArtifactModal({
  artifact,
  onClose,
  onCopy,
  onDownload,
  copied,
}) {
  if (!artifact) return null;

  return (
    <div className="fixed inset-0 bg-black/80 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <div className="bg-[#141b2a] border border-slate-700 rounded-2xl w-full max-w-2xl max-h-[85vh] flex flex-col shadow-2xl overflow-hidden animate-in fade-in zoom-in-95 duration-150">
        <div className="flex justify-between items-center p-4 border-b border-slate-800 bg-slate-900/80">
          <div className="flex items-center gap-2">
            <FileText className="w-4 h-4 text-sky-400" />
            <span className="text-xs font-semibold text-slate-100">
              {artifact.name}
            </span>
            <span className="text-[10px] bg-slate-800 text-slate-400 px-2 py-0.5 rounded font-mono">
              {artifact.source}
            </span>
          </div>
          <Tooltip text="Close" position="left">
            <button
              onClick={onClose}
              className="text-slate-400 hover:text-slate-200 cursor-pointer"
            >
              <X className="w-4 h-4" />
            </button>
          </Tooltip>
        </div>

        <div className="flex-1 overflow-y-auto p-4">
          {artifact.type === "image" ? (
            <div className="flex justify-center items-center bg-slate-950 p-4 rounded-xl border border-slate-800">
              <img
                src={artifact.preview}
                alt={artifact.name}
                className="max-h-[50vh] object-contain rounded-lg"
              />
            </div>
          ) : (
            <pre className="text-xs font-mono text-slate-200 bg-slate-950 p-4 rounded-xl border border-slate-800 overflow-x-auto whitespace-pre-wrap leading-relaxed">
              {artifact.content}
            </pre>
          )}
        </div>

        <div className="flex justify-end gap-2 p-3 border-t border-slate-800 bg-slate-900/80 text-xs">
          {artifact.type !== "image" && (
            <button
              onClick={() => onCopy(artifact.content)}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-slate-700 hover:bg-slate-800 text-slate-300 font-medium transition cursor-pointer"
            >
              {copied ? (
                <Check className="w-3.5 h-3.5 text-emerald-400" />
              ) : (
                <Copy className="w-3.5 h-3.5" />
              )}
              <span>{copied ? "Copied" : "Copy Content"}</span>
            </button>
          )}
          <button
            onClick={() =>
              onDownload(
                artifact.name,
                artifact.type === "image" ? artifact.preview : artifact.content,
                artifact.type === "image",
              )
            }
            className="flex items-center gap-1.5 bg-sky-600 hover:bg-sky-500 text-white px-3.5 py-1.5 rounded-lg font-semibold transition cursor-pointer"
          >
            <Download className="w-3.5 h-3.5" />
            <span>Download File</span>
          </button>
        </div>
      </div>
    </div>
  );
}
