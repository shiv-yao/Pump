# Tri-AI Marketplace

Runnable scaffold for a three-agent trading control plane with a lightweight plugin marketplace.

## What it does
- **Grok agent**: generates candidate opportunities from a watchlist
- **Claude agent**: converts signals into BUY / WATCH / SKIP decisions
- **GPT agent**: executes the plan in **simulation mode by default**
- **Marketplace API**: list, enable, and disable plugins
- **Railway-ready** deployment files

## Safety / mode
This project runs in **simulation mode** unless you explicitly wire a real execution adapter and set:

```bash
REAL_TRADING=true
```

The included real execution file is only a placeholder and does not send orders.

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open:
- App: `http://127.0.0.1:8000`
- Docs: `http://127.0.0.1:8000/docs`

## Example API calls

Health:
```bash
curl http://127.0.0.1:8000/api/health
```

Run pipeline:
```bash
curl -X POST http://127.0.0.1:8000/api/run \
  -H "Content-Type: application/json" \
  -d '{"watchlist": ["PEPE", "BONK", "WIF", "DOGEAI"], "max_buys": 2}'
```

List plugins:
```bash
curl http://127.0.0.1:8000/api/plugins
```

Enable a plugin:
```bash
curl -X POST http://127.0.0.1:8000/api/plugins/momentum-alpha/enable
```

## Railway deployment
1. Push this folder to GitHub.
2. In Railway, create a new project from that repository.
3. Add environment variables if needed.
4. Deploy.

## Next upgrade points
- Replace `grok_agent.py` with real data feeds
- Replace `claude_agent.py` with an LLM allocator or rule engine
- Replace `jupiter_stub.py` with a thoroughly tested paper-trading or real-trading adapter
- Add DB, auth, billing, and per-user plugin state


## Product Homepage

Open `/` to use the mobile-friendly product dashboard. Open `/api-info` for the raw API summary.
