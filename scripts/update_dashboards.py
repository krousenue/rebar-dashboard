"""
update_dashboards.py
Fetches latest rebar market indicator data from free public APIs and
rewrites both dashboard HTML files in /docs for GitHub Pages hosting.

APIs used (all free, no key required unless noted):
  - FRED (St. Louis Fed) — housing, treasury, PMI  [requires free API key]
  - EIA  (US Energy Info Admin)                    [requires free API key]
  - BLS  (Bureau of Labor Statistics)              [no key required]
  - NASDAQ Data Link / Quandl Steel futures        [requires free API key]

Keys are stored as GitHub Actions secrets (never hardcoded).
"""

import os
import json
import datetime
import requests

# ── API keys from environment (set as GitHub Actions secrets) ─────────────────
FRED_KEY  = os.environ.get("FRED_API_KEY", "")
EIA_KEY   = os.environ.get("EIA_API_KEY", "")

TODAY     = datetime.date.today().strftime("%b %d, %Y")

# ── Helper ────────────────────────────────────────────────────────────────────
def fred(series_id, n=1):
    """Fetch latest n observations from FRED."""
    try:
        url = (
            f"https://api.stlouisfed.org/fred/series/observations"
            f"?series_id={series_id}&api_key={FRED_KEY}&file_type=json"
            f"&sort_order=desc&limit={n}"
        )
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        obs = r.json().get("observations", [])
        vals = [o["value"] for o in obs if o["value"] != "."]
        return vals
    except Exception as e:
        print(f"  FRED {series_id} error: {e}")
        return []

def eia(route):
    """Fetch from EIA API v2."""
    try:
        url = f"https://api.eia.gov/v2/{route}&api_key={EIA_KEY}"
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"  EIA error: {e}")
        return {}

def fmt_pct(val, decimals=1):
    return f"{float(val):.{decimals}f}%"

def fmt_dollar(val, decimals=0):
    return f"${float(val):,.{decimals}f}"

def fmt_m(val):
    """Format as millions with 2 decimal places."""
    return f"{float(val)/1000:.2f}M"

def signal(val, bull_above=None, bear_below=None, neutral_range=None):
    """Return bull/bear/neutral based on thresholds."""
    v = float(val)
    if bull_above is not None and v > bull_above:
        return "bull"
    if bear_below is not None and v < bear_below:
        return "bear"
    return "neutral"

# ── Fetch all data ─────────────────────────────────────────────────────────────
print("Fetching data...")

# Housing starts (HOUST) — thousands of units, annualized
houst = fred("HOUST")
houst_val  = fmt_m(float(houst[0])*1000) if houst else "N/A"
houst_prev = fmt_m(float(houst[1])*1000) if len(houst) > 1 else None
houst_chg  = f"{((float(houst[0])-float(houst[1]))/float(houst[1])*100):+.1f}% MoM" if len(houst)>1 else "—"
houst_sig  = signal(houst[0], bear_below=1350) if houst else "neutral"

# Building permits (PERMIT) — thousands, annualized
permit = fred("PERMIT")
permit_val = fmt_m(float(permit[0])*1000) if permit else "N/A"
permit_chg = f"{((float(permit[0])-float(permit[1]))/float(permit[1])*100):+.1f}% MoM" if len(permit)>1 else "—"
permit_sig = signal(permit[0], bull_above=1400, bear_below=1300) if permit else "neutral"

# 10-Year Treasury (DGS10)
tsy = fred("DGS10")
tsy_val    = fmt_pct(tsy[0]) if tsy else "N/A"
tsy_chg    = f"{(float(tsy[0])-float(tsy[1]))*100:+.0f} bps WoW" if len(tsy)>1 else "—"
tsy_sig    = "bull" if tsy and float(tsy[0]) < 4.5 else "bear"

# ISM Manufacturing PMI (MANEMP is employment; use NAPM for PMI composite)
pmi = fred("NAPM")
pmi_val    = f"{float(pmi[0]):.1f}" if pmi else "N/A"
pmi_chg    = f"{float(pmi[0])-float(pmi[1]):+.1f} pts MoM" if len(pmi)>1 else "—"
pmi_sig    = "bull" if pmi and float(pmi[0]) > 50 else "bear"

# Fed Funds Rate (FEDFUNDS)
ffr = fred("FEDFUNDS")
ffr_val    = fmt_pct(ffr[0]) if ffr else "N/A"
ffr_sig    = "bear"  # High rates = bearish for construction demand

# WTI Crude Oil (DCOILWTICO)
wti = fred("DCOILWTICO", n=5)
wti_val    = f"${float(wti[0]):.2f}" if wti else "N/A"
wti_chg    = f"{float(wti[0])-float(wti[-1]):+.2f} WoW" if len(wti)>1 else "—"
wti_sig    = "bull" if wti and float(wti[0]) > 70 else "bear"

# Texas single-family permits (DALL148BP1FH = DFW; TXBPPRIV = statewide)
tx_permits = fred("TXBPPRIV")
tx_p_val   = f"{int(float(tx_permits[0])):,}" if tx_permits else "N/A"
tx_p_chg   = f"{((float(tx_permits[0])-float(tx_permits[1]))/float(tx_permits[1])*100):+.1f}% MoM" if len(tx_permits)>1 else "—"
tx_p_sig   = signal(tx_permits[0], bull_above=12000, bear_below=9000) if tx_permits else "neutral"

print("Data fetch complete.")
print(f"  Housing starts:    {houst_val} ({houst_chg})")
print(f"  Building permits:  {permit_val} ({permit_chg})")
print(f"  10-yr Treasury:    {tsy_val} ({tsy_chg})")
print(f"  ISM PMI:           {pmi_val} ({pmi_chg})")
print(f"  Fed funds rate:    {ffr_val}")
print(f"  WTI crude:         {wti_val} ({wti_chg})")
print(f"  TX permits:        {tx_p_val} ({tx_p_chg})")

# ── Build indicator data structures ──────────────────────────────────────────

GLOBAL_INDICATORS = {
    "demand": [
        {"name": "Housing Starts",   "value": houst_val,  "unit": "ann. rate", "change": f"{'▼' if '-' in houst_chg else '▲'} {houst_chg}", "signal": houst_sig,  "note": "Census Bureau / FRED"},
        {"name": "Building Permits", "value": permit_val, "unit": "ann. rate", "change": f"{'▼' if '-' in permit_chg else '▲'} {permit_chg}", "signal": permit_sig, "note": "Census Bureau / FRED"},
        {"name": "ABI Score",        "value": "48.6",     "unit": "index",     "change": "▼ -0.9 pts",  "signal": "bear",       "note": "Update manually — AIA"},
        {"name": "Dodge Momentum",   "value": "171.3",    "unit": "index",     "change": "▲ +2.4%",     "signal": "bull",       "note": "Update manually — Dodge"},
    ],
    "input": [
        {"name": "HMS #1 Scrap",     "value": "$398",     "unit": "/ton",      "change": "▼ -$12 WoW",  "signal": "bear",       "note": "Update manually — AMM"},
        {"name": "Shredded Scrap",   "value": "$376",     "unit": "/ton",      "change": "▼ -$8 WoW",   "signal": "bear",       "note": "Update manually — AMM"},
        {"name": "Natural Gas",      "value": "$2.14",    "unit": "/MMBtu",    "change": "▲ +$0.06",    "signal": "neutral",    "note": "Update manually — Henry Hub"},
        {"name": "Electricity Cost", "value": "Stable",   "unit": "",          "change": "— flat",       "signal": "neutral",    "note": "Midwest industrial"},
    ],
    "trade": [
        {"name": "SHFE Rebar Futures","value": "¥3,082",  "unit": "/ton",      "change": "▲ +0.4%",     "signal": "bull",       "note": "Update manually — SHFE"},
        {"name": "US Mill Utilization","value": "74.2%",  "unit": "",          "change": "▼ -0.8 pts",  "signal": "bear",       "note": "Update manually — AISI"},
        {"name": "Rebar Imports",    "value": "148K",     "unit": "tons",      "change": "▲ +9% MoM",   "signal": "bear",       "note": "Update manually — Census"},
        {"name": "Mill Lead Times",  "value": "3–4 wks",  "unit": "",          "change": "— flat",       "signal": "neutral",    "note": "EAF mills avg"},
    ],
    "macro": [
        {"name": "10-Yr Treasury",   "value": tsy_val,    "unit": "",          "change": f"{'▼' if '-' in tsy_chg else '▲'} {tsy_chg}", "signal": tsy_sig,    "note": "FRED (DGS10)"},
        {"name": "Fed Funds Rate",   "value": ffr_val,    "unit": "",          "change": "— on hold",    "signal": ffr_sig,      "note": "FRED (FEDFUNDS)"},
        {"name": "ISM Mfg PMI",      "value": pmi_val,    "unit": "index",     "change": f"{'▼' if '-' in pmi_chg else '▲'} {pmi_chg}", "signal": pmi_sig,    "note": "FRED (NAPM)"},
    ],
}

TEXAS_INDICATORS = {
    "demand": [
        {"name": "TX SF Permits (fcst)", "value": "169K",    "unit": "2026 fcst", "change": "▲ +4% vs 2025",  "signal": "bull",    "note": "TRERC forecast"},
        {"name": "TX Statewide Permits", "value": tx_p_val,  "unit": "monthly",   "change": f"{'▼' if '-' in tx_p_chg else '▲'} {tx_p_chg}", "signal": tx_p_sig, "note": "FRED (TXBPPRIV)"},
        {"name": "TX Home Prices",       "value": "$334K",   "unit": "median",    "change": "▲ +1.2% fcst",   "signal": "bull",    "note": "TRERC 2026 est."},
        {"name": "TX Housing Inventory", "value": "Elevated","unit": "",          "change": "▲ rising YoY",   "signal": "bear",    "note": "Affordability drag"},
        {"name": "TX Construction Empl.","value": "+1.8%",   "unit": "fcst YoY", "change": "▲ revised up",   "signal": "bull",    "note": "Dallas Fed May 2026"},
        {"name": "TX Total Job Growth",  "value": "1.2%",    "unit": "2026 fcst", "change": "▲ recovering",   "signal": "neutral", "note": "Dallas Fed lower band"},
    ],
    "infra": [
        {"name": "TxDOT Biennial Budget","value": "$39.9B",  "unit": "FY26–27",   "change": "▲ +6.5% vs prior","signal": "bull",   "note": "SB1 appropriation"},
        {"name": "TxDOT 10-Yr UTP",     "value": "$146B",   "unit": "plan",       "change": "▲ record level",  "signal": "bull",   "note": "2026 UTP adopted"},
        {"name": "TX Water Infra.",      "value": "$1B/yr",  "unit": "dedicated",  "change": "▲ new Prop 4",    "signal": "bull",   "note": "Through 2035"},
        {"name": "Data Center Pipeline", "value": "442",     "unit": "planned/u-c","change": "▲ doubling",      "signal": "bull",   "note": "TX #2 nationally"},
        {"name": "TX Construction Spend","value": "$50B+",   "unit": "annual",     "change": "▲ leads nation",  "signal": "bull",   "note": "2025–2026 pace"},
        {"name": "Material Costs (TX)",  "value": "Volatile","unit": "",           "change": "▲ elevated demand","signal": "bear",  "note": "High-demand squeeze"},
    ],
    "macro": [
        {"name": "WTI Crude Oil",        "value": wti_val,   "unit": "/bbl",       "change": f"{'▼' if '-' in wti_chg else '▲'} {wti_chg}", "signal": wti_sig, "note": "FRED (DCOILWTICO)"},
        {"name": "TX Well Permits",      "value": "Rising",  "unit": "",           "change": "▲ +MoM",          "signal": "bull",   "note": "Update manually — RRC TX"},
        {"name": "TX Leading Index",     "value": "Positive","unit": "3-mo trend", "change": "▲ rose Mar 2026", "signal": "bull",   "note": "Dallas Fed"},
        {"name": "TX Unemployment",      "value": "4.3%",    "unit": "",           "change": "— stable",         "signal": "neutral","note": "BLS / Dallas Fed"},
        {"name": "TX Business Sentiment","value": "Moderating","unit": "",         "change": "▼ geopolitical risk","signal": "bear", "note": "TBOS Apr 2026"},
        {"name": "USMCA Trade Risk",     "value": "Elevated","unit": "",           "change": "▼ review pending", "signal": "bear",  "note": "Cross-border impact"},
    ],
}

METRO_DATA = [
    {"name": "Dallas / Fort Worth", "outlook": "bull",    "permits": "Leading TX", "permits_cls": "bull",  "price": "-4.1%",  "price_cls": "bear",   "trend": "▲ Bullish",  "trend_cls": "bull",   "note": "Tarrant Co. surge; infra-driven"},
    {"name": "Houston",             "outlook": "bull",    "permits": "Stable",     "permits_cls": "bull",  "price": "+0.4%",  "price_cls": "bull",   "trend": "▲ Bullish",  "trend_cls": "bull",   "note": "Industrial + energy activity"},
    {"name": "Austin",              "outlook": "bear",    "permits": "Slowing",    "permits_cls": "bear",  "price": "-2.5%",  "price_cls": "bear",   "trend": "▼ Bearish",  "trend_cls": "bear",   "note": "Oversupply working off"},
    {"name": "San Antonio",         "outlook": "neutral", "permits": "Mixed",      "permits_cls": "neutral","price": "-1.8%", "price_cls": "bear",   "trend": "— Neutral",  "trend_cls": "neutral","note": "Entry-level inventory overhang"},
]

# ── Shared CSS + JS template ──────────────────────────────────────────────────

SHARED_STYLE = """
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  :root {
    --bg: #0f1117; --bg2: #161b26; --bg3: #1e2535;
    --border: rgba(255,255,255,0.08); --border2: rgba(255,255,255,0.14);
    --text: #e8eaf0; --text2: #8b92a8; --text3: #555e75;
    --bull: #3ecf8e; --bull-bg: rgba(62,207,142,0.10); --bull-border: rgba(62,207,142,0.25);
    --bear: #f26b6b; --bear-bg: rgba(242,107,107,0.10); --bear-border: rgba(242,107,107,0.25);
    --neutral: #8b92a8; --neutral-bg: rgba(139,146,168,0.10);
    --radius: 10px; --radius-sm: 6px;
  }
  body { background:var(--bg); color:var(--text); font-family:'DM Sans',sans-serif; font-size:14px; line-height:1.5; min-height:100vh; padding:2rem 1.5rem 3rem; }
  .page { max-width:1100px; margin:0 auto; }
  .header { display:flex; align-items:flex-start; justify-content:space-between; flex-wrap:wrap; gap:1rem; margin-bottom:1.75rem; padding-bottom:1.25rem; border-bottom:1px solid var(--border); }
  .header-left h1 { font-size:22px; font-weight:600; letter-spacing:-0.3px; margin-bottom:4px; display:flex; align-items:center; gap:10px; }
  .header-left p { font-size:13px; color:var(--text2); }
  .badge { font-size:11px; font-weight:500; padding:4px 10px; border-radius:20px; border:1px solid var(--border2); color:var(--text2); background:var(--bg2); font-family:'DM Mono',monospace; }
  .tx-badge { font-size:11px; font-weight:600; padding:3px 10px; border-radius:20px; background:rgba(245,166,35,0.12); border:1px solid rgba(245,166,35,0.3); color:#f5a623; letter-spacing:0.05em; }
  .summary-bar { display:flex; background:var(--bg2); border:1px solid var(--border); border-radius:var(--radius); margin-bottom:1.75rem; overflow:hidden; }
  .summary-item { flex:1; display:flex; flex-direction:column; align-items:center; padding:1rem; gap:4px; border-right:1px solid var(--border); }
  .summary-item:last-child { border-right:none; }
  .summary-count { font-size:26px; font-weight:600; font-family:'DM Mono',monospace; letter-spacing:-1px; }
  .summary-count.bull { color:var(--bull); } .summary-count.bear { color:var(--bear); } .summary-count.neutral { color:var(--neutral); }
  .summary-count.verdict { font-size:15px; letter-spacing:-0.3px; font-family:'DM Sans',sans-serif; text-align:center; line-height:1.3; }
  .summary-label { font-size:11px; color:var(--text3); text-transform:uppercase; letter-spacing:0.07em; font-weight:500; }
  .section-label { font-size:10px; font-weight:600; text-transform:uppercase; letter-spacing:0.1em; color:var(--text3); margin:1.75rem 0 0.75rem; display:flex; align-items:center; gap:8px; }
  .section-label::after { content:''; flex:1; height:1px; background:var(--border); }
  .cards-grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(210px,1fr)); gap:10px; }
  .ind-card { background:var(--bg2); border:1px solid var(--border); border-radius:var(--radius); padding:14px 16px; display:flex; flex-direction:column; gap:6px; transition:border-color 0.15s; }
  .ind-card:hover { border-color:var(--border2); }
  .ind-card.bull { border-left:2px solid var(--bull); } .ind-card.bear { border-left:2px solid var(--bear); } .ind-card.neutral { border-left:2px solid #3a4259; }
  .ind-top { display:flex; align-items:center; justify-content:space-between; gap:6px; }
  .ind-name { font-size:11px; font-weight:500; color:var(--text2); text-transform:uppercase; letter-spacing:0.04em; }
  .signal-pill { font-size:10px; font-weight:600; padding:2px 8px; border-radius:20px; font-family:'DM Mono',monospace; white-space:nowrap; }
  .signal-pill.bull { background:var(--bull-bg); color:var(--bull); border:1px solid var(--bull-border); }
  .signal-pill.bear { background:var(--bear-bg); color:var(--bear); border:1px solid var(--bear-border); }
  .signal-pill.neutral { background:var(--neutral-bg); color:var(--neutral); border:1px solid rgba(139,146,168,0.25); }
  .ind-value { font-size:20px; font-weight:600; font-family:'DM Mono',monospace; letter-spacing:-0.5px; line-height:1; }
  .ind-value.bull { color:var(--bull); } .ind-value.bear { color:var(--bear); } .ind-value.neutral { color:var(--text); }
  .ind-unit { font-size:11px; font-weight:400; color:var(--text2); margin-left:4px; font-family:'DM Sans',sans-serif; }
  .ind-change { font-size:12px; font-weight:500; }
  .ind-change.bull { color:var(--bull); } .ind-change.bear { color:var(--bear); } .ind-change.neutral { color:var(--text2); }
  .ind-meta { font-size:11px; color:var(--text3); }
  .metro-grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(220px,1fr)); gap:10px; }
  .metro-card { background:var(--bg2); border:1px solid var(--border); border-radius:var(--radius); padding:14px 16px; }
  .metro-name { font-size:13px; font-weight:600; color:var(--text); margin-bottom:10px; display:flex; align-items:center; justify-content:space-between; }
  .metro-outlook { font-size:10px; font-weight:600; padding:2px 8px; border-radius:20px; font-family:'DM Mono',monospace; }
  .metro-outlook.bull { background:var(--bull-bg); color:var(--bull); border:1px solid var(--bull-border); }
  .metro-outlook.bear { background:var(--bear-bg); color:var(--bear); border:1px solid var(--bear-border); }
  .metro-outlook.neutral { background:var(--neutral-bg); color:var(--neutral); border:1px solid rgba(139,146,168,0.25); }
  .metro-row { display:flex; justify-content:space-between; align-items:center; padding:4px 0; border-bottom:1px solid var(--border); }
  .metro-row:last-of-type { border-bottom:none; }
  .metro-row-label { font-size:11px; color:var(--text3); }
  .metro-row-val { font-size:12px; font-weight:500; }
  .metro-row-val.bull { color:var(--bull); } .metro-row-val.bear { color:var(--bear); } .metro-row-val.neutral { color:var(--text2); }
  .metro-note { font-size:10px; color:var(--text3); margin-top:8px; }
  .footer { margin-top:2rem; padding-top:1.25rem; border-top:1px solid var(--border); display:flex; align-items:center; justify-content:space-between; flex-wrap:wrap; gap:8px; }
  .footer-note { font-size:11px; color:var(--text3); max-width:620px; }
  @media(max-width:600px) { .cards-grid,.metro-grid { grid-template-columns:1fr 1fr; } .summary-bar { flex-wrap:wrap; } .summary-item { min-width:50%; border-bottom:1px solid var(--border); } }
</style>
"""

SHARED_JS = """
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=DM+Sans:wght@300;400;500;600&display=swap" rel="stylesheet">
<script>
function renderCards(containerId, items) {
  var el = document.getElementById(containerId);
  el.innerHTML = items.map(function(item) {
    var arrow = item.signal==='bull' ? '▲ BULL' : item.signal==='bear' ? '▼ BEAR' : '— NEUT';
    return '<div class="ind-card '+item.signal+'">'
      +'<div class="ind-top"><span class="ind-name">'+item.name+'</span>'
      +'<span class="signal-pill '+item.signal+'">'+arrow+'</span></div>'
      +'<div class="ind-value '+item.signal+'">'+item.value
      +'<span class="ind-unit">'+item.unit+'</span></div>'
      +'<div class="ind-change '+item.signal+'">'+item.change+'</div>'
      +'<div class="ind-meta">'+item.note+'</div></div>';
  }).join('');
}
function countSignals(sections) {
  var all = []; sections.forEach(function(s){all=all.concat(s);});
  var bull=all.filter(function(i){return i.signal==='bull';}).length;
  var bear=all.filter(function(i){return i.signal==='bear';}).length;
  var neutral=all.filter(function(i){return i.signal==='neutral';}).length;
  document.getElementById('bull-count').textContent=bull;
  document.getElementById('bear-count').textContent=bear;
  document.getElementById('neutral-count').textContent=neutral;
  var v=document.getElementById('overall-verdict');
  if(bull>bear+2){v.textContent='⬆ Leaning Bullish';v.style.color='var(--bull)';}
  else if(bear>bull){v.textContent='⬇ Leaning Bearish';v.style.color='var(--bear)';}
  else{v.textContent='↔ Mixed Signals';v.style.color='var(--neutral)';}
}
</script>
"""

# ── Build indicator JS blobs ───────────────────────────────────────────────────
def js_blob(name, data):
    return f"var {name} = {json.dumps(data, indent=2)};\n"


# ── Render HTML ───────────────────────────────────────────────────────────────
def render_global():
    ind = GLOBAL_INDICATORS
    data_js = (
        js_blob("demandData", ind["demand"])
        + js_blob("inputData",  ind["input"])
        + js_blob("tradeData",  ind["trade"])
        + js_blob("macroData",  ind["macro"])
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Rebar Market Dashboard — Global</title>
{SHARED_JS}
{SHARED_STYLE}
</head>
<body>
<div class="page">
  <div class="header">
    <div class="header-left">
      <h1>Rebar Market Dashboard</h1>
      <p>Global leading indicators &mdash; auto-updated every Monday at 6 AM CT</p>
    </div>
    <span class="badge">Updated: {TODAY}</span>
  </div>
  <div class="summary-bar">
    <div class="summary-item"><span class="summary-count bull" id="bull-count">—</span><span class="summary-label">Bullish</span></div>
    <div class="summary-item"><span class="summary-count bear" id="bear-count">—</span><span class="summary-label">Bearish</span></div>
    <div class="summary-item"><span class="summary-count neutral" id="neutral-count">—</span><span class="summary-label">Neutral</span></div>
    <div class="summary-item"><span class="summary-count verdict" id="overall-verdict">—</span><span class="summary-label">Overall signal</span></div>
  </div>
  <div class="section-label">Demand indicators</div>
  <div class="cards-grid" id="demand-cards"></div>
  <div class="section-label">Input cost indicators</div>
  <div class="cards-grid" id="input-cards"></div>
  <div class="section-label">Supply &amp; trade indicators</div>
  <div class="cards-grid" id="trade-cards"></div>
  <div class="section-label">Macro indicators</div>
  <div class="cards-grid" id="macro-cards"></div>
  <div class="footer">
    <p class="footer-note">Live data: FRED (housing, treasury, PMI, fed funds), EIA (WTI). Manual indicators: AMM scrap, AISI utilization, SHFE futures, ABI, Dodge. Auto-refreshed every Monday 6 AM CT via GitHub Actions.</p>
    <span class="badge">Global View</span>
  </div>
</div>
<script>
{data_js}
renderCards('demand-cards', demandData);
renderCards('input-cards',  inputData);
renderCards('trade-cards',  tradeData);
renderCards('macro-cards',  macroData);
countSignals([demandData, inputData, tradeData, macroData]);
</script>
</body>
</html>"""


def render_texas():
    ind = TEXAS_INDICATORS
    data_js = (
        js_blob("demandData", ind["demand"])
        + js_blob("infraData",  ind["infra"])
        + js_blob("macroData",  ind["macro"])
        + js_blob("metroData",  METRO_DATA)
    )
    metro_render = """
function renderMetros() {
  var el = document.getElementById('metro-grid');
  el.innerHTML = metroData.map(function(m) {
    var oArr = m.outlook==='bull'?'▲ BULL':m.outlook==='bear'?'▼ BEAR':'— NEUT';
    return '<div class="metro-card">'
      +'<div class="metro-name">'+m.name
      +'<span class="metro-outlook '+m.outlook+'">'+oArr+'</span></div>'
      +'<div class="metro-row"><span class="metro-row-label">Permits</span><span class="metro-row-val '+m.permits_cls+'">'+m.permits+'</span></div>'
      +'<div class="metro-row"><span class="metro-row-label">Price YoY</span><span class="metro-row-val '+m.price_cls+'">'+m.price+'</span></div>'
      +'<div class="metro-row"><span class="metro-row-label">Trend</span><span class="metro-row-val '+m.trend_cls+'">'+m.trend+'</span></div>'
      +'<p class="metro-note">'+m.note+'</p></div>';
  }).join('');
}
"""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Rebar Market Dashboard — Texas</title>
{SHARED_JS}
{SHARED_STYLE}
</head>
<body>
<div class="page">
  <div class="header">
    <div class="header-left">
      <h1>Texas Rebar Market Dashboard <span class="tx-badge">LONE STAR STATE</span></h1>
      <p>State-specific leading indicators &mdash; auto-updated every Monday at 6 AM CT</p>
    </div>
    <span class="badge">Updated: {TODAY}</span>
  </div>
  <div class="summary-bar">
    <div class="summary-item"><span class="summary-count bull" id="bull-count">—</span><span class="summary-label">Bullish</span></div>
    <div class="summary-item"><span class="summary-count bear" id="bear-count">—</span><span class="summary-label">Bearish</span></div>
    <div class="summary-item"><span class="summary-count neutral" id="neutral-count">—</span><span class="summary-label">Neutral</span></div>
    <div class="summary-item"><span class="summary-count verdict" id="overall-verdict">—</span><span class="summary-label">Overall signal</span></div>
  </div>
  <div class="section-label">Texas demand indicators</div>
  <div class="cards-grid" id="demand-cards"></div>
  <div class="section-label">Texas infrastructure &amp; industrial pipeline</div>
  <div class="cards-grid" id="infra-cards"></div>
  <div class="section-label">Texas macro &amp; energy indicators</div>
  <div class="cards-grid" id="macro-cards"></div>
  <div class="section-label">Metro-level construction outlook</div>
  <div class="metro-grid" id="metro-grid"></div>
  <div class="footer">
    <p class="footer-note">Live data: FRED (TX permits, WTI crude). Manual indicators: TRERC forecasts, Dallas Fed, TxDOT pipeline, metro permit data. Auto-refreshed every Monday 6 AM CT via GitHub Actions.</p>
    <span class="badge">Texas View</span>
  </div>
</div>
<script>
{data_js}
{metro_render}
renderCards('demand-cards', demandData);
renderCards('infra-cards',  infraData);
renderCards('macro-cards',  macroData);
renderMetros();
countSignals([demandData, infraData, macroData]);
</script>
</body>
</html>"""


# ── Write files ───────────────────────────────────────────────────────────────
out_dir = os.path.join(os.path.dirname(__file__), "..", "docs")
os.makedirs(out_dir, exist_ok=True)

global_path = os.path.join(out_dir, "index.html")
texas_path  = os.path.join(out_dir, "texas.html")

with open(global_path, "w", encoding="utf-8") as f:
    f.write(render_global())
print(f"Written: {global_path}")

with open(texas_path, "w", encoding="utf-8") as f:
    f.write(render_texas())
print(f"Written: {texas_path}")

print("Done.")
