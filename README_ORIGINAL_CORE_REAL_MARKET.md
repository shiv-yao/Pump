# Pump 原系統核心版 + 真實市場實盤整合版

這包是以你原本的 `Pump-main-debug-fixed` 為主體，不重建架構、不移除原本 plugin/dashboard/API；只做增量整合：

- 保留原本 Plugin Store / dashboard / agent terminal / alpha plugins
- 修正並接上 `/api/trade`, `/api/trade/buy`, `/api/trade/sell`
- 保留原本 `execution_gateway`，並加上 `REAL_TRADING` / `MANUAL_CONFIRM` 防呆
- 保留 Jupiter v2 order/execute + optional Jito bundle path
- 保留 fund brain / wallet alpha / sniper / allocator / risk engine plugins

## 啟動

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

打開：

- `http://localhost:8000/`
- `http://localhost:8000/docs`
- `http://localhost:8000/api/trading/status`

## Railway

Start command:

```bash
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

## 重要 ENV

```env
REAL_TRADING=false
MANUAL_CONFIRM=true
USE_JITO=false
RPC_URL=https://api.mainnet-beta.solana.com
SOLANA_PRIVATE_KEY=
MAX_ORDER_SIZE=25
SLIPPAGE_BPS=80
JITO_TIP_LAMPORTS=2000
```

## 實盤開關

預設安全模式：

```env
REAL_TRADING=false
```

此時 `/api/trade` 只會走 paper guard，不會送鏈上交易。

要真實送單：

```env
REAL_TRADING=true
MANUAL_CONFIRM=true
```

請求要帶：

```json
{
  "symbol": "TOKEN_MINT_OR_SYMBOL",
  "side": "buy",
  "size": 1000000,
  "slippage_bps": 80,
  "confirm": true
}
```

> 注意：目前 execution_gateway 內部 amount 會直接送進 Jupiter order。對 SPL token/USDC 等不同 mint，要使用對應最小單位。先用小額測試。

## API

### 狀態

```bash
curl http://localhost:8000/api/trading/status
```

### Paper 測試交易

```bash
curl -X POST http://localhost:8000/api/trade \
  -H 'Content-Type: application/json' \
  -d '{"symbol":"SOL","side":"buy","size":1000000,"slippage_bps":80}'
```

### 實盤交易

```bash
curl -X POST http://localhost:8000/api/trade \
  -H 'Content-Type: application/json' \
  -d '{"symbol":"SOL","side":"buy","size":1000000,"slippage_bps":80,"confirm":true}'
```

## 這版不是重新做的骨架

主體仍然是你的原系統：

- `app/main.py`
- `app/plugin_manager.py`
- `plugins/*`
- `app/routers/dashboard_v4.py`
- `plugins/execution_gateway`
- `plugins/fund_brain*`
- `plugins/wallet_alpha*`
- `plugins/sniper_engine`

