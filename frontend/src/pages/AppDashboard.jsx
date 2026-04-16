import { useEffect, useState } from "react";
import { checkout, getDashboard, getInvestorOverview, getReport, getTradingStatus, manualConfirmTrade, simulateTrade, startTrading, stopTrading, unlockIntegration, updateTradingConfig } from "../lib/api";

function Metric({ title, value }) {
  return (
    <div className="rounded-2xl border border-slate-800 bg-slate-900 p-5">
      <div className="text-sm text-slate-400">{title}</div>
      <div className="mt-2 text-3xl font-bold">{value}</div>
    </div>
  );
}

export default function AppDashboard({ token, authPayload }) {
  const [dashboard, setDashboard] = useState(null);
  const [status, setStatus] = useState(null);
  const [report, setReport] = useState(null);
  const [investor, setInvestor] = useState(null);
  const [unlockText, setUnlockText] = useState("I understand the risk");
  const [manual, setManual] = useState({ symbol: "SOL-USD", size_usd: 50, confirm_text: "EXECUTE LIVE" });
  const [config, setConfig] = useState({
    paper_mode: true,
    strategy_mode: "safe",
    execution_provider: "mock",
    max_position_usd: 100,
    daily_loss_limit_usd: 100,
    auto_trading_enabled: false,
  });

  async function refresh() {
    const [d, s, r, i] = await Promise.all([
      getDashboard(token),
      getTradingStatus(token),
      getReport(token, "weekly"),
      getInvestorOverview(token),
    ]);
    setDashboard(d);
    setStatus(s);
    setReport(r);
    setInvestor(i);
    setConfig({
      paper_mode: s.paper_mode,
      strategy_mode: s.strategy_mode,
      execution_provider: s.execution_provider,
      max_position_usd: s.max_position_usd,
      daily_loss_limit_usd: s.daily_loss_limit_usd,
      auto_trading_enabled: s.auto_trading_enabled,
    });
  }

  useEffect(() => { refresh(); }, []);

  return (
    <div className="mx-auto max-w-7xl px-6 py-8">
      <div className="grid gap-6 md:grid-cols-4">
        {dashboard?.metrics ? (
          <>
            <Metric title="Total Return" value={`${dashboard.metrics.total_return_pct}%`} />
            <Metric title="Win Rate" value={`${dashboard.metrics.win_rate_pct}%`} />
            <Metric title="Max DD" value={`${dashboard.metrics.max_drawdown_pct}%`} />
            <Metric title="MRR" value={`$${dashboard.metrics.monthly_revenue_usd}`} />
          </>
        ) : null}
      </div>

      <div className="mt-8 grid gap-6 lg:grid-cols-3">
        <div className="rounded-2xl border border-slate-800 bg-slate-900 p-6 lg:col-span-2">
          <h2 className="text-xl font-semibold">Integrated Trading Controls</h2>
          <div className="mt-4 grid gap-4 md:grid-cols-2">
            <label className="block">
              <span className="mb-2 block text-sm text-slate-300">Strategy Mode</span>
              <select className="w-full rounded border border-slate-700 bg-slate-950 px-3 py-2" value={config.strategy_mode} onChange={(e) => setConfig({ ...config, strategy_mode: e.target.value })}>
                <option value="safe">safe</option>
                <option value="balanced">balanced</option>
                <option value="aggressive">aggressive</option>
              </select>
            </label>
            <label className="block">
              <span className="mb-2 block text-sm text-slate-300">Execution Provider</span>
              <select className="w-full rounded border border-slate-700 bg-slate-950 px-3 py-2" value={config.execution_provider} onChange={(e) => setConfig({ ...config, execution_provider: e.target.value })}>
                <option value="mock">mock</option>
                <option value="integration">integration</option>
              </select>
            </label>
            <label className="block">
              <span className="mb-2 block text-sm text-slate-300">Max Position (USD)</span>
              <input className="w-full rounded border border-slate-700 bg-slate-950 px-3 py-2" type="number" value={config.max_position_usd} onChange={(e) => setConfig({ ...config, max_position_usd: Number(e.target.value) })} />
            </label>
            <label className="block">
              <span className="mb-2 block text-sm text-slate-300">Daily Loss Limit (USD)</span>
              <input className="w-full rounded border border-slate-700 bg-slate-950 px-3 py-2" type="number" value={config.daily_loss_limit_usd} onChange={(e) => setConfig({ ...config, daily_loss_limit_usd: Number(e.target.value) })} />
            </label>
            <label className="flex items-center gap-3 pt-2">
              <input type="checkbox" checked={config.paper_mode} onChange={(e) => setConfig({ ...config, paper_mode: e.target.checked })} />
              <span className="text-sm text-slate-300">Paper mode</span>
            </label>
            <label className="flex items-center gap-3 pt-2">
              <input type="checkbox" checked={config.auto_trading_enabled} onChange={(e) => setConfig({ ...config, auto_trading_enabled: e.target.checked })} />
              <span className="text-sm text-slate-300">Auto trading enabled</span>
            </label>
          </div>

          <div className="mt-6 flex flex-wrap gap-3">
            <button className="rounded bg-white px-4 py-2 font-medium text-slate-900" onClick={async () => { await updateTradingConfig(token, config); await refresh(); }}>Save config</button>
            <button className="rounded bg-emerald-600 px-4 py-2 font-medium" onClick={async () => { await startTrading(token); await refresh(); }}>Start</button>
            <button className="rounded bg-amber-600 px-4 py-2 font-medium" onClick={async () => { await stopTrading(token); await refresh(); }}>Stop</button>
            <button className="rounded bg-sky-600 px-4 py-2 font-medium" onClick={async () => { await simulateTrade(token); await refresh(); }}>Run integrated sim</button>
          </div>

          <div className="mt-6 rounded-xl bg-slate-950 p-4">
            <div className="font-medium text-white">Integration Unlock</div>
            <div className="mt-3 flex gap-3">
              <input className="flex-1 rounded border border-slate-700 bg-slate-900 px-3 py-2 text-sm" value={unlockText} onChange={(e) => setUnlockText(e.target.value)} />
              <button className="rounded bg-rose-600 px-4 py-2 text-sm font-medium" onClick={async () => { const r = await unlockIntegration(token, unlockText); alert(r.detail || "Integration unlocked"); await refresh(); }}>
                Unlock
              </button>
            </div>
            <div className="mt-2 text-xs text-slate-400">Required phrase: I understand the risk</div>
          </div>

          <div className="mt-6 rounded-xl bg-slate-950 p-4">
            <div className="font-medium text-white">Manual Integration Confirm</div>
            <div className="mt-3 grid gap-3 md:grid-cols-3">
              <input className="rounded border border-slate-700 bg-slate-900 px-3 py-2 text-sm" value={manual.symbol} onChange={(e) => setManual({ ...manual, symbol: e.target.value })} />
              <input className="rounded border border-slate-700 bg-slate-900 px-3 py-2 text-sm" type="number" value={manual.size_usd} onChange={(e) => setManual({ ...manual, size_usd: Number(e.target.value) })} />
              <input className="rounded border border-slate-700 bg-slate-900 px-3 py-2 text-sm" value={manual.confirm_text} onChange={(e) => setManual({ ...manual, confirm_text: e.target.value })} />
            </div>
            <div className="mt-3">
              <button className="rounded bg-red-700 px-4 py-2 text-sm font-medium" onClick={async () => { const r = await manualConfirmTrade(token, manual); alert(r.detail || JSON.stringify(r)); await refresh(); }}>
                Execute manual live confirm
              </button>
            </div>
            <div className="mt-2 text-xs text-slate-400">Required phrase: EXECUTE LIVE</div>
          </div>

          {status ? (
            <div className="mt-6 rounded-xl bg-slate-950 p-4 text-sm text-slate-300">
              <div>Running: {String(status.running)}</div>
              <div>Paper mode: {String(status.paper_mode)}</div>
              <div>Execution provider: {status.execution_provider}</div>
              <div>Integration unlocked: {String(status.integration_unlocked)}</div>
              <div>Trades today: {status.trades_today}</div>
              <div>Daily PnL: ${status.daily_pnl_usd}</div>
              <div>Total PnL: ${status.total_pnl_usd}</div>
              <div>Win Rate: {status.win_rate_pct}%</div>
              <div>Max Drawdown: {status.max_drawdown_pct}%</div>
              <div>Last signal: {status.last_signal || "none"}</div>
            </div>
          ) : null}
        </div>

        <div className="rounded-2xl border border-slate-800 bg-slate-900 p-6">
          <h2 className="text-xl font-semibold">Plan, Reports, Investor View</h2>
          <div className="mt-4 text-sm text-slate-300">Signed in as <span className="font-medium text-white">{authPayload?.user?.email}</span></div>
          <div className="mt-2 text-sm text-slate-300">Current plan: <span className="font-medium text-white">{dashboard?.user?.plan || "free"}</span></div>

          <div className="mt-4 flex gap-3">
            <button className="rounded bg-indigo-600 px-4 py-2 text-sm font-medium" onClick={async () => { const r = await checkout(token, "pro"); alert(r.message || JSON.stringify(r)); await refresh(); }}>Upgrade to Pro</button>
            <button className="rounded bg-fuchsia-600 px-4 py-2 text-sm font-medium" onClick={async () => { const r = await checkout(token, "fund"); alert(r.message || JSON.stringify(r)); await refresh(); }}>Upgrade to Fund</button>
          </div>

          {report ? (
            <div className="mt-6 rounded-xl bg-slate-950 p-4 text-sm text-slate-300">
              <div className="font-medium text-white">{report.period.toUpperCase()} Report</div>
              <div className="mt-2">{report.summary}</div>
              <div className="mt-3">Attribution:</div>
              <ul className="mt-2 space-y-1">
                {report.attribution.map((item) => (
                  <li key={item.name}>{item.name}: ${item.pnl_usd} ({item.weight_pct}%)</li>
                ))}
              </ul>
            </div>
          ) : null}

          {investor ? (
            <div className="mt-6 rounded-xl bg-slate-950 p-4 text-sm text-slate-300">
              <div className="font-medium text-white">{investor.headline}</div>
              <div className="mt-2">{investor.summary}</div>
              <div className="mt-3">Ecosystem:</div>
              <ul className="mt-2 space-y-1">
                {investor.ecosystem.map((item) => (
                  <li key={item.name}>{item.name} — {item.species} ({item.weight_pct}%)</li>
                ))}
              </ul>
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}
