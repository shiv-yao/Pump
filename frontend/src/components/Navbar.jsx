export default function Navbar({ token, onLogout }) {
  return (
    <div className="flex items-center justify-between border-b border-slate-800 px-6 py-4">
      <div>
        <div className="text-xl font-semibold">AI Fund OS</div>
        <div className="text-sm text-slate-400">Integrated product edition</div>
      </div>
      <div className="flex items-center gap-3">
        {token ? (
          <>
            <div className="rounded bg-slate-800 px-3 py-2 text-xs text-slate-300">Session active</div>
            <button className="rounded bg-slate-700 px-4 py-2 text-sm hover:bg-slate-600" onClick={onLogout}>
              Logout
            </button>
          </>
        ) : null}
      </div>
    </div>
  );
}\n