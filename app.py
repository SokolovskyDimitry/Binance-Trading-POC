"""
Binance Public Market Data Web Dashboard Server
Built with Python's standard http.server (Zero external dependencies).
Serves a full interactive dashboard UI with real-time tickers, 24h stats, order book visualizer, OHLC Candlestick chart, and Indicator overlays.
"""

import json
import os
import sys
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
import numpy as np

# Ensure stdout handles UTF-8 on Windows command prompts
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from binance_client import BinancePublicClient, BinanceAPIError
from indicators import detect_breakouts
from reasoning import BreakthroughReasoningEngine

# Initialize global Binance client and reasoning engine
client = BinancePublicClient()
_reasoning_engine = BreakthroughReasoningEngine()


def clean_numpy_for_json(obj):
    """Convert NumPy arrays and types to standard Python JSON-serializable types."""
    if isinstance(obj, np.ndarray):
        return [None if (np.isnan(x) or np.isinf(x)) else float(x) for x in obj]
    elif isinstance(obj, dict):
        return {k: clean_numpy_for_json(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [clean_numpy_for_json(x) for x in obj]
    elif isinstance(obj, (np.floating, np.integer)):
        return float(obj)
    elif isinstance(obj, (np.bool_, bool)):
        return bool(obj)
    elif isinstance(obj, np.generic):
        return obj.item()
    return obj


HTML_DASHBOARD = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Binance Public Market Dashboard</title>
  <!-- Chart.js CDN -->
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
  <style>
    :root {
      --bg-color: #0b0e11;
      --card-bg: #181a20;
      --border-color: #2b313a;
      --text-main: #eaecef;
      --text-muted: #848e9c;
      --green: #0ecb81;
      --red: #f6465d;
      --accent: #f0b90b;
      --donchian: #f0b90b;
      --bollinger: #36a2eb;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
    body { background-color: var(--bg-color); color: var(--text-main); padding: 20px; }
    header { display: flex; justify-content: space-between; align-items: center; padding-bottom: 20px; border-bottom: 1px solid var(--border-color); margin-bottom: 20px; flex-wrap: wrap; gap: 15px; }
    .logo { display: flex; align-items: center; gap: 10px; font-size: 1.4rem; font-weight: bold; color: var(--accent); }
    .search-container { display: flex; gap: 10px; align-items: center; }
    input[type="text"] { background: #2b313a; border: 1px solid var(--border-color); color: var(--text-main); padding: 8px 14px; border-radius: 6px; font-size: 1rem; outline: none; text-transform: uppercase; }
    button { background: var(--accent); color: #000; border: none; padding: 8px 16px; border-radius: 6px; font-weight: bold; cursor: pointer; transition: opacity 0.2s; }
    button:hover { opacity: 0.9; }
    .quick-symbols { display: flex; gap: 8px; margin-top: 10px; }
    .quick-btn { background: var(--card-bg); border: 1px solid var(--border-color); color: var(--text-muted); padding: 4px 10px; border-radius: 4px; font-size: 0.85rem; cursor: pointer; }
    .quick-btn:hover, .quick-btn.active { color: var(--accent); border-color: var(--accent); }
    
    .ticker-bar { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 15px; margin-bottom: 20px; }
    .metric-card { background: var(--card-bg); border: 1px solid var(--border-color); padding: 15px; border-radius: 8px; }
    .metric-label { font-size: 0.8rem; color: var(--text-muted); margin-bottom: 6px; }
    .metric-value { font-size: 1.3rem; font-weight: bold; }
    .green { color: var(--green); }
    .red { color: var(--red); }

    .main-grid { display: grid; grid-template-columns: 2fr 1fr; gap: 20px; margin-bottom: 20px; }
    @media (max-width: 992px) { .main-grid { grid-template-columns: 1fr; } }
    
    .panel { background: var(--card-bg); border: 1px solid var(--border-color); border-radius: 8px; padding: 20px; }
    .panel-title { font-size: 1.1rem; font-weight: bold; margin-bottom: 15px; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 10px; }

    .interval-selector { display: flex; gap: 6px; }
    .int-btn { background: #2b313a; border: none; color: var(--text-muted); padding: 4px 8px; border-radius: 4px; font-size: 0.8rem; cursor: pointer; }
    .int-btn.active { background: var(--accent); color: #000; font-weight: bold; }

    .toggle-bar { display: flex; gap: 10px; align-items: center; margin-bottom: 10px; font-size: 0.85rem; background: #12141a; padding: 8px 12px; border-radius: 6px; border: 1px solid var(--border-color); flex-wrap: wrap; }
    .toggle-label { display: flex; align-items: center; gap: 6px; cursor: pointer; color: var(--text-main); font-weight: 500; }
    .toggle-label input { cursor: pointer; accent-color: var(--accent); }

    .order-book-container { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; font-size: 0.85rem; }
    .book-row { display: flex; justify-content: space-between; padding: 3px 0; border-bottom: 1px solid #22262d; }

    .movers-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px; }
    table { width: 100%; border-collapse: collapse; font-size: 0.9rem; }
    th { text-align: left; padding: 10px; color: var(--text-muted); border-bottom: 1px solid var(--border-color); }
    td { padding: 8px 10px; border-bottom: 1px solid #22262d; }
    tr:hover { background: #22262d; cursor: pointer; }
    
    .badge { background: rgba(14, 203, 129, 0.15); color: var(--green); padding: 2px 6px; border-radius: 4px; font-weight: bold; font-size: 0.8rem; }
    .badge-red { background: rgba(246, 70, 93, 0.15); color: var(--red); }
  </style>
</head>
<body>

  <header>
    <div>
      <div class="logo">[Binance] Public Market Dashboard</div>
      <div style="font-size: 0.85rem; color: var(--text-muted); margin-top: 4px;">Real-Time Public REST API v3 • Interactive Candlesticks & Technical Indicators</div>
      <div class="quick-symbols">
        <button class="quick-btn active" onclick="selectSymbol('BTCUSDT')">BTC/USDT</button>
        <button class="quick-btn" onclick="selectSymbol('ETHUSDT')">ETH/USDT</button>
        <button class="quick-btn" onclick="selectSymbol('SOLUSDT')">SOL/USDT</button>
        <button class="quick-btn" onclick="selectSymbol('BNBUSDT')">BNB/USDT</button>
        <button class="quick-btn" onclick="selectSymbol('XRPUSDT')">XRP/USDT</button>
        <button class="quick-btn" onclick="selectSymbol('DOGEUSDT')">DOGE/USDT</button>
      </div>
    </div>
    <div class="search-container">
      <input type="text" id="symbolInput" value="BTCUSDT" placeholder="Symbol (e.g. BTCUSDT)">
      <button onclick="handleSearch()">Load Market</button>
    </div>
  </header>

  <!-- Metric Bar -->
  <div class="ticker-bar">
    <div class="metric-card">
      <div class="metric-label">Last Price</div>
      <div class="metric-value" id="valLastPrice">--</div>
    </div>
    <div class="metric-card">
      <div class="metric-label">24h Change</div>
      <div class="metric-value" id="valPriceChange">--</div>
    </div>
    <div class="metric-card">
      <div class="metric-label">24h High</div>
      <div class="metric-value" id="valHigh">--</div>
    </div>
    <div class="metric-card">
      <div class="metric-label">24h Low</div>
      <div class="metric-value" id="valLow">--</div>
    </div>
    <div class="metric-card">
      <div class="metric-label">24h Volume (Quote)</div>
      <div class="metric-value" id="valVolume">--</div>
    </div>
  </div>

  <!-- Main Grid: Chart & Order Book -->
  <div class="main-grid">
    <div class="panel">
      <div class="panel-title">
        <span id="chartTitle">BTCUSDT Candlesticks & Technical Overlays</span>
        <div class="interval-selector">
          <button class="int-btn" onclick="setInterval('1m')">1m</button>
          <button class="int-btn" onclick="setInterval('5m')">5m</button>
          <button class="int-btn" onclick="setInterval('15m')">15m</button>
          <button class="int-btn active" onclick="setInterval('1h')">1h</button>
          <button class="int-btn" onclick="setInterval('4h')">4h</button>
          <button class="int-btn" onclick="setInterval('1d')">1d</button>
        </div>
      </div>

      <!-- Controls Toggle Bar -->
      <div class="toggle-bar">
        <span style="color: var(--text-muted); font-weight: bold; margin-right: 5px;">View Overlays:</span>
        <label class="toggle-label">
          <input type="checkbox" id="chkCandles" checked onchange="updateChartOverlays()"> OHLC Candlestick Bars
        </label>
        <label class="toggle-label" style="color: var(--donchian)">
          <input type="checkbox" id="chkDonchian" checked onchange="updateChartOverlays()"> Donchian Channels (20)
        </label>
        <label class="toggle-label" style="color: var(--bollinger)">
          <input type="checkbox" id="chkBollinger" checked onchange="updateChartOverlays()"> Bollinger Bands (20, 2)
        </label>
        <label class="toggle-label" style="color: var(--text-muted)">
          <input type="checkbox" id="chkVolume" checked onchange="updateChartOverlays()"> Volume Bars
        </label>
        <label class="toggle-label" style="color: var(--green)">
          <input type="checkbox" id="chkSignals" checked onchange="updateChartOverlays()"> Entry Signals (Triangles)
        </label>
      </div>

      <div style="height: 400px; position: relative;">
        <canvas id="priceChart"></canvas>
      </div>
    </div>

    <div class="panel">
      <div class="panel-title">Order Book Depth (Top 10)</div>
      <div class="order-book-container">
        <div>
          <div style="color: var(--green); font-weight: bold; margin-bottom: 8px;">BIDS (Buy)</div>
          <div id="bidsContainer"></div>
        </div>
        <div>
          <div style="color: var(--red); font-weight: bold; margin-bottom: 8px;">ASKS (Sell)</div>
          <div id="asksContainer"></div>
        </div>
      </div>
      
      <div style="border-top: 1px solid var(--border-color); margin-top: 15px; padding-top: 15px;">
  <div class="panel-title" style="font-size: 0.95rem;">Technical Indicators &amp; Breakouts</div>
  <div style="font-size: 0.85rem; display: grid; gap: 6px;">
    <div class="book-row"><span>Donchian Upper (20):</span><strong id="valDonchianUpper">--</strong></div>
    <div class="book-row"><span>Donchian Lower (20):</span><strong id="valDonchianLower">--</strong></div>
    <div class="book-row"><span>Volume Ratio (vs 20 MA):</span><strong id="valVolRatio">--</strong></div>
    <div class="book-row"><span>Bollinger Squeeze:</span><strong id="valSqueeze">--</strong></div>
    <div class="book-row"><span>Breakout Signal:</span><strong id="valBreakout">NONE</strong></div>
  </div>
  <!-- AI Conviction / Reasoning Panel -->
  <div style="margin-top: 14px; padding: 12px; background: #12141a; border-radius: 6px; border: 1px solid var(--border-color);">
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
      <span style="font-size: 0.8rem; color: var(--text-muted); font-weight: bold; text-transform: uppercase; letter-spacing: 0.05em;">AI Conviction Score</span>
      <span id="convictionGradeBadge" style="font-size: 0.75rem; font-weight: bold; padding: 2px 8px; border-radius: 4px; background: #2b313a; color: var(--text-muted);">--</span>
    </div>
    <div style="background: #2b313a; border-radius: 4px; height: 10px; margin-bottom: 8px; overflow: hidden;">
      <div id="convictionBar" style="height: 100%; width: 0%; border-radius: 4px; transition: width 0.5s ease, background-color 0.5s ease; background: #848e9c;"></div>
    </div>
    <div style="display: flex; justify-content: space-between; font-size: 0.78rem; color: var(--text-muted); margin-bottom: 10px;">
      <span>0</span>
      <span id="convictionScore" style="font-weight: bold; color: var(--text-main);">--</span>
      <span>100</span>
    </div>
    <div id="factorGrid" style="display: grid; grid-template-columns: 1fr 1fr; gap: 4px 10px; font-size: 0.78rem; margin-bottom: 10px;"></div>
    <details id="reasonsDetails" style="font-size: 0.78rem;">
      <summary style="cursor: pointer; color: var(--text-muted); user-select: none; padding: 2px 0;">&#9654; View reasoning</summary>
      <ol id="reasonsList" style="margin: 6px 0 0 16px; display: grid; gap: 4px; color: var(--text-main); line-height: 1.4;"></ol>
    </details>
  </div>
</div>

    </div>
  </div>

  <!-- Top Movers Grid -->
  <div class="movers-grid">
    <div class="panel">
      <div class="panel-title">Top Gainers (24h)</div>
      <table>
        <thead>
          <tr><th>Symbol</th><th>Price</th><th>24h %</th></tr>
        </thead>
        <tbody id="tblGainers"></tbody>
      </table>
    </div>
    <div class="panel">
      <div class="panel-title">Top Losers (24h)</div>
      <table>
        <thead>
          <tr><th>Symbol</th><th>Price</th><th>24h %</th></tr>
        </thead>
        <tbody id="tblLosers"></tbody>
      </table>
    </div>
    <div class="panel">
      <div class="panel-title">Highest Volume Pairs</div>
      <table>
        <thead>
          <tr><th>Symbol</th><th>Price</th><th>24h Volume</th></tr>
        </thead>
        <tbody id="tblVolume"></tbody>
      </table>
    </div>
  </div>

  <script>
    let currentSymbol = 'BTCUSDT';
    let currentInterval = '1h';
    let chartInstance = null;
let cachedIndicatorData = null;
let reasoningBars = []; // holds full reasoning data for chart overlay

    // Custom Candlestick plugin for Chart.js
    const candlestickPlugin = {
      id: 'candlestickPlugin',
      beforeDraw(chart) {
        if (!document.getElementById('chkCandles').checked) return;
        const meta = chart.getDatasetMeta(0);
        if (!meta || !meta.data || !chart.config.options.customOHLC) return;
        
        const ctx = chart.ctx;
        const ohlcData = chart.config.options.customOHLC;
        const yScale = chart.scales.y;
        
        ctx.save();
        meta.data.forEach((element, i) => {
          const item = ohlcData[i];
          if (!item) return;

          const x = element.x;
          const openY = yScale.getPixelForValue(item.open);
          const closeY = yScale.getPixelForValue(item.close);
          const highY = yScale.getPixelForValue(item.high);
          const lowY = yScale.getPixelForValue(item.low);

          const isBull = item.close >= item.open;
          const color = isBull ? '#0ecb81' : '#f6465d';

          // Draw High-Low Wick
          ctx.beginPath();
          ctx.strokeStyle = color;
          ctx.lineWidth = 1.5;
          ctx.moveTo(x, highY);
          ctx.lineTo(x, lowY);
          ctx.stroke();

          // Draw Open-Close Candle Body
          const candleWidth = Math.max(3, Math.min(10, (chart.chartArea.width / ohlcData.length) * 0.6));
          const topY = Math.min(openY, closeY);
          const bodyHeight = Math.max(2, Math.abs(closeY - openY));

          ctx.fillStyle = color;
          ctx.fillRect(x - candleWidth / 2, topY, candleWidth, bodyHeight);
        });
        ctx.restore();
      }
    };

    Chart.register(candlestickPlugin);

    function formatCurrency(val) {
      if (!val && val !== 0) return '--';
      const n = parseFloat(val);
      if (n >= 1000) return '$' + n.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2});
      if (n >= 1) return '$' + n.toLocaleString(undefined, {minimumFractionDigits: 4, maximumFractionDigits: 4});
      return '$' + n.toLocaleString(undefined, {minimumFractionDigits: 6, maximumFractionDigits: 8});
    }

    function formatPercent(val) {
      const n = parseFloat(val);
      const prefix = n > 0 ? '+' : '';
      return `${prefix}${n.toFixed(2)}%`;
    }

    async function loadStats() {
      try {
        const res = await fetch(`/api/stats?symbol=${currentSymbol}`);
        const data = await res.json();
        
        document.getElementById('valLastPrice').innerText = formatCurrency(data.lastPrice);
        
        const changeElem = document.getElementById('valPriceChange');
        changeElem.innerText = formatPercent(data.priceChangePercent);
        changeElem.className = 'metric-value ' + (data.priceChangePercent >= 0 ? 'green' : 'red');

        document.getElementById('valHigh').innerText = formatCurrency(data.highPrice);
        document.getElementById('valLow').innerText = formatCurrency(data.lowPrice);
        document.getElementById('valVolume').innerText = '$' + (data.quoteVolume).toLocaleString(undefined, {maximumFractionDigits: 0});
      } catch (err) {
        console.error("Failed to load stats:", err);
      }
    }

    async function loadChartAndIndicators() {
      try {
        // ── Primary load: indicators + chart (fast, must not block) ──────────
        const indRes = await fetch(`/api/indicators?symbol=${currentSymbol}&interval=${currentInterval}`);
        const data = await indRes.json();
        cachedIndicatorData = data;

        document.getElementById('chartTitle').innerText = `${currentSymbol} (${currentInterval}) Candlesticks & Indicators`;

        // Update side panel values
        const latest = data.latest;
        document.getElementById('valDonchianUpper').innerText = formatCurrency(latest.upper_channel);
        document.getElementById('valDonchianLower').innerText = formatCurrency(latest.lower_channel);

        const volRatioElem = document.getElementById('valVolRatio');
        volRatioElem.innerText = `${latest.volume_ratio.toFixed(2)}x ${latest.is_volume_expansion ? '⚡' : ''}`;
        volRatioElem.style.color = latest.is_volume_expansion ? 'var(--accent)' : 'var(--text-main)';

        const sqzElem = document.getElementById('valSqueeze');
        sqzElem.innerText = latest.is_squeeze ? 'ACTIVE SQUEEZE ⚠️' : 'NONE';
        sqzElem.style.color = latest.is_squeeze ? 'var(--accent)' : 'var(--text-muted)';

        const boElem = document.getElementById('valBreakout');
        if (latest.bullish_breakout) {
          boElem.innerText = '🟢 BULLISH BREAKOUT!';
          boElem.style.color = 'var(--green)';
        } else if (latest.bearish_breakout) {
          boElem.innerText = '🔴 BEARISH BREAKOUT!';
          boElem.style.color = 'var(--red)';
        } else {
          boElem.innerText = 'NONE';
          boElem.style.color = 'var(--text-muted)';
        }

        // ── Conviction panel from inline reasoning (already in /api/indicators) ──
        renderConvictionPanel(data.reasoning);

        // ── Render chart immediately with whatever reasoningBars we have ──────
        renderChart();

        // ── Load entry-point markers asynchronously (non-blocking) ───────────
        fetch(`/api/reasoning?symbol=${currentSymbol}&interval=${currentInterval}&min_score=30&limit=100`)
          .then(r => r.json())
          .then(reasonData => {
            reasoningBars = reasonData.bars || [];
            renderChart(); // re-render with markers once reasoning arrives
          })
          .catch(() => {}); // silent fail — chart already drawn above

      } catch (err) {
        console.error("Failed to load chart and indicators:", err);
      }
    }

    function renderConvictionPanel(r) {
      const convBar   = document.getElementById('convictionBar');
      const convScore = document.getElementById('convictionScore');
      const convBadge = document.getElementById('convictionGradeBadge');
      const factorGrid  = document.getElementById('factorGrid');
      const reasonsList = document.getElementById('reasonsList');

      if (r && r.signal && r.signal !== 'NONE') {
        const score = r.conviction_score || 0;
        const grade = r.grade || 'WEAK';
        const color = grade === 'STRONG' ? '#0ecb81' : grade === 'MODERATE' ? '#f0b90b' : '#f6465d';
        convBar.style.width = score + '%';
        convBar.style.background = color;
        convScore.innerText = score.toFixed(1) + ' / 100';
        convBadge.innerText = r.signal + ' · ' + grade;
        convBadge.style.background = color + '33';
        convBadge.style.color = color;
        const factors = r.factor_scores || {};
        factorGrid.innerHTML = Object.entries(factors).map(([k, v]) =>
          `<span style="color:var(--text-muted)">${k.replace(/_/g,' ')}:</span><span style="font-weight:bold">${(v||0).toFixed(1)}</span>`
        ).join('');
        const reasons = r.reasons || [];
        reasonsList.innerHTML = reasons.map(reason => `<li>${reason}</li>`).join('');
      } else {
        convBar.style.width = (r && r.conviction_score) ? (r.conviction_score + '%') : '0%';
        convBar.style.background = '#848e9c';
        convScore.innerText = (r && r.conviction_score != null) ? (r.conviction_score.toFixed(1) + ' / 100') : '--';
        convBadge.innerText = 'NONE';
        convBadge.style.color = 'var(--text-muted)';
        convBadge.style.background = '#2b313a';
        factorGrid.innerHTML = '';
        reasonsList.innerHTML = '<li style="color:var(--text-muted)">No confirmed breakout on current bar.</li>';
      }
    }

    function renderChart() {
      if (!cachedIndicatorData) return;
      const data = cachedIndicatorData;
      const klines = data.klines;

      const labels = klines.map(k => k.open_datetime.replace('T', ' ').slice(5, 16));
      const closePrices = klines.map(k => k.close);
      const volumes = klines.map(k => k.volume);
      const maxVol = Math.max(...volumes);

      const showCandles = document.getElementById('chkCandles').checked;
      const showDonchian = document.getElementById('chkDonchian').checked;
      const showBollinger = document.getElementById('chkBollinger').checked;
      const showVolume = document.getElementById('chkVolume').checked;

      const datasets = [];

      // Primary Close / Line Dataset
      datasets.push({
        label: `${currentSymbol} Close`,
        data: closePrices,
        borderColor: showCandles ? 'rgba(255, 255, 255, 0.2)' : '#0ecb81',
        backgroundColor: showCandles ? 'transparent' : 'rgba(14, 203, 129, 0.1)',
        borderWidth: showCandles ? 1 : 2,
        pointRadius: 0,
        fill: !showCandles
      });

      // Volume Histogram Dataset (positioned on yVolume scale at bottom)
      if (showVolume) {
        datasets.push({
          type: 'bar',
          label: 'Trading Volume',
          data: volumes,
          yAxisID: 'yVolume',
          backgroundColor: klines.map(k => k.close >= k.open ? 'rgba(14, 203, 129, 0.45)' : 'rgba(246, 70, 93, 0.45)'),
          borderColor: klines.map(k => k.close >= k.open ? '#0ecb81' : '#f6465d'),
          borderWidth: 1,
          barPercentage: 0.65
        });
      }

      // Donchian Channels Datasets
      if (showDonchian) {
        datasets.push({
          label: 'Donchian Upper (20)',
          data: data.donchian.upper,
          borderColor: '#f0b90b',
          borderDash: [4, 4],
          borderWidth: 1.5,
          pointRadius: 0,
          fill: false
        });
        datasets.push({
          label: 'Donchian Lower (20)',
          data: data.donchian.lower,
          borderColor: '#f0b90b',
          borderDash: [4, 4],
          borderWidth: 1.5,
          pointRadius: 0,
          fill: false
        });
      }

      // Bollinger Bands Datasets
      if (showBollinger) {
        datasets.push({
          label: 'Bollinger Upper (20, 2)',
          data: data.bollinger.upper,
          borderColor: '#36a2eb',
          borderWidth: 1.5,
          pointRadius: 0,
          fill: false
        });
        datasets.push({
          label: 'Bollinger Lower (20, 2)',
          data: data.bollinger.lower,
          borderColor: '#36a2eb',
          borderWidth: 1.5,
          pointRadius: 0,
          fill: false
        });
        datasets.push({
          label: 'Bollinger SMA',
          data: data.bollinger.sma,
          borderColor: '#9966ff',
          borderWidth: 1,
          borderDash: [2, 2],
          pointRadius: 0,
          fill: false
        });
      }

      // ── Entry Point Markers ───────────────────────────────────────────────
      const showSignals = document.getElementById('chkSignals') ? document.getElementById('chkSignals').checked : true;
      if (showSignals && reasoningBars.length > 0) {
        const klinesByTime = {};
        klines.forEach((k, idx) => { klinesByTime[k.open_time] = idx; });

        const bullishPoints = new Array(klines.length).fill(null);
        const bearishPoints = new Array(klines.length).fill(null);

        reasoningBars.forEach(r => {
          const idx = klinesByTime[r.timestamp];
          if (idx === undefined) return;
          if (r.signal === 'BULLISH' && (r.is_confirmed || r.conviction_score >= 30)) {
            bullishPoints[idx] = klines[idx].low * 0.9985;
          } else if (r.signal === 'BEARISH' && (r.is_confirmed || r.conviction_score >= 30)) {
            bearishPoints[idx] = klines[idx].high * 1.0015;
          }
        });

        if (bullishPoints.some(v => v !== null)) {
          datasets.push({
            label: '🟢 Bullish Entry',
            data: bullishPoints,
            pointStyle: 'triangle',
            pointRadius: 10,
            pointHoverRadius: 13,
            pointRotation: 0,
            backgroundColor: '#0ecb81',
            borderColor: '#0ecb81',
            borderWidth: 0,
            showLine: false
          });
        }

        if (bearishPoints.some(v => v !== null)) {
          datasets.push({
            label: '🔴 Bearish Entry',
            data: bearishPoints,
            pointStyle: 'triangle',
            pointRadius: 10,
            pointHoverRadius: 13,
            pointRotation: 180,
            backgroundColor: '#f6465d',
            borderColor: '#f6465d',
            borderWidth: 0,
            showLine: false
          });
        }
      }

      const ctx = document.getElementById('priceChart').getContext('2d');
      if (chartInstance) {
        chartInstance.destroy();
      }

      chartInstance = new Chart(ctx, {
        type: 'line',
        data: { labels: labels, datasets: datasets },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          customOHLC: klines,
          plugins: {
            legend: { display: true, labels: { color: '#848e9c', font: { size: 11 } } },
            tooltip: {
              callbacks: {
                label: function(context) {
                  const idx = context.dataIndex;
                  const k = klines[idx];
                  if (context.datasetIndex === 0 && k) {
                    return [
                      `Open:  $${k.open.toLocaleString()}`,
                      `High:  $${k.high.toLocaleString()}`,
                      `Low:   $${k.low.toLocaleString()}`,
                      `Close: $${k.close.toLocaleString()}`,
                      `Vol:   ${k.volume.toLocaleString()}`
                    ];
                  }
                  if (context.dataset.label && context.dataset.label.includes('Entry') && k) {
                    const r = reasoningBars.find(b => b.timestamp === k.open_time);
                    if (r) {
                      return `${context.dataset.label}: Score ${r.conviction_score.toFixed(1)}/100 (${r.grade})`;
                    }
                  }
                  return `${context.dataset.label}: ${context.raw ? context.raw.toLocaleString() : '--'}`;
                }
              }
            }
          },
          scales: {
            x: { grid: { color: '#22262d' }, ticks: { color: '#848e9c', maxTicksLimit: 10 } },
            y: { position: 'left', grid: { color: '#22262d' }, ticks: { color: '#848e9c' } },
            yVolume: {
              type: 'linear',
              position: 'right',
              display: false,
              grid: { display: false },
              min: 0,
              max: maxVol * 4
            }
          }
        }
      });
    }

    function updateChartOverlays() {
      renderChart();
    }

    async function loadOrderBook() {
      try {
        const res = await fetch(`/api/depth?symbol=${currentSymbol}&limit=10`);
        const data = await res.json();

        const bidsContainer = document.getElementById('bidsContainer');
        const asksContainer = document.getElementById('asksContainer');

        bidsContainer.innerHTML = data.bids.map(b => `<div class="book-row"><span>${formatCurrency(b[0])}</span><span style="color:var(--text-muted)">${b[1].toFixed(4)}</span></div>`).join('');
        asksContainer.innerHTML = data.asks.map(a => `<div class="book-row"><span>${formatCurrency(a[0])}</span><span style="color:var(--text-muted)">${a[1].toFixed(4)}</span></div>`).join('');
      } catch (err) {
        console.error("Failed to load order book:", err);
      }
    }

    async function loadMovers() {
      try {
        const res = await fetch('/api/movers?limit=6&quote=USDT');
        const data = await res.json();

        const renderRows = (items, isVol=false) => items.map(item => `
          <tr onclick="selectSymbol('${item.symbol}')">
            <td><strong>${item.symbol}</strong></td>
            <td>${formatCurrency(item.lastPrice)}</td>
            <td><span class="badge ${item.priceChangePercent >= 0 ? '' : 'badge-red'}">${isVol ? '$' + (item.quoteVolume/1e6).toFixed(1) + 'M' : formatPercent(item.priceChangePercent)}</span></td>
          </tr>
        `).join('');

        document.getElementById('tblGainers').innerHTML = renderRows(data.gainers);
        document.getElementById('tblLosers').innerHTML = renderRows(data.losers);
        document.getElementById('tblVolume').innerHTML = renderRows(data.volume, true);
      } catch (err) {
        console.error("Failed to load movers:", err);
      }
    }

    function selectSymbol(sym) {
      currentSymbol = sym.toUpperCase();
      document.getElementById('symbolInput').value = currentSymbol;
      
      document.querySelectorAll('.quick-btn').forEach(btn => {
        btn.classList.toggle('active', btn.innerText.replace('/', '') === currentSymbol);
      });

      refreshAll();
    }

    function handleSearch() {
      const val = document.getElementById('symbolInput').value.trim();
      if (val) selectSymbol(val);
    }

    function setInterval(intv) {
      currentInterval = intv;
      document.querySelectorAll('.int-btn').forEach(btn => {
        btn.classList.toggle('active', btn.innerText === intv);
      });
      loadChartAndIndicators();
    }

    function refreshAll() {
      loadStats();
      loadChartAndIndicators();
      loadOrderBook();
    }

    // Initial load
    refreshAll();
    loadMovers();

    // Auto refresh stats & order book every 1s (max safe REST polling rate)
    // Chart/indicators refresh every 5s to avoid heavy klines requests on each tick
    window.setInterval(() => {
      loadStats();
      loadOrderBook();
    }, 1000);
    window.setInterval(() => {
      loadChartAndIndicators();
    }, 5000);
  </script>
</body>
</html>
"""


class DashboardRequestHandler(BaseHTTPRequestHandler):
    """Custom HTTP request handler serving REST API endpoints and web UI."""

    def _send_json(self, data: Any, status: int = 200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode("utf-8"))

    def _send_html(self, html_content: str, status: int = 200):
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html_content.encode("utf-8"))

    def do_GET(self):
        parsed_path = urllib.parse.urlparse(self.path)
        path = parsed_path.path
        query = urllib.parse.parse_qs(parsed_path.query)

        def get_param(name: str, default: Any = None) -> Any:
            return query.get(name, [default])[0]

        try:
            if path == "/" or path == "/index.html":
                self._send_html(HTML_DASHBOARD)
            elif path == "/api/ping":
                self._send_json({"status": "ok", "ping": client.ping()})
            elif path == "/api/ticker":
                symbol = get_param("symbol", "BTCUSDT")
                self._send_json(client.get_ticker_price(symbol))
            elif path == "/api/stats":
                symbol = get_param("symbol", "BTCUSDT")
                self._send_json(client.get_24hr_stats(symbol))
            elif path == "/api/klines":
                symbol = get_param("symbol", "BTCUSDT")
                interval = get_param("interval", "1h")
                limit = int(get_param("limit", 60))
                self._send_json(client.get_klines(symbol, interval=interval, limit=limit))
            elif path == "/api/depth":
                symbol = get_param("symbol", "BTCUSDT")
                limit = int(get_param("limit", 10))
                self._send_json(client.get_order_book(symbol, limit=limit))
            elif path == "/api/movers":
                limit = int(get_param("limit", 10))
                quote = get_param("quote", "USDT")
                self._send_json(client.get_top_movers(limit=limit, quote_asset=quote))
            elif path == "/api/indicators":
                symbol = get_param("symbol", "BTCUSDT")
                interval = get_param("interval", "1h")
                min_score = float(get_param("min_score", 60))
                klines = client.get_klines(symbol, interval=interval, limit=60)
                res = detect_breakouts(klines, donchian_period=20, volume_period=20)
                cleaned_res = clean_numpy_for_json(res)
                cleaned_res["klines"] = klines
                # Attach latest-bar reasoning to the response
                try:
                    engine = BreakthroughReasoningEngine(min_score=min_score)
                    reasoning_latest = engine.analyze_latest(klines)
                    cleaned_res["reasoning"] = clean_numpy_for_json(reasoning_latest)
                except Exception:
                    cleaned_res["reasoning"] = None
                self._send_json(cleaned_res)
            elif path == "/api/reasoning":
                symbol = get_param("symbol", "BTCUSDT")
                interval = get_param("interval", "1h")
                limit = int(get_param("limit", 60))
                min_score = float(get_param("min_score", 60))
                klines = client.get_klines(symbol, interval=interval, limit=limit)
                engine = BreakthroughReasoningEngine(min_score=min_score)
                reasoning_bars = engine.analyze(klines)
                # Only send bars that have a non-NONE signal (or all, filtered)
                show_all = get_param("show_all", "false").lower() == "true"
                if not show_all:
                    reasoning_bars = [r for r in reasoning_bars if r["signal"] != "NONE"]
                self._send_json(clean_numpy_for_json({
                    "symbol": symbol.upper(),
                    "interval": interval,
                    "min_score": min_score,
                    "count": len(reasoning_bars),
                    "bars": reasoning_bars,
                }))
            else:
                self._send_json({"error": "Endpoint not found"}, status=404)
        except BinanceAPIError as e:
            self._send_json({"error": e.msg, "code": e.code}, status=e.status_code or 400)
        except Exception as e:
            self._send_json({"error": str(e)}, status=500)

    def log_message(self, format, *args):
        # Suppress noisy HTTP request logging in stdout
        pass


def run_server(port: int = 5001):
    server_address = ("", port)
    httpd = HTTPServer(server_address, DashboardRequestHandler)
    print(f"[SERVER] Binance Public Dashboard Server running at http://localhost:{port}")
    print("Press Ctrl+C to stop.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")


if __name__ == "__main__":
    port = 5001
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            pass
    run_server(port)
