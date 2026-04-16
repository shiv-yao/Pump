# AI Fund Integrated Product

This is a runnable full-stack scaffold that integrates:

- AI Fund Brain
- Execution AI
- RL policy layer
- Alpha Ecosystem
- Sim2Real pipeline
- Investor Dashboard

## Safe by default

- Paper mode is enabled by default
- Real-money execution is not auto-enabled
- Execution integration is exposed through a provider interface

## Run locally

### Backend
```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### Frontend
```bash
cd frontend
npm install
npm run dev
```

### Docker
```bash
docker compose up --build
```\n