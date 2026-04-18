# AI Agent Skill Store

Railway 可部署的 AI Agent，支援動態安裝/管理 skills，整合交易系統。

## 功能
- 🤖 Claude-powered AI Agent（支援 tool use）
- ⬡ 動態 Skill 安裝/卸載/啟停
- 💬 Web Chat UI（深色終端風格）
- 🔌 內建 Skills：web_search、calculator、trading_signals
- 📦 範例 Skill：binance_trading（漲跌榜、RSI信號、市場數據）
- 🚀 Railway 一鍵部署

## 部署到 Railway

### 方法一：GitHub 連接（推薦）
```bash
# 1. push 到 GitHub
git init && git add . && git commit -m "init"
git remote add origin https://github.com/YOUR_USERNAME/ai-agent-skill-store
git push -u origin main

# 2. Railway.app → New Project → Deploy from GitHub
# 3. 設定環境變數（見下方）
```

### 方法二：Railway CLI
```bash
npm install -g @railway/cli
railway login
railway init
railway up
```

## 環境變數（Railway Variables）
```
ANTHROPIC_API_KEY=sk-ant-...       # 必填
CLAUDE_MODEL=claude-opus-4-5       # 選填，預設 claude-opus-4-5
AGENT_SYSTEM_PROMPT=你是...        # 選填，自定義 Agent 行為
SERPER_API_KEY=...                 # 選填，啟用真實 web_search
```

## 本地開發
```bash
pip install -r requirements.txt
cp .env.example .env  # 填入 ANTHROPIC_API_KEY
python main.py
# 開啟 http://localhost:8080
```

## Skill 結構
```
skills/
└── my_skill/
    ├── skill.json    # manifest（名稱、描述、tool 定義）
    └── handler.py    # tool 執行邏輯（async def）
```

## 範例：安裝 Binance 交易 Skill
```bash
# 複製範例 skill
cp -r example_skills/binance_trading skills/

# 重啟後自動載入
# 或透過 Web UI → Install Skill → 手動建立
```

## API Endpoints
| 端點 | 說明 |
|------|------|
| GET / | Web Chat UI |
| POST /api/chat | 對話 |
| GET /api/skills | 列出所有 skills |
| POST /api/skills/install | 安裝 skill（URL 或 manifest） |
| POST /api/skills/create | 手動建立 skill |
| DELETE /api/skills/{name} | 移除 skill |
| PATCH /api/skills/{name}/toggle | 啟用/停用 |
| GET /health | 健康檢查 |
