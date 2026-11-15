import { useState } from "react";
import { KeyRound } from "lucide-react";

/** Shown when the gateway runs in production mode and no valid API key is stored. */
export default function ApiKeyModal({ open, error, onSubmit }) {
  const [value, setValue] = useState("");
  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/70 backdrop-blur-sm">
      <form
        className="w-full max-w-md rounded-xl border border-slate-700 bg-[#0f1524] p-6 shadow-2xl"
        onSubmit={(e) => {
          e.preventDefault();
          if (value.trim()) onSubmit(value.trim());
        }}
      >
        <div className="mb-3 flex items-center gap-2 text-slate-100">
          <KeyRound className="h-5 w-5 text-emerald-400" />
          <h2 className="text-lg font-semibold">Authentication required</h2>
        </div>
        <p className="mb-4 text-sm text-slate-400">
          This gateway is running in production mode. Enter your API key to
          continue. Your role and permissions are bound to the key on the
          server.
        </p>
        <input
          type="password"
          autoFocus
          autoComplete="off"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder="API key"
          className="mb-3 w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100 outline-none focus:border-emerald-500"
        />
        {error && <p className="mb-3 text-sm text-rose-400">{error}</p>}
        <button
          type="submit"
          className="w-full rounded-lg bg-emerald-600 px-3 py-2 text-sm font-medium text-white hover:bg-emerald-500"
        >
          Continue
        </button>
      </form>
    </div>
  );
}
