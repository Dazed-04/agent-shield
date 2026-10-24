import { useState, useEffect, useRef } from "react";
import { ChevronDown, Check } from "lucide-react";
import Tooltip from "./Tooltip";

export default function CustomDropdown({
  icon: Icon,
  value,
  options,
  onChange,
  tooltipText,
}) {
  const [isOpen, setIsOpen] = useState(false);
  const dropdownRef = useRef(null);

  useEffect(() => {
    const handleClickOutside = (e) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target)) {
        setIsOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const selectedOption = options.find((o) => o.value === value) || options[0];

  return (
    <div className="relative inline-flex items-center" ref={dropdownRef}>
      <Tooltip text={isOpen ? "" : tooltipText} position="bottom">
        <button
          onClick={() => setIsOpen(!isOpen)}
          className={`flex items-center gap-1.5 px-2.5 py-1 rounded-lg border text-xs font-medium transition cursor-pointer ${
            isOpen
              ? "bg-slate-800 border-sky-500/50 text-white"
              : "bg-slate-900 border-slate-800 text-slate-300 hover:text-white hover:border-slate-700"
          }`}
        >
          {Icon && <Icon className="w-3.5 h-3.5 text-sky-400 flex-shrink-0" />}
          <span className="truncate max-w-[130px] text-[11px]">
            {selectedOption?.label || value}
          </span>
          <ChevronDown
            className={`w-3 h-3 text-slate-400 transition-transform duration-150 ${isOpen ? "rotate-180" : ""}`}
          />
        </button>
      </Tooltip>

      {isOpen && (
        <div className="absolute top-full mt-1.5 right-0 z-50 w-48 bg-[#101625] border border-slate-800 rounded-xl shadow-2xl p-1 animate-in fade-in zoom-in-95 duration-100">
          {options.map((opt) => (
            <div
              key={opt.value}
              onClick={() => {
                onChange(opt.value);
                setIsOpen(false);
              }}
              className={`px-2.5 py-1.5 rounded-lg text-xs cursor-pointer transition flex items-center justify-between ${
                opt.value === value
                  ? "bg-sky-500/15 text-sky-300 font-semibold"
                  : "text-slate-300 hover:bg-slate-800/60 hover:text-white"
              }`}
            >
              <span className="truncate">{opt.label}</span>
              {opt.value === value && (
                <Check className="w-3 h-3 text-sky-400 flex-shrink-0" />
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
