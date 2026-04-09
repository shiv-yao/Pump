# V61 Complete Live Trading Repo

This repo packages a Solana meme-coin trading engine with:
- V52.1-style alpha core extended into a V61 "full live" engine
- Jupiter Swap V2 `/order` + `/execute`
- RPC fallback via `sendTransaction` and `getSignatureStatuses`
- Optional Jito low-latency sender
- FastAPI control plane
- Streamlit dashboard
- Railway / Docker deployment files

## Quick start

```bash
pip install -r requirements.txt
python run.py
```

## Required environment variables
- `JUP_API_KEY`
- `SOLANA_PRIVATE_KEY_B58` or `PRIVATE_KEY_B58`
- `SOLANA_RPC_HTTP`
- Optional: `USE_JITO=true`, `JITO_AUTH_UUID`, `BIRDEYE_API_KEY`

## Notes
- Start in paper mode first: `REAL_TRADING=false`
- Then switch to real mode only after validating quotes, signing, balances, and tx landing.
