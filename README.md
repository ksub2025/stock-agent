# Stock Agent 📈

A personal stock analysis agent and portfolio alert system, built in one evening as a Passenger to Pilot exercise. Streamlit chat UI, Claude as the analyst brain, yfinance for live NSE data, Telegram for daily alerts.

Analysis, not advice. The human makes every decision. The system just holds up the mirror.

## What it does

- **Chat with an analyst.** Ask about any NSE stock and get moving averages, RSI, 52-week position, and volume read from live data via a Claude tool-use loop.
- **Portfolio dashboard.** Every position with buy price, live price, P&L in rupees and percent, days held. The view my broker app wouldn't give me.
- **Telegram alerts.** A daily pulse after market close, and loud flags the moment any position crosses the +10% target, +15% stretch target, or falls past -10%.
- **Runs itself.** A cron job checks the portfolio every trading day at 3:35 PM.

## Files

| File | Purpose |
|------|---------|
| `stock_agent.py` | Streamlit app: dashboard + chat agent with two tools |
| `portfolio_alert.py` | Standalone script: checks thresholds, messages Telegram |
| `telegram_hello.py` | One-time setup: finds your chat ID, tests the pipe |
| `portfolio.sample.json` | Template for your positions (copy to `portfolio.json`) |
| `telegram_config.sample.json` | Template for bot credentials (copy to `telegram_config.json`) |

Your real `portfolio.json` and `telegram_config.json` are gitignored. Holdings and tokens never leave your machine.

## Setup

```bash
pip install streamlit anthropic yfinance pandas requests

# your private files, from the templates
cp portfolio.sample.json portfolio.json
cp telegram_config.sample.json telegram_config.json
# then edit both with your real positions and credentials

# the dashboard + chat
export ANTHROPIC_API_KEY=your_key
streamlit run stock_agent.py

# telegram setup (one time): create a bot via @BotFather, press Start on it, then
python telegram_hello.py

# the alert check (cron-friendly)
python portfolio_alert.py
```

To automate, add a cron entry (weekdays 3:35 PM, after NSE close):

```
35 15 * * 1-5 /path/to/python /path/to/portfolio_alert.py >> /path/to/alert.log 2>&1
```

## Architecture note

One `portfolio.json`, two consumers. The Streamlit dashboard and the Telegram alerter both read the same source of truth, so editing a position updates everything. The alert script has no AI in it at all; it is pure plumbing, cheap and deterministic. The intelligence lives only where judgment is needed.

## Built by

Karthi Subbaraman, as part of living the Passenger to Pilot curriculum before teaching it. More at [learnerd.in](https://learnerd.in).
