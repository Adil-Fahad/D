/* HALAL SCAN AI PRO ULTIMATE — app.js v3 */
'use strict';

let _signals = [];

document.addEventListener('DOMContentLoaded', () => {
  checkStatus();
  setInterval(checkStatus, 30000);
});

// ── Tab switching ──────────────────────────────────────────────────────────
function showTab(name) {
  document.querySelectorAll('.tab').forEach(t => {
    t.classList.remove('active'); t.classList.add('hidden');
  });
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
  const tab = document.getElementById(`tab-${name}`);
  if (tab) { tab.classList.remove('hidden'); tab.classList.add('active'); }
  const nav = document.getElementById(`nav-${name}`);
  if (nav) nav.classList.add('active');
}

// ── Status ─────────────────────────────────────────────────────────────────
async function checkStatus() {
  const dot  = document.getElementById('status-dot');
  const text = document.getElementById('status-text');
  try {
    const r = await fetch('/api/status');
    const d = await r.json();
    dot.className  = 'dot ' + (d.model_ready ? 'online' : 'offline');
    text.textContent = d.model_ready ? 'Model Ready' : 'No Model';
  } catch {
    dot.className = 'dot error';
    text.textContent = 'Offline';
  }
}

// ── Helpers ────────────────────────────────────────────────────────────────
function pc(p) {
  if (p >= 85) return '#f97316';
  if (p >= 70) return '#22c55e';
  if (p >= 50) return '#eab308';
  return '#ef4444';
}

function vc(v) {
  const m = { 'STRONG BUY': 'v-sb', 'BUY': 'v-buy', 'WATCH': 'v-watch', 'AVOID': 'v-avoid' };
  return 'verdict ' + (m[v] || 'v-avoid');
}

function cc(v) {
  const m = { 'STRONG BUY': 'card-sb', 'BUY': 'card-buy', 'WATCH': 'card-watch', 'AVOID': 'card-avoid' };
  return 'signal-card ' + (m[v] || 'card-avoid');
}

function fn(v, d = 1) {
  if (v == null || isNaN(v)) return '—';
  return parseFloat(v).toFixed(d);
}

function fp(v) {
  if (v == null || isNaN(v)) return '—';
  const n = parseFloat(v);
  if (n >= 1000) return n.toLocaleString('en', { maximumFractionDigits: 2 });
  if (n >= 1)    return n.toFixed(4);
  if (n >= 0.0001) return n.toFixed(6);
  return n.toExponential(3);
}

function ft(iso) {
  if (!iso) return '—';
  try { return new Date(iso).toLocaleString('en-GB', { month: 'short', day: '2-digit', hour: '2-digit', minute: '2-digit' }); }
  catch { return iso; }
}

function ret(v) {
  if (v == null || isNaN(v)) return '<span style="color:var(--muted)">—</span>';
  return `<span class="${v >= 0 ? 'positive' : 'negative'}">${v >= 0 ? '+' : ''}${v.toFixed(2)}%</span>`;
}

function rc(r) {
  if (r >= 70) return '#ef4444';
  if (r <= 30) return '#22c55e';
  return '#e2e8f0';
}

function probRingSM(p) {
  const col = pc(p);
  const deg = Math.round(Math.min(p, 100) * 3.6);
  return `<div class="prob-ring" style="background:conic-gradient(${col} ${deg}deg,rgba(255,255,255,.07) ${deg}deg)">
    <span class="prob-val" style="color:${col}">${p.toFixed(0)}%</span>
    <span class="prob-lbl">AI</span>
  </div>`;
}

function probRingLG(p) {
  const col = pc(p);
  const deg = Math.round(Math.min(p, 100) * 3.6);
  return `<div class="prob-ring-lg" style="background:conic-gradient(${col} ${deg}deg,rgba(255,255,255,.07) ${deg}deg)">
    <span class="val" style="color:${col}">${p.toFixed(1)}%</span>
    <span class="lbl">AI Score</span>
  </div>`;
}

// ── SCAN ───────────────────────────────────────────────────────────────────
async function runScan() {
  const btn   = document.getElementById('scan-btn');
  const modal = document.getElementById('scan-modal');
  const list  = document.getElementById('signals-list');
  const status = document.getElementById('scan-status');

  btn.disabled = true;
  btn.textContent = '⏳ Scanning…';
  modal.classList.remove('hidden');
  list.innerHTML = '';
  if (status) status.style.display = 'none';

  try {
    const r = await fetch('/api/scan', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ min_prob: 55, top_n: 50 }),
    });
    const d = await r.json();

    if (d.success) {
      _signals = d.signals || [];
      renderSignals(_signals);
      updateStats(_signals);
      document.getElementById('stats-row').style.display = 'grid';
      showToast(`✅ ${d.count} signals found`);
    } else {
      showError(list, d.error || 'Scan failed');
    }
  } catch (e) {
    showError(list, 'Connection failed — is server running?');
  } finally {
    btn.disabled = false;
    btn.textContent = '⚡ Scan Market Now';
    modal.classList.add('hidden');
  }
}

function renderSignals(signals) {
  const list = document.getElementById('signals-list');
  const status = document.getElementById('scan-status');

  if (!signals || signals.length === 0) {
    if (status) { status.style.display = 'block'; status.textContent = 'No signals found. Try scanning again.'; }
    return;
  }
  if (status) status.style.display = 'none';

  list.innerHTML = signals.map((s, i) => {
    const verdict = s.combined_verdict || s.verdict || 'AVOID';
    const flow = s.flow_signal
      ? `<div style="margin-top:.5rem;font-size:.68rem;color:var(--muted)">
           Flow: <span style="color:${s.flow_score >= 65 ? 'var(--green)' : s.flow_score <= 35 ? 'var(--red)' : 'var(--yellow)'}">
           ${s.flow_signal}</span>
           ${s.taker_buy_ratio != null ? ` · Buy ${fn(s.taker_buy_ratio)}%` : ''}
         </div>` : '';

    return `<div class="${cc(verdict)}">
      <div class="card-top">
        <span class="card-sym">${s.symbol}</span>
        <span class="${vc(verdict)}">${verdict}</span>
      </div>
      <div class="card-row">
        ${probRingSM(s.probability)}
        <div class="card-grid">
          <div class="mini"><div class="mini-lbl">RSI</div>
            <div class="mini-val" style="color:${rc(s.rsi)}">${fn(s.rsi)}</div></div>
          <div class="mini"><div class="mini-lbl">ADX</div>
            <div class="mini-val">${fn(s.adx)}</div></div>
          <div class="mini"><div class="mini-lbl">Vol</div>
            <div class="mini-val">${fn(s.volume_ratio, 2)}x</div></div>
          <div class="mini"><div class="mini-lbl">24h</div>
            <div class="mini-val">${ret(s.return_24h)}</div></div>
          <div class="mini"><div class="mini-lbl">72h</div>
            <div class="mini-val">${ret(s.return_72h)}</div></div>
          <div class="mini"><div class="mini-lbl">Score</div>
            <div class="mini-val" style="color:${pc(s.probability)}">${fn((s.composite_score || 0) * 100, 0)}%</div></div>
        </div>
      </div>
      ${flow}
      <button class="analyze-btn" onclick="goAnalyze('${s.symbol}')">🔬 Deep Analyze</button>
    </div>`;
  }).join('');
}

function updateStats(signals) {
  const total  = signals.length;
  const strong = signals.filter(s => (s.combined_verdict || s.verdict) === 'STRONG BUY').length;
  const buy    = signals.filter(s => (s.combined_verdict || s.verdict) === 'BUY').length;
  const avg    = total > 0 ? (signals.reduce((a, s) => a + s.probability, 0) / total).toFixed(1) + '%' : '—';
  setText('stat-total',  total);
  setText('stat-strong', strong);
  setText('stat-buy',    buy);
  setText('stat-avg',    avg);
}

// ── ANALYZER ───────────────────────────────────────────────────────────────
function qa(coin) {
  const inp = document.getElementById('coin-input');
  if (inp) inp.value = coin;
  showTab('analyzer');
  analyzeCoin();
}

function goAnalyze(coin) {
  const inp = document.getElementById('coin-input');
  if (inp) inp.value = coin;
  showTab('analyzer');
  analyzeCoin();
}

async function analyzeCoin() {
  const inp     = document.getElementById('coin-input');
  const loading = document.getElementById('analyze-loading');
  const errBox  = document.getElementById('analyze-error');
  const result  = document.getElementById('analyze-result');
  const coin    = (inp?.value || '').trim().toUpperCase();

  if (!coin) { showToast('Enter a symbol first'); return; }

  loading.classList.remove('hidden');
  errBox.classList.add('hidden');
  result.innerHTML = '';

  try {
    const r = await fetch(`/api/analyze/${coin}`);
    const d = await r.json();
    if (d.error) {
      errBox.textContent = d.error;
      errBox.classList.remove('hidden');
    } else {
      result.innerHTML = buildAnalyzeCard(d);
    }
  } catch {
    errBox.textContent = 'Request failed — check connection.';
    errBox.classList.remove('hidden');
  } finally {
    loading.classList.add('hidden');
  }
}

function buildAnalyzeCard(d) {
  const prob    = d.probability || 0;
  const verdict = d.combined_verdict || d.verdict || 'AVOID';
  const str     = d.signal_strength || 1;
  const pips    = [1,2,3,4].map(n => `<div class="pip ${n <= str ? 'on' : ''}"></div>`).join('');
  const hasFlow = d.flow_score != null;

  const flowHTML = hasFlow ? `
    <div class="flow-section">
      <div class="flow-title">⚡ Order Flow</div>
      <div class="flow-grid">
        <div><div class="flow-lbl">Flow Score</div>
          <div class="flow-val" style="color:${pc(d.flow_score)}">${fn(d.flow_score)}%</div></div>
        <div><div class="flow-lbl">Signal</div>
          <div class="flow-val" style="font-size:.78rem">${d.flow_signal || '—'}</div></div>
        <div><div class="flow-lbl">Buy Ratio</div>
          <div class="flow-val" style="color:${(d.taker_buy_ratio||50) >= 50 ? 'var(--green)' : 'var(--red)'}">
            ${fn(d.taker_buy_ratio)}%</div></div>
        <div><div class="flow-lbl">OB Imbalance</div>
          <div class="flow-val" style="color:${(d.ob_imbalance_pct||0) >= 0 ? 'var(--green)' : 'var(--red)'}">
            ${d.ob_imbalance_pct != null ? (d.ob_imbalance_pct >= 0 ? '+' : '') + fn(d.ob_imbalance_pct) + '%' : '—'}</div></div>
        <div><div class="flow-lbl">Whale Buys</div>
          <div class="flow-val" style="color:var(--green)">${d.whale_buys ?? '—'}</div></div>
        <div><div class="flow-lbl">Whale Sells</div>
          <div class="flow-val" style="color:var(--red)">${d.whale_sells ?? '—'}</div></div>
      </div>
      <div class="flow-bar-wrap">
        <div class="flow-bar-labels">
          <span>Sell ${fn(100-(d.taker_buy_ratio||50))}%</span>
          <span>Buy ${fn(d.taker_buy_ratio||50)}%</span>
        </div>
        <div class="flow-bar-track">
          <div class="flow-bar-fill" style="width:100%"></div>
          <div class="flow-bar-marker" style="left:${d.taker_buy_ratio||50}%"></div>
        </div>
      </div>
    </div>` : `<div class="error-box" style="margin-bottom:1rem">Order flow unavailable.</div>`;

  return `<div class="analyze-card">
    <div class="analyze-hero">
      ${probRingLG(prob)}
      <div style="flex:1">
        <div class="analyze-sym">${d.symbol}</div>
        <div class="analyze-price">${fp(d.price)} USDT</div>
        <div style="margin-top:.5rem;display:flex;align-items:center;gap:.5rem">
          <span class="${vc(verdict)}">${verdict}</span>
        </div>
        <div class="pips">${pips}</div>
      </div>
    </div>
    ${flowHTML}
    <div class="metrics-grid">
      <div class="metric-box"><div class="metric-lbl">RSI (14)</div>
        <div class="metric-val" style="color:${rc(d.rsi)}">${fn(d.rsi)}</div></div>
      <div class="metric-box"><div class="metric-lbl">ADX</div>
        <div class="metric-val">${fn(d.adx)}</div></div>
      <div class="metric-box"><div class="metric-lbl">Vol Ratio</div>
        <div class="metric-val">${fn(d.volume_ratio,2)}x</div></div>
      <div class="metric-box"><div class="metric-lbl">Return 24h</div>
        <div class="metric-val">${ret(d.return_24h)}</div></div>
      <div class="metric-box"><div class="metric-lbl">Return 72h</div>
        <div class="metric-val">${ret(d.return_72h)}</div></div>
      <div class="metric-box"><div class="metric-lbl">MACD</div>
        <div class="metric-val" style="font-size:.75rem">${fn(d.macd,6)}</div></div>
      <div class="metric-box"><div class="metric-lbl">EMA 20</div>
        <div class="metric-val" style="font-size:.75rem">${fp(d.ema20)}</div></div>
      <div class="metric-box"><div class="metric-lbl">EMA 50</div>
        <div class="metric-val" style="font-size:.75rem">${fp(d.ema50)}</div></div>
      <div class="metric-box"><div class="metric-lbl">Scanned</div>
        <div class="metric-val" style="font-size:.68rem;color:var(--muted)">${ft(d.scanned_at)}</div></div>
    </div>
  </div>`;
}

// ── Utilities ──────────────────────────────────────────────────────────────
function setText(id, v) {
  const el = document.getElementById(id);
  if (el) el.textContent = v;
}

function showError(container, msg) {
  container.innerHTML = `<div class="error-box">${msg}</div>`;
}

let _tt = null;
function showToast(msg) {
  const t = document.getElementById('toast');
  if (!t) return;
  t.textContent = msg;
  t.classList.remove('hidden');
  if (_tt) clearTimeout(_tt);
  _tt = setTimeout(() => t.classList.add('hidden'), 3000);
}
