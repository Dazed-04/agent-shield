import {
  Paperclip,
  Square,
  CornerDownLeft,
  X,
  ImageIcon,
  FileText,
} from "lucide-react";
import Tooltip from "../ui/Tooltip";

export default function InputBar({
  prompt,
  onPromptChange,
  onSend,
  loading,
  onStop,
  attachedFile,
  onRemoveFile,
  onFileUpload,
  textareaRef,
  fileInputRef,
}) {
  return (
    <div className="w-full px-4 md:px-6 pb-4 pt-1 flex flex-col items-center flex-shrink-0">
      <div className="w-full max-w-4xl">
        {attachedFile && (
          <div className="flex items-center gap-2 mb-2 p-1.5 bg-slate-800 border border-slate-700 rounded-lg text-xs w-fit">
            {attachedFile.type === "image" ? (
              <ImageIcon className="w-3.5 h-3.5 text-sky-400" />
            ) : (
              <FileText className="w-3.5 h-3.5 text-sky-400" />
            )}
            <span className="text-slate-200 font-medium">
              {attachedFile.name}
            </span>
            <button
              onClick={onRemoveFile}
              className="text-slate-400 hover:text-rose-400 ml-1 cursor-pointer"
            >
              <X className="w-3 h-3" />
            </button>
          </div>
        )}

        <div className="relative flex items-center bg-[#131927] border border-slate-700/80 focus-within:border-sky-500/80 rounded-2xl shadow-xl transition-all px-2 py-1">
          <input
            type="file"
            ref={fileInputRef}
            onChange={onFileUpload}
            accept=".txt,.md,image/*"
            className="hidden"
          />
          <Tooltip text="Attach File" position="top">
            <button
              onClick={() => fileInputRef.current?.click()}
              className="p-1.5 text-slate-400 hover:text-sky-400 transition flex items-center justify-center cursor-pointer"
            >
              <Paperclip className="w-4 h-4" />
            </button>
          </Tooltip>

          <textarea
            ref={textareaRef}
            value={prompt}
            onChange={(e) => onPromptChange(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
                e.preventDefault();
                if (!loading) onSend();
              }
            }}
            placeholder={
              loading ? "Agent reasoning in progress..." : "Reply..."
            }
            className="flex-1 bg-transparent text-sm text-slate-100 px-2.5 py-1.5 focus:outline-none placeholder-slate-500 resize-none max-h-40 min-h-[36px] overflow-y-auto leading-relaxed"
            rows={1}
            disabled={loading}
          />

          {loading ? (
            <Tooltip text="Stop" position="top">
              <button
                onClick={onStop}
                className="p-1.5 rounded-xl bg-rose-500 hover:bg-rose-600 text-white transition shadow-md flex items-center justify-center cursor-pointer"
              >
                <Square className="w-3.5 h-3.5 fill-white" />
              </button>
            </Tooltip>
          ) : (
            <Tooltip text="Send (Ctrl + Enter)" position="top">
              <button
                onClick={() => {
                  if ((prompt.trim() || attachedFile) && !loading) onSend();
                }}
                className={`flex items-center py-1 px-2.5 rounded-xl border text-[11px] font-mono transition-all duration-150 ${
                  prompt.trim() || attachedFile
                    ? "bg-sky-500 hover:bg-sky-400 text-slate-950 font-semibold border-sky-400 cursor-pointer shadow-md"
                    : "bg-slate-800/40 hover:bg-slate-800 border-slate-800/80 hover:border-slate-700 text-slate-500 hover:text-slate-300 cursor-default"
                }`}
              >
                <span className="flex items-center gap-1">
                  Ctrl
                  <CornerDownLeft className="w-2.5 h-2.5" />
                </span>
              </button>
            </Tooltip>
          )}
        </div>
      </div>
    </div>
  );
}
