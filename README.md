# AI Fund Integrated Product (Connected Edition)

This version connects the product scaffold to a safer execution integration flow.

## Added in this edition

- Execution provider switch: `mock` or `integration`
- Manual unlock state
- Manual confirmation endpoint for integration mode
- Safer live-routing guardrails
- Execution adapter file where you can attach your verified Jupiter execution code
- Frontend controls for unlock + integration confirm

## Safety model

- `mock` provider: paper-mode simulation, always safe
- `integration` provider: routes through `app/execution/live_adapter.py`
- live integration requires:
  1. `paper_mode = false`
  2. system unlock
  3. manual confirmation
  4. a verified execution adapter implementation

By default, the included adapter still returns a safe mocked response unless you replace it.

## Run

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
