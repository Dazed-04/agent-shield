import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  Clock,
  Copy,
  Pencil,
  Paperclip,
  Eye,
  ChevronDown,
  ChevronUp,
} from "lucide-react";
import Tooltip from "../ui/Tooltip";
import CodeBlock from "../ui/CodeBlock";
import ModernLogo from "../ui/ModernLogo";

export default function ChatFeed({
  messages,
  loading,
  collapsedResponses,
  onToggleCollapse,
  editingIndex,
  editPromptText,
  onStartEdit,
  onSaveEdit,
  onCancelEdit,
  onEditPromptChange,
  onCopy,
  onSelectArtifact,
  getBadge,
  messagesEndRef,
}) {
  return (
    <div className="w-full flex-1 overflow-y-auto px-4 md:px-6 py-4">
      <div className="max-w-4xl mx-auto space-y-4">
        {messages.length === 0 ? (
          <div className="h-[60vh] flex flex-col items-center justify-center text-center text-slate-500 space-y-3">
            <ModernLogo />
            <div>
              <h2 className="text-sm font-semibold text-slate-200">
                Agent Shield Gateway Active
              </h2>
              <p className="text-xs text-slate-400 max-w-sm mt-1">
                Prompt your agent or test an attack payload from the
                verification menu.
              </p>
            </div>
          </div>
        ) : (
          messages.map((m, idx) => (
            <div key={idx} className="space-y-1.5 group">
              {m.role === "user" ? (
                <div className="flex justify-end items-start gap-2">
                  {editingIndex === idx ? (
                    <div className="flex-1 max-w-2xl bg-slate-900 border border-sky-500/50 rounded-2xl p-3 space-y-2">
                      <textarea
                        value={editPromptText}
                        onChange={(e) => onEditPromptChange(e.target.value)}
                        className="w-full bg-transparent text-sm text-slate-100 focus:outline-none resize-none font-sans"
                        rows={3}
                      />
                      <div className="flex justify-end gap-2 text-xs">
                        <button
                          onClick={onCancelEdit}
                          className="px-2.5 py-1 rounded-lg border border-slate-700 hover:bg-slate-800 text-slate-400 cursor-pointer"
                        >
                          Cancel
                        </button>
                        <button
                          onClick={() => onSaveEdit(idx)}
                          className="px-3 py-1 rounded-lg bg-sky-500 hover:bg-sky-600 text-slate-950 font-semibold cursor-pointer"
                        >
                          Save & Fork
                        </button>
                      </div>
                    </div>
                  ) : (
                    <div className="flex items-center gap-1.5 max-w-2xl">
                      <Tooltip text="Copy prompt" position="left">
                        <button
                          onClick={() => onCopy(m.content)}
                          className="opacity-0 group-hover:opacity-100 text-slate-500 hover:text-slate-300 p-1 transition cursor-pointer"
                        >
                          <Copy className="w-3.5 h-3.5" />
                        </button>
                      </Tooltip>
                      <Tooltip text="Edit & branch" position="left">
                        <button
                          onClick={() => onStartEdit(idx, m.content)}
                          className="opacity-0 group-hover:opacity-100 text-slate-500 hover:text-sky-400 p-1 transition cursor-pointer"
                        >
                          <Pencil className="w-3.5 h-3.5" />
                        </button>
                      </Tooltip>
                      <div className="bg-sky-600 text-white text-sm px-4 py-2.5 rounded-2xl shadow-sm leading-relaxed whitespace-pre-wrap">
                        {m.attachmentData && (
                          <button
                            onClick={() => onSelectArtifact(m.attachmentData)}
                            className="flex items-center gap-2 text-[11px] bg-sky-700/80 hover:bg-sky-800 px-2.5 py-1.5 rounded-lg mb-2 text-sky-100 transition border border-sky-400/30 shadow-sm group/att cursor-pointer w-fit"
                          >
                            <Paperclip className="w-3 h-3 text-sky-300 group-hover/att:scale-110 transition" />
                            <span className="font-medium underline underline-offset-2">
                              {m.attachmentData.name}
                            </span>
                            <Eye className="w-3 h-3 opacity-70 group-hover/att:opacity-100 ml-1" />
                          </button>
                        )}
                        {m.content}
                      </div>
                    </div>
                  )}
                </div>
              ) : (
                <div className="flex flex-col items-start max-w-3xl space-y-1.5">
                  {collapsedResponses[idx] ? (
                    <div
                      onClick={() => onToggleCollapse(idx)}
                      className="w-full flex items-center justify-between p-3 bg-[#141b2a] hover:bg-[#182032] border border-slate-800 rounded-2xl text-xs cursor-pointer transition select-none"
                    >
                      <div className="flex items-center gap-2 text-slate-400">
                        <ChevronDown className="w-4 h-4 text-sky-400" />
                        <span className="font-medium">
                          Response #{idx + 1} (
                          {m.content?.split("\n").length || 1} lines)
                        </span>
                        <span className="text-[10px] text-slate-500 italic">
                          • Click to expand
                        </span>
                      </div>
                      {m.decision && (
                        <span
                          className={`px-2 py-0.5 rounded-full text-[10px] font-bold border ${getBadge(m.decision).bg}`}
                        >
                          {m.decision} ({m.risk}/100)
                        </span>
                      )}
                    </div>
                  ) : (
                    <div className="bg-[#141b2a] border border-slate-800 text-slate-200 text-sm p-3.5 rounded-2xl shadow-sm w-full space-y-2 relative group/bot">
                      <div className="flex items-center justify-between pb-2 border-b border-slate-800/60 text-xs text-slate-400">
                        <div className="flex items-center gap-2">
                          <span className="text-[11px] font-mono font-medium text-slate-400">
                            Response #{idx + 1}
                          </span>
                          {m.latency && (
                            <span className="inline-flex items-center gap-1 text-[10px] font-mono bg-slate-900 px-1.5 py-0.5 rounded border border-slate-800 text-slate-400">
                              <Clock className="w-2.5 h-2.5" /> {m.latency}ms
                            </span>
                          )}
                        </div>
                        <div className="flex items-center gap-1.5">
                          <Tooltip text="Collapse" position="top">
                            <button
                              onClick={() => onToggleCollapse(idx)}
                              className="p-1 hover:text-slate-200 text-slate-500 transition cursor-pointer"
                            >
                              <ChevronUp className="w-3.5 h-3.5" />
                            </button>
                          </Tooltip>
                          <Tooltip text="Copy" position="top">
                            <button
                              onClick={() => onCopy(m.content || "")}
                              className="p-1 hover:text-slate-200 text-slate-500 transition cursor-pointer"
                            >
                              <Copy className="w-3.5 h-3.5" />
                            </button>
                          </Tooltip>
                        </div>
                      </div>

                      <div className="leading-relaxed px-1 text-slate-200">
                        <ReactMarkdown
                          remarkPlugins={[remarkGfm]}
                          components={{
                            p: ({ node, ...props }) => (
                              <p
                                className="my-1.5 leading-relaxed text-slate-200"
                                {...props}
                              />
                            ),
                            ul: ({ node, ...props }) => (
                              <ul
                                className="list-disc list-outside pl-5 my-2 space-y-1 text-slate-300"
                                {...props}
                              />
                            ),
                            ol: ({ node, ...props }) => (
                              <ol
                                className="list-decimal list-outside pl-5 my-2 space-y-1 text-slate-300"
                                {...props}
                              />
                            ),
                            blockquote: ({ node, ...props }) => (
                              <blockquote
                                className="border-l-2 border-sky-500/40 pl-3 my-2 text-slate-400 italic bg-sky-950/10 py-1 rounded-r"
                                {...props}
                              />
                            ),
                            strong: ({ node, ...props }) => (
                              <strong
                                className="font-semibold text-slate-100"
                                {...props}
                              />
                            ),
                            table: ({ node, ...props }) => (
                              <div className="overflow-x-auto my-2.5 rounded-lg border border-slate-800 bg-slate-950/40">
                                <table
                                  className="border-collapse text-xs w-full text-left"
                                  {...props}
                                />
                              </div>
                            ),
                            th: ({ node, ...props }) => (
                              <th
                                className="border-b border-slate-800 bg-slate-900/90 px-3.5 py-2 font-semibold text-slate-200"
                                {...props}
                              />
                            ),
                            td: ({ node, ...props }) => (
                              <td
                                className="border-b border-slate-800/50 px-3.5 py-2 text-slate-300"
                                {...props}
                              />
                            ),
                            code: ({ node, className, children, ...props }) => {
                              const match = /language-(\w+)/.exec(
                                className || "",
                              );
                              const codeVal = String(children).replace(
                                /\n$/,
                                "",
                              );
                              const isBlock =
                                Boolean(match) || codeVal.includes("\n");

                              if (isBlock) {
                                return (
                                  <CodeBlock
                                    language={match ? match[1] : ""}
                                    value={codeVal}
                                  />
                                );
                              }
                              return (
                                <code
                                  className="font-mono text-[0.88em] font-medium text-sky-300/90 bg-white/[0.05] border border-white/[0.08] px-1.5 py-0.5 rounded align-baseline mx-0.5"
                                  {...props}
                                >
                                  {children}
                                </code>
                              );
                            },
                          }}
                        >
                          {m.content || ""}
                        </ReactMarkdown>
                      </div>

                      {m.decision && m.logId && (
                        <div className="border border-slate-800/80 bg-slate-900/60 rounded-xl p-2 text-xs w-full">
                          <div className="flex items-center justify-between select-none">
                            <div className="flex items-center gap-2">
                              <span
                                className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full font-bold border text-[10px] ${getBadge(m.decision).bg}`}
                              >
                                {getBadge(m.decision).icon}
                                {m.decision} (Risk: {m.risk}/100)
                              </span>
                              <span className="text-[11px] text-slate-400 truncate max-w-sm">
                                {m.justification}
                              </span>
                            </div>
                            <span className="text-[10px] text-slate-500 font-mono">
                              Audit #{m.logId}
                            </span>
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )}
            </div>
          ))
        )}

        {loading && (
          <div className="flex items-center gap-2 text-slate-400 text-xs italic">
            <div className="w-2 h-2 rounded-full bg-sky-400 animate-ping" />
            Agent Shield analyzing execution graph...
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>
    </div>
  );
}
