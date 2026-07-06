"""
portfolio_alert.py - Step 2: your portfolio talks to your Telegram.

What it does:
1. Reads portfolio.json (same file your Streamlit app uses)
2. Fetches live prices via yfinance
3. Computes P&L per position
4. Sends a Telegram alert for anything past +10%, +15%, or -10%
5. Optionally sends a daily summary even when nothing crossed

Setup (one time):
    Edit telegram_config.json with your bot token and chat ID.

Run:
    python portfolio_alert.py
"""

import json
from datetime import datetime
from pathlib import Path

import requests
import yfinance as yf

HERE = Path(__file__).parent
PORTFOLIO_FILE = HERE / "portfolio.json"
CONFIG_FILE = HERE / "telegram_config.json"


def load_json(path):
    with open(path) as f:
        return json.load(f)


def get_portfolio_status():
    pf = load_json(PORTFOLIO_FILE)
    target = pf.get("target_pct", 10)
    stretch = pf.get("stretch_target_pct", 15)

    rows, total_cost, total_value = [], 0.0, 0.0
    for p in pf["positions"]:
        try:
            hist = yf.Ticker(p["ticker"]).history(period="5d")
            ltp = float(hist["Close"].iloc[-1])
        except Exception:
            rows.append({"name": p["name"], "error": True})
            continue

        cost = p["qty"] * p["buy_price"]
        value = p["qty"] * ltp
        pnl_pct = (value - cost) / cost * 100

        if pnl_pct >= stretch:
            flag = f"🎯🎯 crossed +{stretch}% stretch target"
        elif pnl_pct >= target:
            flag = f"🎯 crossed +{target}% target"
        elif pnl_pct <= -target:
            flag = f"⚠️ down more than {target}%, review exit rules"
        else:
            flag = None

        rows.append({
            "name": p["name"],
            "ltp": round(ltp, 2),
            "pnl": round(value - cost, 2),
            "pnl_pct": round(pnl_pct, 2),
            "alert": flag,
        })
        total_cost += cost
        total_value += value

    return {
        "positions": rows,
        "total_pnl": round(total_value - total_cost, 2),
        "total_pnl_pct": round((total_value - total_cost) / total_cost * 100, 2) if total_cost else 0,
    }


def send_telegram(cfg, text):
    resp = requests.get(
        f"https://api.telegram.org/bot{cfg['bot_token']}/sendMessage",
        params={"chat_id": cfg["chat_id"], "text": text},
    ).json()
    return resp.get("ok", False)


def main():
    cfg = load_json(CONFIG_FILE)
    if "PASTE" in str(cfg.get("bot_token", "")):
        print("Edit telegram_config.json first: add your bot token and chat ID.")
        return

    status = get_portfolio_status()
    alerts = [p for p in status["positions"] if p.get("alert")]
    now = datetime.now().strftime("%d %b, %I:%M %p")

    if alerts:
        lines = [f"📈 Portfolio Alert ({now})\n"]
        for p in alerts:
            sign = "+" if p["pnl_pct"] >= 0 else ""
            lines.append(f"{p['alert']}\n{p['name']}: {sign}{p['pnl_pct']}% (₹{p['pnl']:+,.0f}) at ₹{p['ltp']}\n")
        lines.append(f"Total P&L: {status['total_pnl_pct']:+.2f}% (₹{status['total_pnl']:+,.0f})")
        message = "\n".join(lines)
    elif cfg.get("always_send_summary", True):
        lines = [f"📊 Daily check ({now}): no thresholds crossed.\n"]
        for p in status["positions"]:
            if p.get("error"):
                lines.append(f"{p['name']}: price fetch failed")
            else:
                sign = "+" if p["pnl_pct"] >= 0 else ""
                lines.append(f"{p['name']}: {sign}{p['pnl_pct']}%")
        lines.append(f"\nTotal: {status['total_pnl_pct']:+.2f}% (₹{status['total_pnl']:+,.0f})")
        message = "\n".join(lines)
    else:
        print("No alerts, summary disabled. Nothing sent.")
        return

    if send_telegram(cfg, message):
        print("Sent to Telegram:\n")
        print(message)
    else:
        print("Telegram send failed. Check token and chat ID in telegram_config.json.")


if __name__ == "__main__":
    main()
