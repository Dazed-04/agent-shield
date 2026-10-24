export default function ModernLogo() {
  return (
    <div className="relative w-7 h-7 flex items-center justify-center flex-shrink-0">
      <div className="absolute inset-0 bg-sky-500/20 blur-md rounded-full" />
      <svg
        className="w-7 h-7 text-sky-400 relative z-10"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <polygon points="12 2 22 8.5 22 15.5 12 22 2 15.5 2 8.5 12 2" />
        <line x1="12" y1="22" x2="12" y2="15.5" />
        <polyline points="22 8.5 12 15.5 2 8.5" />
        <polyline points="2 15.5 12 8.5 22 15.5" />
        <line x1="12" y1="2" x2="12" y2="8.5" />
        <circle cx="12" cy="12" r="1.5" fill="#38bdf8" />
      </svg>
    </div>
  );
}
