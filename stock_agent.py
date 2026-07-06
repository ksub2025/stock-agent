"""
Stock Analyst Agent v1.1 - Portfolio Edition
Streamlit + Claude + yfinance

New in v1.1:
- portfolio.json holds your positions
- Live dashboard with P&L per position and total
- Threshold badges when a position crosses 10% / 15%
- Second tool: Claude can read your live portfolio status

Run:
    pip install streamlit anthropic yfinance pandas
    streamlit run stock_agent.py
(keep portfolio.json in the same folder)
"""

import json
import os
from datetime import datetime
from pathlib import Path

import anthropic
import pandas as pd
import streamlit as st
import yfinance as yf

PORTFOLIO_FILE = Path(__file__).parent / "portfolio.json"

# ---------------------------------------------------------------
# Tool 1: single stock analysis
# ---------------------------------------------------------------

def get_stock_data(ticker: str) -> dict:
    """Fetch price, moving averages, RSI, and volume data for a ticker."""

    def _fetch(symbol):
        t = yf.Ticker(symbol)
        hist = t.history(period="1y")
        return t, hist

    ticker = ticker.strip().upper()
    stock, hist = _fetch(ticker if "." in ticker else ticker + ".NS")
    if hist.empty and "." not in ticker:
        stock, hist = _fetch(ticker)
    if hist.empty:
        return {"error": f"No data found for '{ticker}'. Check the symbol."}

    close = hist["Close"]
    volume = hist["Volume"]

    dma20 = close.rolling(20).mean().iloc[-1]
    dma50 = close.rolling(50).mean().iloc[-1]
    dma200 = close.rolling(200).mean().iloc[-1] if len(close) >= 200 else None

    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rsi = (100 - 100 / (1 + gain / loss)).iloc[-1]

    last = close.iloc[-1]
    prev = close.iloc[-2] if len(close) > 1 else last

    info = {}
    try:
        info = stock.info or {}
    except Exception:
        pass

    return {
        "ticker": stock.ticker,
        "name": info.get("longName", stock.ticker),
        "last_close": round(float(last), 2),
        "day_change_pct": round(float((last - prev) / prev * 100), 2),
        "dma_20": round(float(dma20), 2),
        "dma_50": round(float(dma50), 2),
        "dma_200": round(float(dma200), 2) if dma200 else "insufficient history",
        "rsi_14": round(float(rsi), 2),
        "52w_high": round(float(close.max()), 2),
        "52w_low": round(float(close.min()), 2),
        "avg_volume_20d": int(volume.rolling(20).mean().iloc[-1]),
        "last_volume": int(volume.iloc[-1]),
        "pe_ratio": info.get("trailingPE"),
        "sector": info.get("sector"),
    }


# ---------------------------------------------------------------
# Tool 2: portfolio status
# ---------------------------------------------------------------

def load_portfolio() -> dict:
    with open(PORTFOLIO_FILE) as f:
        return json.load(f)


@st.cache_data(ttl=300)  # refresh live prices at most every 5 minutes
def fetch_live_prices(tickers: tuple) -> dict:
    prices = {}
    for t in tickers:
        try:
            hist = yf.Ticker(t).history(period="5d")
            if not hist.empty:
                closes = hist["Close"]
                prices[t] = {
                    "ltp": float(closes.iloc[-1]),
                    "prev_close": float(closes.iloc[-2]) if len(closes) > 1 else float(closes.iloc[-1]),
                }
        except Exception:
            prices[t] = None
    return prices


def get_portfolio_status() -> dict:
    """Compute live P&L, day moves, days held, and threshold flags."""
    pf = load_portfolio()
    target = pf.get("target_pct", 10)
    stretch = pf.get("stretch_target_pct", 15)
    prices = fetch_live_prices(tuple(p["ticker"] for p in pf["positions"]))

    rows, total_cost, total_value = [], 0.0, 0.0
    for p in pf["positions"]:
        live = prices.get(p["ticker"])
        if not live:
            rows.append({"ticker": p["ticker"], "error": "price fetch failed"})
            continue

        cost = p["qty"] * p["buy_price"]
        value = p["qty"] * live["ltp"]
        pnl = value - cost
        pnl_pct = pnl / cost * 100
        day_pct = (live["ltp"] - live["prev_close"]) / live["prev_close"] * 100
        days_held = (datetime.now() - datetime.strptime(p["buy_date"], "%Y-%m-%d")).days

        if pnl_pct >= stretch:
            flag = f"HIT {stretch}% STRETCH TARGET"
        elif pnl_pct >= target:
            flag = f"HIT {target}% TARGET"
        elif pnl_pct <= -target:
            flag = f"DOWN MORE THAN {target}%, review against exit rules"
        else:
            flag = None

        rows.append({
            "ticker": p["ticker"],
            "name": p["name"],
            "qty": p["qty"],
            "buy_price": p["buy_price"],
            "buy_date": p["buy_date"],
            "days_held": days_held,
            "ltp": round(live["ltp"], 2),
            "day_change_pct": round(day_pct, 2),
            "invested": round(cost, 2),
            "current_value": round(value, 2),
            "pnl": round(pnl, 2),
            "pnl_pct": round(pnl_pct, 2),
            "alert": flag,
        })
        total_cost += cost
        total_value += value

    return {
        "as_of": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "target_pct": target,
        "stretch_target_pct": stretch,
        "positions": rows,
        "total_invested": round(total_cost, 2),
        "total_value": round(total_value, 2),
        "total_pnl": round(total_value - total_cost, 2),
        "total_pnl_pct": round((total_value - total_cost) / total_cost * 100, 2) if total_cost else 0,
    }


# ---------------------------------------------------------------
# Claude wiring
# ---------------------------------------------------------------

TOOLS = [
    {
        "name": "get_stock_data",
        "description": (
            "Fetch current price, 20/50/200 day moving averages, RSI(14), "
            "52-week range, volume, and basic fundamentals for one stock. "
            "NSE symbols use .NS suffix; bare symbols are tried with .NS."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"ticker": {"type": "string", "description": "e.g. ECLERX.NS"}},
            "required": ["ticker"],
        },
    },
    {
        "name": "get_portfolio_status",
        "description": (
            "Fetch the user's live portfolio: every position with quantity, "
            "buy price, buy date, days held, current price, P&L in rupees and "
            "percent, day change, and alert flags for positions that crossed "
            "the 10% target or 15% stretch target. Call this whenever the user "
            "asks about their portfolio, holdings, P&L, or targets."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
]

SYSTEM_PROMPT = """You are a stock analysis assistant for a swing trader
learning the craft. You have two tools: get_stock_data for analyzing any
single stock, and get_portfolio_status for the user's live holdings with
P&L and target flags. Use real data before answering; never guess prices.

The user's plan: book profits in the 10 to 15 percent zone per position.
When a position has crossed a threshold, say so clearly and early in your
answer. Be objective and factual. Present observations and data, not
buy/sell instructions; the user makes all decisions. Amounts are in INR."""

TOOL_FUNCTIONS = {
    "get_stock_data": get_stock_data,
    "get_portfolio_status": get_portfolio_status,
}


def run_agent(client, messages):
    while True:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2000,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
        )
        if response.stop_reason != "tool_use":
            return "".join(b.text for b in response.content if b.type == "text")

        messages.append({"role": "assistant", "content": response.content})
        tool_results = []
        for block in response.content:
            if block.type == "tool_use":
                fn = TOOL_FUNCTIONS[block.name]
                with st.status(f"Running {block.name}..."):
                    result = fn(**block.input)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps(result, default=str),
                })
        messages.append({"role": "user", "content": tool_results})


# ---------------------------------------------------------------
# UI
# ---------------------------------------------------------------

st.set_page_config(page_title="Stock Analyst Agent", page_icon="📈", layout="wide")
st.title("📈 Stock Analyst Agent")
st.caption("Your portfolio, live. Analysis, not advice.")

api_key = os.environ.get("ANTHROPIC_API_KEY", "")
if not api_key:
    api_key = st.sidebar.text_input("Anthropic API key", type="password")

# ----- Dashboard -----
try:
    status = get_portfolio_status()

    c1, c2, c3 = st.columns(3)
    c1.metric("Invested", f"₹{status['total_invested']:,.0f}")
    c2.metric(
        "Current Value",
        f"₹{status['total_value']:,.0f}",
        f"{status['total_pnl_pct']:+.2f}%",
    )
    c3.metric("Total P&L", f"₹{status['total_pnl']:,.0f}")

    alerts = [p for p in status["positions"] if p.get("alert")]
    for p in alerts:
        if "TARGET" in p["alert"]:
            st.success(f"🎯 {p['name']}: {p['alert']} (up {p['pnl_pct']}%)")
        else:
            st.warning(f"⚠️ {p['name']}: {p['alert']} ({p['pnl_pct']}%)")

    df = pd.DataFrame([p for p in status["positions"] if "error" not in p])
    if not df.empty:
        show = df[["name", "qty", "buy_price", "ltp", "day_change_pct",
                   "pnl", "pnl_pct", "days_held"]].rename(columns={
            "name": "Stock", "qty": "Qty", "buy_price": "Buy",
            "ltp": "LTP", "day_change_pct": "Day %",
            "pnl": "P&L ₹", "pnl_pct": "P&L %", "days_held": "Days",
        })
        st.dataframe(
            show.style.map(
                lambda v: "color: green" if isinstance(v, (int, float)) and v > 0
                else ("color: red" if isinstance(v, (int, float)) and v < 0 else ""),
                subset=["Day %", "P&L ₹", "P&L %"],
            ),
            use_container_width=True,
            hide_index=True,
        )
    st.caption(f"Prices as of {status['as_of']} (cached up to 5 min). "
               f"Targets: {status['target_pct']}% / {status['stretch_target_pct']}%")
except FileNotFoundError:
    st.error("portfolio.json not found. Keep it in the same folder as this app.")

st.divider()

# ----- Chat -----
if not api_key:
    st.info("Add your ANTHROPIC_API_KEY (environment variable or sidebar) to chat.")
    st.stop()

client = anthropic.Anthropic(api_key=api_key)

if "messages" not in st.session_state:
    st.session_state.messages = []
if "display" not in st.session_state:
    st.session_state.display = []

for msg in st.session_state.display:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

if prompt := st.chat_input("Try: 'How is my portfolio doing?' or 'Should Lupin worry me?'"):
    st.session_state.display.append({"role": "user", "content": prompt})
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        try:
            answer = run_agent(client, st.session_state.messages)
        except Exception as e:
            answer = f"Something went wrong: {e}"
        st.markdown(answer)

    st.session_state.messages.append({"role": "assistant", "content": answer})
    st.session_state.display.append({"role": "assistant", "content": answer})
