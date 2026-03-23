from __future__ import annotations

import os
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR / "src"))

from adaptive_trading.live.dashboard import build_dashboard_payload
from adaptive_trading.live.scheduler import WorkerScheduler
from adaptive_trading.live.worker import TradingServiceWorker

worker = TradingServiceWorker(BASE_DIR)
scheduler = WorkerScheduler(worker)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if worker.settings.auto_start_scheduler:
        scheduler.start()
        if worker.settings.run_jobs_on_startup:
            worker.optimization_cycle()
            worker.trading_cycle()
    yield
    scheduler.shutdown()


app = FastAPI(title="Adaptive Trading System v6 Railway OKX Fixed Universe Dashboard", version="6.0.0", lifespan=lifespan)


def dashboard_html() -> str:
    return """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Adaptive Trading Command Center</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
  <style>
    :root {
      --bg:#07111f;
      --bg2:#0b1627;
      --panel:rgba(10, 19, 35, 0.78);
      --panel-2:rgba(12, 24, 44, 0.92);
      --line:rgba(104, 138, 179, 0.22);
      --text:#ecf5ff;
      --muted:#91a7c3;
      --cyan:#41e2ff;
      --green:#5cff8d;
      --red:#ff5f7d;
      --amber:#ffd166;
      --purple:#9b7dff;
      --shadow:0 20px 60px rgba(0,0,0,0.35);
      --radius:22px;
    }
    *{box-sizing:border-box}
    body{
      margin:0;
      color:var(--text);
      font-family:Inter,ui-sans-serif,system-ui,-apple-system,Segoe UI,Roboto,sans-serif;
      background:
        radial-gradient(circle at top left, rgba(65,226,255,0.14), transparent 20%),
        radial-gradient(circle at top right, rgba(155,125,255,0.16), transparent 25%),
        radial-gradient(circle at bottom center, rgba(92,255,141,0.08), transparent 30%),
        linear-gradient(180deg, #06101d 0%, #07111f 35%, #0a1322 100%);
      min-height:100vh;
    }
    .grid-overlay::before{
      content:"";
      position:fixed;
      inset:0;
      pointer-events:none;
      background-image: linear-gradient(rgba(255,255,255,0.03) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.03) 1px, transparent 1px);
      background-size: 36px 36px;
      mask-image: radial-gradient(circle at center, rgba(255,255,255,0.85), transparent 92%);
      opacity:.32;
    }
    .wrap{max-width:1600px;margin:0 auto;padding:24px 20px 40px;position:relative;z-index:1}
    .hero{
      display:flex;justify-content:space-between;gap:16px;align-items:flex-start;flex-wrap:wrap;
      padding:24px 28px;background:linear-gradient(135deg, rgba(12,23,43,.86), rgba(8,17,30,.72));
      border:1px solid rgba(95,125,170,.18);box-shadow:var(--shadow);border-radius:28px;backdrop-filter:blur(16px)
    }
    .title{font-size:34px;font-weight:800;letter-spacing:.02em;margin:0}
    .subtitle{margin-top:8px;color:var(--muted);max-width:820px;line-height:1.5}
    .hero-actions{display:flex;gap:12px;flex-wrap:wrap;align-items:center}
    .btn{
      border:1px solid rgba(122,155,201,.22);background:rgba(12,27,49,.92);color:var(--text);
      padding:12px 16px;border-radius:16px;font-weight:700;cursor:pointer;transition:.2s transform,.2s box-shadow,.2s border-color
    }
    .btn:hover{transform:translateY(-1px);box-shadow:0 12px 30px rgba(0,0,0,.22);border-color:rgba(65,226,255,.38)}
    .btn.primary{background:linear-gradient(135deg, rgba(65,226,255,.18), rgba(155,125,255,.18));border-color:rgba(65,226,255,.4)}
    .toggle{display:flex;align-items:center;gap:10px;color:var(--muted);font-weight:600;padding:10px 14px;border-radius:16px;background:rgba(9,17,31,.72);border:1px solid var(--line)}
    .cards{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:14px;margin-top:18px}
    .card,.panel{
      background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);box-shadow:var(--shadow);backdrop-filter:blur(14px)
    }
    .card{padding:18px 18px 16px;position:relative;overflow:hidden;min-height:128px}
    .card::after{content:"";position:absolute;right:-20px;top:-20px;width:110px;height:110px;border-radius:50%;background:radial-gradient(circle, rgba(65,226,255,.16), transparent 70%)}
    .eyebrow{color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.14em;font-weight:700}
    .value{font-size:30px;font-weight:800;margin-top:10px}
    .delta{margin-top:8px;font-size:13px;color:var(--muted);display:flex;gap:8px;align-items:center;flex-wrap:wrap}
    .up{color:var(--green)} .down{color:var(--red)} .warn{color:var(--amber)} .accent{color:var(--cyan)}
    .layout{display:grid;grid-template-columns:2fr 1fr;gap:16px;margin-top:16px}
    .stack{display:grid;gap:16px}
    .panel{padding:18px}
    .panel h3{margin:0 0 14px 0;font-size:17px;letter-spacing:.02em}
    .panel-head{display:flex;justify-content:space-between;gap:10px;align-items:center;flex-wrap:wrap;margin-bottom:12px}
    .mini-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}
    .data-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px}
    .stat-list{display:grid;gap:12px}
    .stat-row{display:flex;justify-content:space-between;gap:16px;padding:10px 12px;border:1px solid rgba(127,159,205,.12);border-radius:14px;background:rgba(255,255,255,.02)}
    .stat-row span:last-child{font-weight:800}
    table{width:100%;border-collapse:collapse;font-size:13px}
    th,td{padding:11px 10px;border-bottom:1px solid rgba(129,160,201,.12);text-align:left;vertical-align:top}
    th{color:#9fb7d5;font-size:11px;text-transform:uppercase;letter-spacing:.12em}
    tbody tr:hover{background:rgba(255,255,255,.025)}
    .table-wrap{max-height:380px;overflow:auto;border-radius:16px;border:1px solid rgba(133,163,205,.12)}
    .pill{display:inline-flex;align-items:center;gap:6px;padding:7px 10px;border-radius:999px;font-size:12px;font-weight:800;border:1px solid rgba(132,161,209,.16);background:rgba(255,255,255,.03)}
    .pill.green{color:var(--green);border-color:rgba(92,255,141,.24);background:rgba(92,255,141,.08)}
    .pill.red{color:var(--red);border-color:rgba(255,95,125,.24);background:rgba(255,95,125,.08)}
    .pill.cyan{color:var(--cyan);border-color:rgba(65,226,255,.24);background:rgba(65,226,255,.08)}
    .pill.amber{color:var(--amber);border-color:rgba(255,209,102,.24);background:rgba(255,209,102,.08)}
    .chip-row{display:flex;gap:10px;flex-wrap:wrap}
    .footnote{margin-top:10px;color:var(--muted);font-size:12px}
    canvas{width:100% !important;height:320px !important}
    .small-chart canvas{height:260px !important}
    .mono{font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace}
    .empty{color:var(--muted);padding:22px 6px}
    @media (max-width: 1280px){
      .cards{grid-template-columns:repeat(3,minmax(0,1fr))}
      .layout{grid-template-columns:1fr}
      .data-grid{grid-template-columns:1fr}
    }
    @media (max-width: 760px){
      .cards{grid-template-columns:repeat(2,minmax(0,1fr))}
      .mini-grid{grid-template-columns:1fr}
      .title{font-size:28px}
    }
  </style>
</head>
<body class="grid-overlay">
  <div class="wrap">
    <section class="hero">
      <div>
        <div class="eyebrow">Adaptive Trading System v6</div>
        <h1 class="title">OKX Fixed-Pairs Futures Command Center</h1>
        <div class="subtitle">Fixed curated OKX futures universe monitoring for long and short trading, rolling optimization, pair-level ranking, realized and unrealized PnL, and persistent Railway state analytics.</div>
      </div>
      <div class="hero-actions">
        <button class="btn primary" onclick="runJob('trading')">Run trading cycle</button>
        <button class="btn" onclick="runJob('optimization')">Run optimization</button>
        <label class="toggle"><input id="autoRefresh" type="checkbox" checked /> Auto refresh 15s</label>
      </div>
    </section>

    <section class="cards" id="cards"></section>

    <section class="layout">
      <div class="stack">
        <div class="panel">
          <div class="panel-head">
            <h3>Equity trajectory</h3>
            <div class="chip-row" id="systemChips"></div>
          </div>
          <canvas id="equityChart"></canvas>
        </div>

        <div class="mini-grid">
          <div class="panel small-chart">
            <div class="panel-head"><h3>Daily PnL</h3><div class="pill amber">All time</div></div>
            <canvas id="dailyChart"></canvas>
          </div>
          <div class="panel small-chart">
            <div class="panel-head"><h3>Monthly PnL</h3><div class="pill cyan">Regime summary</div></div>
            <canvas id="monthlyChart"></canvas>
          </div>
        </div>

        <div class="mini-grid">
          <div class="panel small-chart">
            <div class="panel-head"><h3>PnL by symbol</h3><div class="pill cyan">Realized</div></div>
            <canvas id="symbolChart"></canvas>
          </div>
          <div class="panel small-chart">
            <div class="panel-head"><h3>Exit reasons</h3><div class="pill amber">Trade outcomes</div></div>
            <canvas id="reasonChart"></canvas>
          </div>
        </div>

        <div class="panel">
          <div class="panel-head"><h3>Recent trades</h3><div class="pill cyan" id="tradeCountPill">0 trades</div></div>
          <div class="table-wrap"><table><thead><tr><th>Exit</th><th>Symbol</th><th>Side</th><th>PnL</th><th>Return %</th><th>Hold h</th><th>Reason</th></tr></thead><tbody id="recentTradesBody"></tbody></table></div>
        </div>

        <div class="panel">
          <div class="panel-head"><h3>Optimization history</h3><div class="pill amber" id="optCountPill">0 runs</div></div>
          <div class="table-wrap"><table><thead><tr><th>Run</th><th>Objective</th><th>Return %</th><th>Max DD %</th><th>Sharpe</th><th>Promoted</th></tr></thead><tbody id="optimizationBody"></tbody></table></div>
        </div>
      </div>

      <div class="stack">
        <div class="panel">
          <div class="panel-head"><h3>System snapshot</h3><div class="pill cyan">Live state</div></div>
          <div class="data-grid">
            <div class="stat-list" id="systemStats"></div>
            <div class="stat-list" id="riskStats"></div>
            <div class="stat-list" id="tradeStats"></div>
          </div>
        </div>

        <div class="panel">
          <div class="panel-head"><h3>Open positions</h3><div class="pill green" id="openPosPill">0 open</div></div>
          <div class="table-wrap"><table><thead><tr><th>Symbol</th><th>Side</th><th>Mark</th><th>Entry</th><th>Unrealized</th><th>Exposure</th><th>Bars</th></tr></thead><tbody id="openPositionsBody"></tbody></table></div>
        </div>

        <div class="panel">
          <div class="panel-head"><h3>Latest signals</h3><div class="pill cyan">Top ranked</div></div>
          <div class="table-wrap"><table><thead><tr><th>Timestamp</th><th>Symbol</th><th>Signal</th><th>Score</th><th>Confidence</th><th>Size</th></tr></thead><tbody id="signalsBody"></tbody></table></div>
        </div>

        <div class="panel">
          <div class="panel-head"><h3>OKX futures universe</h3><div class="pill cyan" id="universePill">0 symbols</div></div>
          <div class="table-wrap"><table><thead><tr><th>#</th><th>Symbol</th><th>Signal</th><th>Score</th><th>24h Quote Vol</th><th>Spread bps</th><th>24h %</th></tr></thead><tbody id="universeBody"></tbody></table></div>
        </div>

        <div class="panel">
          <div class="panel-head"><h3>Recent actions</h3><div class="pill amber">Execution log</div></div>
          <div class="table-wrap"><table><thead><tr><th>Time</th><th>Symbol</th><th>Action</th><th>Reason</th><th>PnL</th></tr></thead><tbody id="actionsBody"></tbody></table></div>
        </div>

        <div class="panel">
          <div class="panel-head"><h3>Champion config</h3><div class="pill cyan">Current promoted set</div></div>
          <div class="table-wrap"><table><thead><tr><th>Key</th><th>Value</th></tr></thead><tbody id="championBody"></tbody></table></div>
          <div class="footnote">The dashboard reads persisted state from Railway disk. Historical continuity is strongest in paper mode because realized PnL is stored locally with every trade.</div>
        </div>
      </div>
    </section>
  </div>

<script>
let charts = {};
let refreshHandle = null;

function fmtNum(v, digits=2){
  const n = Number(v ?? 0);
  if(!Number.isFinite(n)) return '-';
  return n.toLocaleString(undefined,{maximumFractionDigits:digits, minimumFractionDigits:digits});
}
function fmtMoney(v){
  const n = Number(v ?? 0);
  const sign = n > 0 ? '+' : '';
  return sign + fmtNum(n,2);
}
function clsBySign(v){
  return Number(v ?? 0) >= 0 ? 'up' : 'down';
}
function pillBySign(v){
  return Number(v ?? 0) >= 0 ? 'pill green' : 'pill red';
}
function safeRows(arr){ return Array.isArray(arr) ? arr : []; }
function truncate(str, n=24){ if(!str) return '-'; return String(str).length > n ? String(str).slice(0,n-1)+'…' : String(str); }

async function fetchJSON(url, opts={}){
  const res = await fetch(url, opts);
  if(!res.ok) throw new Error('HTTP ' + res.status);
  return await res.json();
}

async function loadDashboard(){
  try{
    const data = await fetchJSON('/api/dashboard');
    renderCards(data);
    renderSnapshot(data);
    renderTables(data);
    renderChampion(data);
    renderCharts(data);
  }catch(err){
    console.error(err);
  }
}

function renderCards(data){
  const s = data.summary || {};
  const cards = [
    ['Current Equity', fmtNum(s.current_equity), `${fmtMoney(s.total_pnl)} total pnl`, clsBySign(s.total_pnl)],
    ['Total Return %', fmtNum(s.total_return_pct,2)+'%', `${fmtMoney(s.realized_pnl)} realized`, clsBySign(s.total_return_pct)],
    ['Unrealized PnL', fmtMoney(s.unrealized_pnl), `${s.open_positions || 0} open positions`, clsBySign(s.unrealized_pnl)],
    ['Win Rate', fmtNum(s.win_rate_pct,2)+'%', `${s.closed_trades || 0} closed trades`, 'accent'],
    ['Profit Factor', fmtNum(s.profit_factor,2), `Best ${fmtMoney(s.best_trade)} / Worst ${fmtMoney(s.worst_trade)}`, 'accent'],
    ['Max Drawdown %', fmtNum(s.max_drawdown_pct,2)+'%', `Current ${fmtNum(s.current_drawdown_pct,2)}%`, Number(s.current_drawdown_pct) < 0 ? 'down' : 'warn'],
    ['Universe', `${s.universe_loaded || 0}/${s.universe_selected || 0}`, 'loaded / selected symbols', 'accent'],
    ['Trading Cycles', fmtNum(s.trading_cycles,0), `${s.optimization_runs || 0} optimization runs`, 'accent'],
    ['Cash Balance', fmtNum(s.cash), `${fmtMoney(s.avg_trade_pnl)} avg trade pnl`, 'accent'],
    ['Average Trade %', fmtNum(s.avg_trade_return_pct,3)+'%', `${fmtNum(s.avg_holding_hours,1)} h avg hold`, 'accent'],
    ['Directional Split', `${s.long_trades || 0}/${s.short_trades || 0}`, 'long / short trades', 'accent'],
    ['Last Trade Cycle', truncate(s.last_cycle_at,22), 'latest worker heartbeat', 'accent'],
    ['Last Optimization', truncate(s.last_optimization_at,22), 'last champion evaluation', 'accent'],
  ];
  const html = cards.map(([title, value, delta, cls]) => `
    <div class="card">
      <div class="eyebrow">${title}</div>
      <div class="value ${cls}">${value}</div>
      <div class="delta"><span class="${cls}">●</span><span>${delta}</span></div>
    </div>`).join('');
  document.getElementById('cards').innerHTML = html;
}

function renderSnapshot(data){
  const s = data.summary || {};
  const last = data.last_cycle || {};
  const champion = data.champion || {};
  const universe = data.universe || {};
  const systemStats = [
    ['Mode', (last.mode || 'paper').toUpperCase()],
    ['Scheduler', data.scheduler?.started ? 'RUNNING' : 'STOPPED'],
    ['Market source', data.health?.market_data_source || '-'],
    ['Universe selected', universe.selected_count ?? 0],
    ['Universe loaded', universe.loaded_count ?? 0],
    ['Signals in last cycle', safeRows(last.signals).length],
    ['Actions in last cycle', safeRows(last.actions).length],
  ];
  const riskStats = [
    ['Open positions', s.open_positions || 0],
    ['Max drawdown %', fmtNum(s.max_drawdown_pct,2)+'%'],
    ['Current drawdown %', fmtNum(s.current_drawdown_pct,2)+'%'],
    ['Cash', fmtNum(s.cash)],
    ['Unrealized', fmtMoney(s.unrealized_pnl)],
  ];
  const tradeStats = [
    ['Closed trades', s.closed_trades || 0],
    ['Win rate', fmtNum(s.win_rate_pct,2)+'%'],
    ['Profit factor', fmtNum(s.profit_factor,2)],
    ['Avg hold', fmtNum(s.avg_holding_hours,1)+' h'],
    ['Champion promoted', champion.promoted ? 'YES' : 'NO'],
  ];
  document.getElementById('systemStats').innerHTML = systemStats.map(([k,v])=>`<div class="stat-row"><span>${k}</span><span>${v}</span></div>`).join('');
  document.getElementById('riskStats').innerHTML = riskStats.map(([k,v])=>`<div class="stat-row"><span>${k}</span><span>${v}</span></div>`).join('');
  document.getElementById('tradeStats').innerHTML = tradeStats.map(([k,v])=>`<div class="stat-row"><span>${k}</span><span>${v}</span></div>`).join('');
  document.getElementById('systemChips').innerHTML = `
    <span class="pill cyan">${(last.mode || 'paper').toUpperCase()}</span>
    <span class="pill ${data.scheduler?.started ? 'green' : 'red'}">Scheduler ${data.scheduler?.started ? 'running' : 'stopped'}</span>
    <span class="pill amber">${data.health?.market_data_source || '-'} feed</span>
    <span class="pill cyan">Universe ${(universe.loaded_count ?? 0)}/${(universe.selected_count ?? 0)}</span>
    <span class="pill cyan">${data.health?.time_utc ? 'UTC ' + truncate(data.health.time_utc, 22) : 'UTC'}</span>`;
}

function renderTables(data){
  const trades = safeRows(data.recent_trades);
  const positions = safeRows(data.open_positions);
  const signals = safeRows(data.recent_signals);
  const actions = safeRows(data.recent_actions);
  const opts = safeRows(data.optimization_history);
  const universe = data.universe || {};
  const universeRows = safeRows(universe.rankings).length ? safeRows(universe.rankings) : safeRows(universe.members);

  document.getElementById('tradeCountPill').textContent = `${trades.length} rows`;
  document.getElementById('openPosPill').textContent = `${positions.length} open`;
  document.getElementById('optCountPill').textContent = `${opts.length} runs`;
  document.getElementById('universePill').textContent = `${universe.loaded_count ?? 0}/${universe.selected_count ?? universeRows.length ?? 0}`;

  document.getElementById('recentTradesBody').innerHTML = trades.length ? trades.map(r => `
    <tr>
      <td class="mono">${truncate(r.exit_time, 24)}</td>
      <td>${r.symbol}</td>
      <td><span class="${r.side === 'LONG' ? 'pill green' : 'pill red'}">${r.side}</span></td>
      <td class="${clsBySign(r.pnl)}">${fmtMoney(r.pnl)}</td>
      <td class="${clsBySign(r.return_pct)}">${fmtNum(r.return_pct,3)}%</td>
      <td>${fmtNum(r.holding_hours,1)}</td>
      <td>${r.reason || '-'}</td>
    </tr>`).join('') : `<tr><td colspan="7" class="empty">No closed trades yet.</td></tr>`;

  document.getElementById('openPositionsBody').innerHTML = positions.length ? positions.map(r => `
    <tr>
      <td>${r.symbol}</td>
      <td><span class="${r.side === 'LONG' ? 'pill green' : 'pill red'}">${r.side}</span></td>
      <td>${fmtNum(r.mark_price,4)}</td>
      <td>${fmtNum(r.entry_price,4)}</td>
      <td class="${clsBySign(r.unrealized_pnl)}">${fmtMoney(r.unrealized_pnl)}</td>
      <td>${fmtNum(r.exposure,2)}</td>
      <td>${r.bars_held || 0}</td>
    </tr>`).join('') : `<tr><td colspan="7" class="empty">No open positions.</td></tr>`;

  document.getElementById('signalsBody').innerHTML = signals.length ? signals.map(r => `
    <tr>
      <td class="mono">${truncate(r.timestamp, 24)}</td>
      <td>${r.symbol}</td>
      <td><span class="${r.signal === 'LONG' ? 'pill green' : 'pill red'}">${r.signal}</span></td>
      <td class="${clsBySign(r.score)}">${fmtNum(r.score,4)}</td>
      <td>${fmtNum(r.confidence,4)}</td>
      <td>${fmtNum((r.notional_fraction || 0) * 100,2)}%</td>
    </tr>`).join('') : `<tr><td colspan="6" class="empty">No signals available yet.</td></tr>`;

  document.getElementById('actionsBody').innerHTML = actions.length ? actions.map(r => `
    <tr>
      <td class="mono">${truncate(r.time, 24)}</td>
      <td>${r.symbol || '-'}</td>
      <td>${r.action || '-'}</td>
      <td>${r.reason || '-'}</td>
      <td class="${clsBySign(r.pnl)}">${r.pnl === null || r.pnl === undefined ? '-' : fmtMoney(r.pnl)}</td>
    </tr>`).join('') : `<tr><td colspan="5" class="empty">No recent actions logged.</td></tr>`;

  document.getElementById('optimizationBody').innerHTML = opts.length ? opts.map(r => `
    <tr>
      <td class="mono">${truncate(r.ran_at, 24)}</td>
      <td>${fmtNum(r.objective,4)}</td>
      <td class="${clsBySign(r.return_pct)}">${fmtNum(r.return_pct,2)}%</td>
      <td>${fmtNum(r.max_drawdown_pct,2)}%</td>
      <td>${fmtNum(r.sharpe,3)}</td>
      <td>${r.promoted ? '<span class="pill green">YES</span>' : '<span class="pill red">NO</span>'}</td>
    </tr>`).join('') : `<tr><td colspan="6" class="empty">No optimization history yet.</td></tr>`;

  document.getElementById('universeBody').innerHTML = universeRows.length ? universeRows.slice(0,100).map(r => {
    const sig = Number(r.signal ?? r.desired_signal ?? 0);
    const sigTxt = sig > 0 ? 'LONG' : (sig < 0 ? 'SHORT' : 'FLAT');
    const sigCls = sig > 0 ? 'pill green' : (sig < 0 ? 'pill red' : 'pill amber');
    const vol = r.volCcy24h ?? r.volCcy24h === 0 ? fmtNum(r.volCcy24h,0) : '-';
    return `
      <tr>
        <td>${r.rank ?? r.volume_rank ?? '-'}</td>
        <td>${r.symbol || r.instId || '-'}</td>
        <td><span class="${sigCls}">${sigTxt}</span></td>
        <td class="${clsBySign(r.ensemble_score ?? 0)}">${r.ensemble_score === undefined ? '-' : fmtNum(r.ensemble_score,4)}</td>
        <td>${vol}</td>
        <td>${r.spread_bps === undefined ? '-' : fmtNum(r.spread_bps,2)}</td>
        <td class="${clsBySign(r.change24h_pct ?? 0)}">${r.change24h_pct === undefined ? '-' : fmtNum(r.change24h_pct,2) + '%'}</td>
      </tr>`;
  }).join('') : `<tr><td colspan="7" class="empty">Universe snapshot not populated yet.</td></tr>`;
}

function renderChampion(data){
  const champ = data.champion || {};
  const rows = [];
  if(champ.objective !== undefined) rows.push(['Objective', fmtNum(champ.objective,4)]);
  if(champ.promoted !== undefined) rows.push(['Promoted', champ.promoted ? 'YES' : 'NO']);
  if(champ.generated_at) rows.push(['Generated at', champ.generated_at]);
  if(champ.metrics){
    for(const [k,v] of Object.entries(champ.metrics)){
      rows.push([`Metric · ${k}`, typeof v === 'number' ? fmtNum(v,4) : String(v)]);
    }
  }
  if(champ.config){
    const cfg = champ.config;
    const ensemble = cfg.ensemble || {};
    const portfolio = cfg.portfolio || {};
    rows.push(['Config · ensemble.entry_threshold', fmtNum(ensemble.entry_threshold,4)]);
    rows.push(['Config · portfolio.max_positions', portfolio.max_positions ?? '-']);
    rows.push(['Config · portfolio.max_symbol_exposure', fmtNum(portfolio.max_symbol_exposure,4)]);
    rows.push(['Config · portfolio.trailing_atr_mult', fmtNum(portfolio.trailing_atr_mult,4)]);
  }
  document.getElementById('championBody').innerHTML = rows.length ? rows.map(([k,v]) => `<tr><td>${k}</td><td class="mono">${v}</td></tr>`).join('') : `<tr><td colspan="2" class="empty">No champion config stored yet.</td></tr>`;
}

function makeChart(id, type, labels, datasets, extra={}){
  if(charts[id]) charts[id].destroy();
  const ctx = document.getElementById(id).getContext('2d');
  charts[id] = new Chart(ctx, {
    type,
    data:{labels,datasets},
    options:{
      responsive:true,
      maintainAspectRatio:false,
      interaction:{intersect:false,mode:'index'},
      plugins:{legend:{labels:{color:'#dbe9f8'}}},
      scales:{
        x:{ticks:{color:'#8ea5c1'},grid:{color:'rgba(141,169,205,.08)'}},
        y:{ticks:{color:'#8ea5c1'},grid:{color:'rgba(141,169,205,.08)'}}
      },
      ...extra,
    }
  });
}

function renderCharts(data){
  const eq = safeRows(data.equity_curve);
  makeChart('equityChart', 'line', eq.map(x => x.time?.slice(0,16).replace('T',' ')), [{
    label:'Equity', data:eq.map(x => x.equity), borderColor:'#41e2ff', backgroundColor:'rgba(65,226,255,.12)', tension:.25, fill:true, pointRadius:0, borderWidth:2
  }]);

  const daily = safeRows(data.daily_pnl);
  makeChart('dailyChart', 'bar', daily.map(x => x.date), [{
    label:'Daily PnL', data:daily.map(x => x.pnl), backgroundColor: daily.map(x => Number(x.pnl) >= 0 ? 'rgba(92,255,141,.65)' : 'rgba(255,95,125,.65)'), borderRadius:8
  }], {plugins:{legend:{display:false}}});

  const monthly = safeRows(data.monthly_pnl);
  makeChart('monthlyChart', 'bar', monthly.map(x => x.month), [{
    label:'Monthly PnL', data:monthly.map(x => x.pnl), backgroundColor: monthly.map(x => Number(x.pnl) >= 0 ? 'rgba(65,226,255,.7)' : 'rgba(255,209,102,.65)'), borderRadius:8
  }], {plugins:{legend:{display:false}}});

  const symbols = safeRows(data.symbol_breakdown);
  makeChart('symbolChart', 'bar', symbols.map(x => x.symbol), [{
    label:'Realized PnL', data:symbols.map(x => x.realized_pnl), backgroundColor:symbols.map(x => Number(x.realized_pnl) >= 0 ? 'rgba(92,255,141,.65)' : 'rgba(255,95,125,.65)'), borderRadius:10
  }], {indexAxis:'y', plugins:{legend:{display:false}}});

  const reasons = safeRows(data.reason_breakdown);
  makeChart('reasonChart', 'doughnut', reasons.map(x => x.reason), [{
    label:'Exits', data:reasons.map(x => Math.abs(x.pnl)), backgroundColor:['rgba(65,226,255,.8)','rgba(155,125,255,.8)','rgba(92,255,141,.8)','rgba(255,95,125,.8)','rgba(255,209,102,.8)','rgba(120,207,255,.8)'], borderWidth:0
  }], {plugins:{legend:{position:'bottom', labels:{color:'#dbe9f8'}}}, scales:{x:{display:false}, y:{display:false}}});
}

async function runJob(kind){
  const map = { trading:'/jobs/run/trading', optimization:'/jobs/run/optimization' };
  const url = map[kind];
  if(!url) return;
  try{
    const btns = document.querySelectorAll('.btn'); btns.forEach(b=>b.disabled=true);
    await fetchJSON(url, {method:'POST'});
    await loadDashboard();
  }catch(err){
    console.error(err);
    alert('Job failed. Check Railway logs.');
  }finally{
    const btns = document.querySelectorAll('.btn'); btns.forEach(b=>b.disabled=false);
  }
}

function setupRefresh(){
  const box = document.getElementById('autoRefresh');
  if(refreshHandle) clearInterval(refreshHandle);
  if(box.checked){
    refreshHandle = setInterval(loadDashboard, 15000);
  }
  box.addEventListener('change', () => {
    if(refreshHandle) clearInterval(refreshHandle);
    if(box.checked) refreshHandle = setInterval(loadDashboard, 15000);
  });
}

loadDashboard();
setupRefresh();
</script>
</body>
</html>
"""


@app.get("/")
def root():
    if worker.settings.root_redirect_to_dashboard:
        return RedirectResponse(url="/dashboard", status_code=307)
    return {
        "service": "adaptive-trading-system-v6-railway-okx-fixed-pairs-dashboard",
        "status": "online",
        "time_utc": datetime.now(timezone.utc).isoformat(),
        "mode": worker.settings.mode,
        "routes": [
            "/health",
            "/status",
            "/scheduler",
            "/dashboard",
            "/api/dashboard",
            "/jobs/run/trading",
            "/jobs/run/optimization",
        ],
    }


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard_page():
    return dashboard_html()


@app.get("/health")
def health():
    return {
        "ok": True,
        "time_utc": datetime.now(timezone.utc).isoformat(),
        "port": os.getenv("PORT"),
        "mode": worker.settings.mode,
        "market_data_source": worker.settings.market_data_source,
        "scheduler_started": scheduler.status()["started"],
    }


@app.get("/status")
def status():
    return JSONResponse(worker.status())


@app.get("/scheduler")
def scheduler_status():
    return scheduler.status()


@app.get("/api/dashboard")
def api_dashboard():
    payload = build_dashboard_payload(worker.store, settings=worker.settings.to_dict())
    payload["health"] = health()
    payload["scheduler"] = scheduler.status()
    payload["service"] = {"mode": worker.settings.mode, "version": app.version}
    return JSONResponse(payload)


@app.post("/jobs/run/trading")
def run_trading_job():
    return JSONResponse(worker.trading_cycle())


@app.post("/jobs/run/optimization")
def run_optimization_job():
    return JSONResponse(worker.optimization_cycle())
