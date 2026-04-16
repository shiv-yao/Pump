# Railway deployment guide

This repo is a monorepo with:
- `backend/` FastAPI API
- `frontend/` React frontend

## Deploy on Railway

Create **two Railway services** from the same GitHub repo.

### Service 1: backend
- Root directory: `backend`
- Railway detects `backend/Dockerfile`
- Generate domain after deploy

### Service 2: frontend
- Root directory: `frontend`
- Railway detects `frontend/Dockerfile`
- Generate domain after deploy

## Environment variables

### Backend
Set:
- `APP_DB_PATH=/data/app.db`

Add a Railway volume and mount it to `/data` for persistence.

### Frontend
The current frontend points to `http://localhost:8000/api` in `frontend/src/lib/api.js`.
Before production, replace it with your backend public URL.

Recommended change:
- create `VITE_API_BASE_URL`
- use `import.meta.env.VITE_API_BASE_URL`

Then set it in Railway Variables for the frontend service.

## Important

This system is still safe-by-default:
- `mock` execution is the default
- `integration` requires unlock + manual confirm
- real execution adapter must be implemented in:
  `backend/app/execution/live_adapter.py`


## Frontend environment variable

This package is already wired for Vite env variables.

Set this in the Railway **frontend** service:
- `VITE_API_BASE_URL=https://your-backend-domain/api`

Example:
- `VITE_API_BASE_URL=https://ai-fund-backend-production.up.railway.app/api`

For local development, you can copy:
- `frontend/.env.example` -> `frontend/.env`
