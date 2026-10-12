"""Build a self-contained HTML navigator for the 35 trades of the
`atas_calibrated_inside_1r` control (the 54.29% WR run reported by Codex).

The page is meant to be used side by side with ATAS replay: for every trade it
shows the session date, the signal candle, the exact levels (OR, entry, stop,
target, imbalance rows) and the realised outcome, so each case can be located
and visually verified on the platform.

Usage:
    python build_inside_control_navigator.py
"""

from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path

SRC = Path(
    r"C:/Users/k_99_/Documents/ChatGPT/research_edge/outputs"
    r"/calibrated_inside_control_v1/trades.csv"
)
OUT = Path(__file__).resolve().parent.parent / "notes_md_claude" / "inside_control_navigator.html"

TICK = 0.25
MONTHS_ES = {
    1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril", 5: "Mayo", 6: "Junio",
    7: "Julio", 8: "Agosto", 9: "Septiembre", 10: "Octubre", 11: "Noviembre",
    12: "Diciembre",
}


def f(row: dict, key: str, default=None):
    """Float accessor tolerant to empty cells."""
    raw = row.get(key, "")
    if raw in ("", None):
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def b(row: dict, key: str) -> bool:
    return str(row.get(key, "")).strip().lower() == "true"


def ny_time(iso: str) -> str:
    """09:36:00 from a full ISO timestamp already expressed in NY offset."""
    if not iso:
        return ""
    try:
        return datetime.fromisoformat(iso).strftime("%H:%M:%S")
    except ValueError:
        return iso[11:19]


def utc_to_ny_clock(iso: str) -> str:
    """Databento stamps are UTC; the sessions are all EDT (UTC-4)."""
    if not iso:
        return ""
    head = iso[:26]
    try:
        dt = datetime.fromisoformat(head.replace("+00:00", ""))
    except ValueError:
        return ""
    hour = (dt.hour - 4) % 24
    return f"{hour:02d}:{dt.minute:02d}:{dt.second:02d}.{dt.microsecond // 1000:03d}"


def build_trades() -> list[dict]:
    rows = list(csv.DictReader(SRC.open(encoding="utf-8")))
    trades = []
    for row in rows:
        direction = int(row["direction"])
        session = row["session"]
        date = datetime.fromisoformat(session)
        imbalances = json.loads(row["all_aligned_rows"] or "[]")

        entry = f(row, "entry")
        stop = f(row, "stop")
        target = f(row, "target")
        exit_px = f(row, "exit")

        trades.append({
            "n": int(row["trade_number"]),
            "session": session,
            "month": f"{MONTHS_ES[date.month]} {date.year}",
            "month_key": f"{date.year}-{date.month:02d}",
            "weekday": ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"][date.weekday()],
            "dir": direction,
            "dir_label": "LARGO" if direction > 0 else "CORTO",
            # Signal candle: ATAS navigation target.
            "candle_start": ny_time(row["candle_start"]),
            "signal_close": ny_time(row["signal_close"]),
            "minute": row["minute"],
            "o": f(row, "open"), "h": f(row, "high"),
            "l": f(row, "low"), "c": f(row, "close"),
            "raw_o": f(row, "raw_open"), "raw_h": f(row, "raw_high"),
            "raw_l": f(row, "raw_low"), "raw_c": f(row, "raw_close"),
            "volume": f(row, "volume"),
            "or_high": f(row, "or_high"), "or_low": f(row, "or_low"),
            "vwap": f(row, "vwap"), "prev_vwap": f(row, "previous_vwap"),
            "vwap_slope": f(row, "vwap_slope"),
            # Orders.
            "entry": entry, "stop": stop, "target": target, "exit": exit_px,
            "entry_clock": utc_to_ny_clock(row["entry_ts"]),
            "exit_clock": utc_to_ny_clock(row["exit_ts"]),
            "entry_print": f(row, "entry_print"),
            "exit_print": f(row, "exit_print"),
            "risk": f(row, "risk_ticks"),
            # Footprint.
            "imbalances": imbalances,
            "imb_count": int(f(row, "imbalance_count", 0) or 0),
            "imb_label": f(row, "imbalance_label_price"),
            "imb_lo": f(row, "imbalance_row_lo"),
            "imb_hi": f(row, "imbalance_row_hi"),
            "imb_vol": f(row, "imbalance_volume"),
            "imb_ref": f(row, "imbalance_reference"),
            "imb_ratio": f(row, "imbalance_ratio"),
            # Outcome.
            "result": row["exit_reason"].upper(),
            "net_ticks": f(row, "net_ticks"),
            "net_r": f(row, "net_r"),
            "net_usd": f(row, "net_usd_one_nq"),
            "mae": f(row, "mae_ticks"), "mfe": f(row, "mfe_ticks"),
            "duration": f(row, "duration_seconds"),
            # Provenance and warnings.
            "source": row["source_kind"],
            "atas_source": row["source_kind"] == "atas_archived",
            "print_at_stop": b(row, "entry_print_at_or_beyond_stop"),
            "grouped_mismatch": (
                f(row, "raw_close") != f(row, "reconstructed_close_grouped")
                or f(row, "raw_high") != f(row, "reconstructed_high_grouped")
                or f(row, "raw_low") != f(row, "reconstructed_low_grouped")
            ),
        })
    trades.sort(key=lambda t: t["session"])
    return trades


HTML = r"""<!doctype html>
<html lang="es-MX">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Navegador Control Inside OR</title>
<style>
:root {
  --bg: #0f1115; --panel: #171a21; --panel-2: #1e222b; --line: #2b313d;
  --text: #e6e9ef; --muted: #98a1b3; --accent: #6ea8fe;
  --up: #3fb950; --down: #f85149; --warn: #d29922;
  --or: #8b5cf6; --vwap: #e3b341;
  --mono: ui-monospace, "Cascadia Mono", "SF Mono", Consolas, monospace;
}
:root[data-theme="light"] {
  --bg: #f6f7f9; --panel: #ffffff; --panel-2: #f0f2f5; --line: #d8dde5;
  --text: #15181d; --muted: #5a6476; --accent: #1f6feb;
  --up: #1a7f37; --down: #cf222e; --warn: #9a6700;
}
* { box-sizing: border-box; }
body {
  margin: 0; background: var(--bg); color: var(--text);
  font: 14px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif;
}
header {
  padding: 16px; border-bottom: 1px solid var(--line);
  display: flex; flex-wrap: wrap; gap: 12px; align-items: center;
  background: var(--panel); position: sticky; top: 0; z-index: 10;
}
h1 { font-size: 17px; margin: 0; font-weight: 650; letter-spacing: -0.01em; }
.sub { color: var(--muted); font-size: 12px; }
.spacer { flex: 1; }
.kpis { display: flex; gap: 14px; flex-wrap: wrap; }
.kpi { background: var(--panel-2); border: 1px solid var(--line); border-radius: 8px; padding: 6px 11px; }
.kpi b { display: block; font-size: 15px; font-variant-numeric: tabular-nums; }
.kpi span { font-size: 10.5px; color: var(--muted); text-transform: uppercase; letter-spacing: .05em; }
.wrap { display: grid; grid-template-columns: minmax(380px, 1fr) minmax(420px, 1.05fr); gap: 0; }
@media (max-width: 1000px) { .wrap { grid-template-columns: 1fr; } }
.left { border-right: 1px solid var(--line); min-width: 0; }
.right { padding: 16px; min-width: 0; }
.filters { padding: 10px 16px; display: flex; gap: 6px; flex-wrap: wrap; border-bottom: 1px solid var(--line); }
button.f, select {
  background: var(--panel-2); color: var(--text); border: 1px solid var(--line);
  border-radius: 6px; padding: 5px 10px; font-size: 12px; cursor: pointer; font-family: inherit;
}
button.f.on { background: var(--accent); border-color: var(--accent); color: #fff; }
table { width: 100%; border-collapse: collapse; font-size: 12.5px; }
th {
  text-align: left; padding: 7px 10px; color: var(--muted); font-weight: 600;
  font-size: 10.5px; text-transform: uppercase; letter-spacing: .05em;
  border-bottom: 1px solid var(--line); position: sticky; top: 0; background: var(--panel);
}
td { padding: 6px 10px; border-bottom: 1px solid var(--line); font-variant-numeric: tabular-nums; }
tbody tr { cursor: pointer; }
tbody tr:hover { background: var(--panel-2); }
tbody tr.sel { background: color-mix(in srgb, var(--accent) 18%, transparent); }
.num { text-align: right; }
.mono { font-family: var(--mono); }
.tp { color: var(--up); font-weight: 600; }
.sl { color: var(--down); font-weight: 600; }
.long { color: var(--up); } .short { color: var(--down); }
.tag {
  display: inline-block; padding: 1px 6px; border-radius: 4px; font-size: 10px;
  border: 1px solid var(--line); background: var(--panel-2); color: var(--muted);
}
.tag.warn { color: var(--warn); border-color: var(--warn); }
.tag.atas { color: var(--accent); border-color: var(--accent); }
.card { background: var(--panel); border: 1px solid var(--line); border-radius: 10px; padding: 14px; margin-bottom: 12px; }
.card h3 { margin: 0 0 10px; font-size: 12px; text-transform: uppercase; letter-spacing: .06em; color: var(--muted); font-weight: 650; }
.grid2 { display: grid; grid-template-columns: repeat(auto-fit, minmax(135px, 1fr)); gap: 10px; }
.field span { display: block; font-size: 10.5px; color: var(--muted); text-transform: uppercase; letter-spacing: .04em; }
.field b { font-family: var(--mono); font-size: 14px; font-weight: 600; }
.navbox { background: var(--panel-2); border: 1px dashed var(--accent); border-radius: 8px; padding: 12px; }
.navbox .big { font-family: var(--mono); font-size: 19px; font-weight: 650; letter-spacing: -0.01em; }
.copy { background: var(--accent); color: #fff; border: 0; border-radius: 6px; padding: 5px 11px; font-size: 11.5px; cursor: pointer; font-family: inherit; }
table.inner { font-size: 12px; }
table.inner th { position: static; background: transparent; }
svg { display: block; width: 100%; height: auto; }
.legend { display: flex; gap: 12px; flex-wrap: wrap; font-size: 11px; color: var(--muted); margin-top: 8px; }
.legend i { display: inline-block; width: 14px; height: 2px; vertical-align: middle; margin-right: 4px; }
.empty { padding: 40px 16px; text-align: center; color: var(--muted); }
.note { font-size: 11.5px; color: var(--muted); margin-top: 8px; line-height: 1.5; }
.warnbox { border-color: var(--warn); }
.warnbox h3 { color: var(--warn); }
</style>
</head>
<body>
<header>
  <div>
    <h1>Control &ldquo;apertura dentro del OR&rdquo; &mdash; 35 operaciones</h1>
    <div class="sub">Run <code>calibrated_inside_control_v1</code> &middot; NQ &middot; 9 Mar &ndash; 9 Oct 2026 &middot; RR 1:1 &middot; horas de Nueva York (EDT)</div>
  </div>
  <div class="spacer"></div>
  <div class="kpis">
    <div class="kpi"><b>35</b><span>Trades</span></div>
    <div class="kpi"><b>54.29%</b><span>WR</span></div>
    <div class="kpi"><b>1.382</b><span>PF 1 NQ</span></div>
    <div class="kpi"><b>0.959</b><span>PF en R</span></div>
    <div class="kpi"><b>+$1,515</b><span>Neto 1 NQ</span></div>
    <div class="kpi"><b>&minus;0.79R</b><span>Neto en R</span></div>
  </div>
  <button class="f" id="theme">Tema</button>
</header>

<div class="wrap">
  <div class="left">
    <div class="filters">
      <button class="f on" data-k="all">Todas (35)</button>
      <button class="f" data-k="tp">Solo TP (19)</button>
      <button class="f" data-k="sl">Solo SL (16)</button>
      <button class="f" data-k="long">Largos (19)</button>
      <button class="f" data-k="short">Cortos (16)</button>
      <select id="month"><option value="">Todos los meses</option></select>
    </div>
    <table>
      <thead><tr>
        <th>#</th><th>Sesión</th><th>Vela</th><th>Dir</th>
        <th class="num">Riesgo</th><th>Salida</th><th class="num">Ticks</th><th class="num">R</th>
      </tr></thead>
      <tbody id="rows"></tbody>
    </table>
    <div class="empty" id="empty" hidden>Sin operaciones con este filtro.</div>
  </div>
  <div class="right" id="detail"></div>
</div>

<script>
const TRADES = __DATA__;
const fx = (v, d = 2) => v === null || v === undefined ? "&mdash;" : v.toFixed(d);
const px = v => v === null || v === undefined ? "&mdash;" : v.toFixed(2);
let filter = "all", month = "", selected = TRADES[0].n;

function visible() {
  return TRADES.filter(t => {
    if (month && t.month_key !== month) return false;
    if (filter === "tp") return t.result === "TP";
    if (filter === "sl") return t.result === "SL";
    if (filter === "long") return t.dir > 0;
    if (filter === "short") return t.dir < 0;
    return true;
  });
}

function renderList() {
  const list = visible();
  document.getElementById("empty").hidden = list.length > 0;
  document.getElementById("rows").innerHTML = list.map(t => `
    <tr data-n="${t.n}" class="${t.n === selected ? "sel" : ""}">
      <td class="mono">${t.n}</td>
      <td class="mono">${t.session}</td>
      <td class="mono">${t.minute}</td>
      <td class="${t.dir > 0 ? "long" : "short"}">${t.dir > 0 ? "▲ L" : "▼ C"}</td>
      <td class="num mono">${fx(t.risk, 0)}t</td>
      <td class="${t.result.toLowerCase()}">${t.result}</td>
      <td class="num mono ${t.net_ticks > 0 ? "tp" : "sl"}">${t.net_ticks > 0 ? "+" : ""}${fx(t.net_ticks, 1)}</td>
      <td class="num mono ${t.net_r > 0 ? "tp" : "sl"}">${t.net_r > 0 ? "+" : ""}${fx(t.net_r, 2)}</td>
    </tr>`).join("");
  document.querySelectorAll("#rows tr").forEach(tr => {
    tr.onclick = () => { selected = +tr.dataset.n; renderList(); renderDetail(); };
  });
}

/* Vertical price ladder: OR band, signal candle, orders and imbalance rows. */
function ladder(t) {
  const vals = [t.h, t.l, t.or_high, t.or_low, t.entry, t.stop, t.target, t.exit, t.vwap]
    .filter(v => v !== null);
  t.imbalances.forEach(i => { vals.push(i.row_lo, i.row_hi); });
  let hi = Math.max(...vals), lo = Math.min(...vals);
  const pad = (hi - lo) * 0.10 || 1;
  hi += pad; lo -= pad;
  const W = 460, H = 330, L = 118, R = 74;
  const y = p => H - 18 - ((p - lo) / (hi - lo)) * (H - 36);
  const lbl = (p, text, color, dash = "") => `
    <line x1="${L}" x2="${W - R}" y1="${y(p).toFixed(1)}" y2="${y(p).toFixed(1)}"
          stroke="${color}" stroke-width="1.4" ${dash ? `stroke-dasharray="${dash}"` : ""}/>
    <text x="${L - 7}" y="${(y(p) + 3.5).toFixed(1)}" fill="${color}" font-size="10.5"
          text-anchor="end" font-family="var(--mono)">${text}</text>
    <text x="${W - R + 6}" y="${(y(p) + 3.5).toFixed(1)}" fill="${color}" font-size="10.5"
          font-family="var(--mono)">${p.toFixed(2)}</text>`;

  // OR band.
  const orTop = y(t.or_high), orBot = y(t.or_low);
  let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Escalera de precios de la operación">
    <rect x="${L}" y="${orTop.toFixed(1)}" width="${W - L - R}" height="${(orBot - orTop).toFixed(1)}"
          fill="var(--or)" opacity="0.13"/>`;
  s += lbl(t.or_high, "OR high", "var(--or)", "4 3");
  s += lbl(t.or_low, "OR low", "var(--or)", "4 3");

  // Imbalance rows (5-tick bands) drawn as blocks.
  t.imbalances.forEach((i, k) => {
    const top = y(i.row_hi), bot = y(i.row_lo);
    s += `<rect x="${L + 6}" y="${top.toFixed(1)}" width="${(W - L - R - 12).toFixed(1)}"
            height="${Math.max(bot - top, 3).toFixed(1)}"
            fill="${t.dir > 0 ? "var(--up)" : "var(--down)"}" opacity="0.22"/>
          <text x="${L + 12}" y="${(top + Math.max(bot - top, 10) / 2 + 3.5).toFixed(1)}"
            font-size="9.5" fill="var(--muted)" font-family="var(--mono)">imb ${k + 1} · ${i.volume}×${i.reference} · ${i.ratio_infinite ? "∞" : i.ratio.toFixed(1)}</text>`;
  });

  // Signal candle body + wicks, centred.
  const cx = (L + W - R) / 2, bw = 26;
  const bodyTop = y(Math.max(t.o, t.c)), bodyBot = y(Math.min(t.o, t.c));
  const col = t.c >= t.o ? "var(--up)" : "var(--down)";
  s += `<line x1="${cx}" x2="${cx}" y1="${y(t.h).toFixed(1)}" y2="${y(t.l).toFixed(1)}" stroke="${col}" stroke-width="1.6"/>
        <rect x="${cx - bw / 2}" y="${bodyTop.toFixed(1)}" width="${bw}"
              height="${Math.max(bodyBot - bodyTop, 2).toFixed(1)}" fill="${col}"/>`;

  s += lbl(t.vwap, "VWAP", "var(--vwap)", "2 3");
  s += lbl(t.stop, "SL", "var(--down)");
  s += lbl(t.target, "TP", "var(--up)");
  s += lbl(t.entry, "Entrada", "var(--accent)");
  s += `</svg>`;
  return s;
}

function renderDetail() {
  const t = TRADES.find(x => x.n === selected);
  const warn = [];
  if (t.print_at_stop) warn.push("El primer print de entrada ya está en o más allá del SL: no ejecutable tal cual.");
  if (t.risk <= 5) warn.push(`Riesgo de ${t.risk} ticks: demasiado fino para ser ejecutable en NQ.`);
  if (t.grouped_mismatch) warn.push("OHLC nativo distinto del agrupado ceil-5: ATAS y Databento pueden dibujar la vela distinta.");

  document.getElementById("detail").innerHTML = `
    <div class="card">
      <h3>Dónde buscarlo en ATAS</h3>
      <div class="navbox">
        <div class="big">${t.session} &middot; ${t.minute} NY</div>
        <div class="sub" style="margin:6px 0 10px">
          ${t.weekday} &middot; vela M1 que abre ${t.candle_start} y cierra ${t.signal_close} &middot;
          señal ${t.dir > 0 ? "<span class='long'>LARGA</span>" : "<span class='short'>CORTA</span>"}
        </div>
        <button class="copy" data-copy="${t.session} ${t.minute}">Copiar fecha y minuto</button>
        <span class="tag ${t.atas_source ? "atas" : ""}">${t.atas_source ? "footprint desde export ATAS" : "footprint reconstruido Databento"}</span>
      </div>
      <div class="note">
        Poner el replay en <b>${t.session}</b>, gráfico M1 de NQ, e ir a la vela de las <b>${t.minute}</b>.
        El OR es la vela 09:30&ndash;09:31. La entrada simulada ocurre al primer print tras el cierre,
        a las <b>${t.entry_clock}</b>; la salida, a las <b>${t.exit_clock}</b>
        (${t.duration < 60 ? fx(t.duration, 1) + " s" : fx(t.duration / 60, 1) + " min"} después).
      </div>
    </div>

    <div class="card">
      <h3>Niveles a verificar</h3>
      <div class="grid2">
        <div class="field"><span>OR high</span><b>${px(t.or_high)}</b></div>
        <div class="field"><span>OR low</span><b>${px(t.or_low)}</b></div>
        <div class="field"><span>Entrada</span><b style="color:var(--accent)">${px(t.entry)}</b></div>
        <div class="field"><span>Stop</span><b style="color:var(--down)">${px(t.stop)}</b></div>
        <div class="field"><span>Target</span><b style="color:var(--up)">${px(t.target)}</b></div>
        <div class="field"><span>Salida real</span><b>${px(t.exit)}</b></div>
        <div class="field"><span>Riesgo</span><b>${fx(t.risk, 0)} ticks</b></div>
        <div class="field"><span>VWAP al cierre</span><b style="color:var(--vwap)">${px(t.vwap)}</b></div>
      </div>
    </div>

    <div class="card">
      <h3>Geometría de la operación</h3>
      ${ladder(t)}
      <div class="legend">
        <span><i style="background:var(--or)"></i>Opening Range</span>
        <span><i style="background:var(--accent)"></i>Entrada</span>
        <span><i style="background:var(--down)"></i>Stop</span>
        <span><i style="background:var(--up)"></i>Target</span>
        <span><i style="background:var(--vwap)"></i>VWAP</span>
        <span>Bloque sombreado = fila de imbalance (5 ticks)</span>
      </div>
    </div>

    <div class="card">
      <h3>Vela de señal (M1 ${t.minute})</h3>
      <table class="inner">
        <tr><th></th><th class="num">Open</th><th class="num">High</th><th class="num">Low</th><th class="num">Close</th></tr>
        <tr><td>Agrupado ceil-5 (motor)</td><td class="num mono">${px(t.o)}</td><td class="num mono">${px(t.h)}</td><td class="num mono">${px(t.l)}</td><td class="num mono">${px(t.c)}</td></tr>
        <tr><td>Nativo Databento</td><td class="num mono">${px(t.raw_o)}</td><td class="num mono">${px(t.raw_h)}</td><td class="num mono">${px(t.raw_l)}</td><td class="num mono">${px(t.raw_c)}</td></tr>
      </table>
      <div class="note">
        Volumen ${fx(t.volume, 0)} &middot; VWAP previa ${px(t.prev_vwap)} &rarr; actual ${px(t.vwap)}
        (pendiente ${t.vwap_slope > 0 ? "+" : ""}${fx(t.vwap_slope, 2)} puntos/min, ${t.vwap_slope > 0 ? "al alza" : "a la baja"}).
        El motor usa la rejilla agrupada, igual que el export de ATAS: cada etiqueta es el tick
        superior de un intervalo de 5 ticks.
      </div>
    </div>

    <div class="card">
      <h3>Imbalances alineados (${t.imb_count})</h3>
      <table class="inner">
        <tr><th>#</th><th class="num">Etiqueta</th><th>Fila (5t)</th><th class="num">Volumen</th><th class="num">Referencia</th><th class="num">Ratio</th><th></th></tr>
        ${t.imbalances.map((i, k) => `
          <tr>
            <td>${k + 1}</td>
            <td class="num mono">${i.label_price.toFixed(2)}</td>
            <td class="mono">${i.row_lo.toFixed(2)}&ndash;${i.row_hi.toFixed(2)}</td>
            <td class="num mono">${i.volume}</td>
            <td class="num mono">${i.reference}</td>
            <td class="num mono">${i.ratio_infinite ? "&infin;" : i.ratio.toFixed(2)}</td>
            <td>${i.label_price === t.imb_label ? '<span class="tag">define el SL</span>' : ""}</td>
          </tr>`).join("")}
      </table>
      <div class="note">
        Comparación diagonal: ${t.dir > 0
          ? "compra = ask de la fila contra bid de la fila inferior"
          : "venta = bid de la fila contra ask de la fila superior"}.
        Ratio exigido &gt; 3.0, volumen mínimo 70. El SL va 5 ticks detrás de la fila alineada
        más lejana al precio.
      </div>
    </div>

    <div class="card">
      <h3>Resultado</h3>
      <div class="grid2">
        <div class="field"><span>Salida</span><b class="${t.result.toLowerCase()}">${t.result}</b></div>
        <div class="field"><span>Ticks netos</span><b class="${t.net_ticks > 0 ? "tp" : "sl"}">${t.net_ticks > 0 ? "+" : ""}${fx(t.net_ticks, 1)}</b></div>
        <div class="field"><span>R neto</span><b class="${t.net_r > 0 ? "tp" : "sl"}">${t.net_r > 0 ? "+" : ""}${fx(t.net_r, 3)}</b></div>
        <div class="field"><span>USD 1 NQ</span><b class="${t.net_usd > 0 ? "tp" : "sl"}">${t.net_usd > 0 ? "+" : ""}${fx(t.net_usd, 0)}</b></div>
        <div class="field"><span>MAE</span><b>${fx(t.mae, 0)} ticks</b></div>
        <div class="field"><span>MFE</span><b>${fx(t.mfe, 0)} ticks</b></div>
      </div>
      <div class="note">Costes incluidos: 1 tick adverso en entrada, 1 tick adverso más overshoot en SL, USD 4 round-trip (0.8 ticks).</div>
    </div>

    ${warn.length ? `<div class="card warnbox"><h3>Advertencias de ejecución</h3>
      <ul style="margin:0;padding-left:18px">${warn.map(w => `<li>${w}</li>`).join("")}</ul></div>` : ""}
  `;
  const btn = document.querySelector("[data-copy]");
  if (btn) btn.onclick = () => {
    navigator.clipboard.writeText(btn.dataset.copy).then(
      () => { btn.textContent = "Copiado"; setTimeout(() => btn.textContent = "Copiar fecha y minuto", 1200); },
      () => { btn.textContent = "No se pudo copiar"; }
    );
  };
}

// Filters.
document.querySelectorAll("button.f[data-k]").forEach(btn => {
  btn.onclick = () => {
    document.querySelectorAll("button.f[data-k]").forEach(x => x.classList.remove("on"));
    btn.classList.add("on");
    filter = btn.dataset.k;
    const list = visible();
    if (list.length && !list.some(t => t.n === selected)) selected = list[0].n;
    renderList(); renderDetail();
  };
});
const sel = document.getElementById("month");
[...new Set(TRADES.map(t => t.month_key))].sort().forEach(k => {
  const t = TRADES.find(x => x.month_key === k);
  sel.insertAdjacentHTML("beforeend", `<option value="${k}">${t.month}</option>`);
});
sel.onchange = () => {
  month = sel.value;
  const list = visible();
  if (list.length && !list.some(t => t.n === selected)) selected = list[0].n;
  renderList(); renderDetail();
};

// Theme toggle and keyboard navigation.
document.getElementById("theme").onclick = () => {
  const cur = document.documentElement.dataset.theme;
  document.documentElement.dataset.theme = cur === "light" ? "dark" : "light";
};
document.onkeydown = e => {
  if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
  const list = visible(), i = list.findIndex(t => t.n === selected);
  const next = e.key === "ArrowDown" ? Math.min(i + 1, list.length - 1) : Math.max(i - 1, 0);
  selected = list[next].n; renderList(); renderDetail();
  e.preventDefault();
};

renderList(); renderDetail();
</script>
</body>
</html>
"""


def main() -> None:
    trades = build_trades()
    html = HTML.replace("__DATA__", json.dumps(trades, ensure_ascii=False))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(html, encoding="utf-8")
    wins = sum(1 for t in trades if t["net_ticks"] > 0)
    print(f"trades: {len(trades)} | TP: {wins} | WR: {wins / len(trades):.2%}")
    print(f"net USD 1 NQ: {sum(t['net_usd'] for t in trades):+.0f}")
    print(f"net R: {sum(t['net_r'] for t in trades):+.4f}")
    print(f"written: {OUT}  ({OUT.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
