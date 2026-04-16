export default function LandingPage({ onShowAuth }) {
  return (
    <div className="min-h-screen bg-slate-950 text-white">
      <div className="mx-auto max-w-6xl px-6 py-20">
        <div className="max-w-3xl">
          <div className="mb-4 inline-flex rounded-full border border-slate-700 px-3 py-1 text-sm text-slate-300">
            AI Fund OS
          </div>
          <h1 className="text-5xl font-bold leading-tight">
            AI Fund, Execution AI, RL, Alpha Ecosystem, and Sim2Real in one product.
          </h1>
          <p className="mt-6 text-lg text-slate-300">
            Fully connected product scaffold with dashboard, reports, trading controls, investor view, and background paper trading.
          </p>
          <div className="mt-8 flex gap-4">
            <button onClick={onShowAuth} className="rounded bg-white px-5 py-3 font-medium text-slate-900">
              Start free
            </button>
            <a href="#pricing" className="rounded border border-slate-700 px-5 py-3 font-medium text-white">
              View pricing
            </a>
          </div>
        </div>

        <div className="mt-20 grid gap-6 md:grid-cols-3">
          {[
            ["AI Fund", "Fund brain, regime, allocator-style routing, and module orchestration."],
            ["Execution AI", "Slippage prediction, fill probability, and execution provider interface."],
            ["Investor Layer", "Weekly and monthly reports with investor overview and attribution."]
          ].map(([title, body]) => (
            <div key={title} className="rounded-2xl border border-slate-800 bg-slate-900 p-6">
              <h3 className="text-xl font-semibold">{title}</h3>
              <p className="mt-3 text-slate-300">{body}</p>
            </div>
          ))}
        </div>

        <div id="pricing" className="mt-20 grid gap-6 md:grid-cols-3">
          {[
            ["Free", "$0", ["Dashboard", "Paper mode", "Safe controls"]],
            ["Pro", "$29/mo", ["Reports", "Config", "Monitoring"]],
            ["Fund", "$199/mo", ["Investor view", "Allocator-ready", "Advanced reporting"]],
          ].map(([name, price, features]) => (
            <div key={name} className="rounded-2xl border border-slate-800 bg-slate-900 p-6">
              <div className="text-lg font-semibold">{name}</div>
              <div className="mt-3 text-3xl font-bold">{price}</div>
              <ul className="mt-4 space-y-2 text-slate-300">
                {features.map((f) => <li key={f}>• {f}</li>)}
              </ul>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}\n