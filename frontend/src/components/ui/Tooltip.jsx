export default function Tooltip({
  text,
  children,
  position = "top",
  align = "center",
}) {
  if (!text) return children;

  const posClasses = {
    top: "bottom-full mb-2",
    bottom: "top-full mt-2",
    left: "right-full mr-2 top-1/2 -translate-y-1/2",
    right: "left-full ml-2 top-1/2 -translate-y-1/2",
  };

  const alignClasses = {
    center: "left-1/2 -translate-x-1/2",
    left: "left-0 translate-x-0",
    right: "right-0 translate-x-0",
  };

  const isVertical = position === "top" || position === "bottom";

  return (
    <div className="relative group/tip inline-flex items-center">
      {children}
      <div
        className={`absolute hidden group-hover/tip:flex z-50 px-2.5 py-1 text-[11px] font-medium text-slate-300 bg-slate-800/95 border border-slate-700/80 rounded-lg shadow-2xl backdrop-blur-md whitespace-nowrap pointer-events-none transition-opacity duration-150 ${posClasses[position]} ${isVertical ? alignClasses[align] : ""}`}
      >
        {text}
      </div>
    </div>
  );
}
