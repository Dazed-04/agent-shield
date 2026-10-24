import { useState } from "react";
import { Copy, Check } from "lucide-react";

export default function CodeBlock({ language, value }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(value);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  return (
    <div className="relative my-2 rounded-xl bg-slate-950 border border-slate-800/80 overflow-hidden group/code">
      <div className="flex items-center justify-between px-3 py-1.5 bg-slate-900/80 border-b border-slate-800/60 text-[10px] text-slate-400 font-mono">
        <span>{language || "code"}</span>
        <button
          onClick={handleCopy}
          className="flex items-center gap-1 hover:text-slate-200 transition cursor-pointer"
          title="Copy code snippet"
        >
          {copied ? (
            <Check className="w-3 h-3 text-emerald-400" />
          ) : (
            <Copy className="w-3 h-3" />
          )}
          <span>{copied ? "Copied" : "Copy"}</span>
        </button>
      </div>
      <pre className="p-3 text-xs font-mono text-slate-300 overflow-x-auto whitespace-pre leading-relaxed">
        {value}
      </pre>
    </div>
  );
}
