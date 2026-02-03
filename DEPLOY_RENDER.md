# Render Deployment Guide (Free Tier)

This project runs as three services on Render:
- `server` (Node.js + Socket.IO backend)
- `klymo_client` (Next.js frontend)
- `gender-service` (FastAPI microservice)

It also needs a Render Redis instance for matchmaking and cross‑server state.

## 1) Create Redis (Render Key Value)
1. In Render, create a new Redis (Key Value) service.
2. Copy the connection string into `REDIS_URL`.

## 2) Deploy Backend (Node.js)
Create a **Web Service** with:
- Root Directory: `server`
- Build Command: `npm ci`
- Start Command: `npm start`

Environment variables:
- `REDIS_URL` = your Render Redis connection string
- `CLIENT_ORIGINS` = `https://<your-frontend>.onrender.com`
- `GENDER_SERVICE_URL` = `https://<your-gender-service>.onrender.com`
- `VERIFICATION_TOKEN_SECRET` = strong random string (required in production)
- `HF_API_TOKEN` = optional (only if you plan to call Hugging Face from server)
- Optional tuning:
  - `DAILY_MATCH_LIMIT` (default `100`)
  - `REPORT_THRESHOLD` (default `5`)
  - `REPORT_TTL_SECONDS` (default `604800`)
  - `MATCH_COUNT_TTL_SECONDS` (default `172800`)
  - `VERIFICATION_TOKEN_TTL_SECONDS` (default `86400`)

Render automatically provides `PORT`.

## 3) Deploy Gender Service (FastAPI)
Create a **Web Service** with:
- Root Directory: `server/gender-service`
- Build Command: `pip install -r requirements.txt`
- Start Command: `uvicorn main:app --host 0.0.0.0 --port $PORT`

Notes:
- First boot can take longer because models may download on cold start.
- This service is called by the backend, not directly by the browser.

## 4) Deploy Frontend (Next.js)
Create a **Web Service** with:
- Root Directory: `klymo_client`
- Build Command: `npm ci && npm run build`
- Start Command: `npm start`

Environment variables:
- `NEXT_PUBLIC_SOCKET_URL` = `https://<your-backend>.onrender.com`
- `NEXT_PUBLIC_API_URL` = `https://<your-backend>.onrender.com`

## 5) Final Wiring Checklist
- Backend `CLIENT_ORIGINS` includes your frontend URL.
- Frontend `NEXT_PUBLIC_SOCKET_URL` points to backend.
- Backend `GENDER_SERVICE_URL` points to gender-service.
- Backend `REDIS_URL` is set and reachable.

## Free Tier Note
Render free services sleep when idle. This can cause WebSocket disconnects on cold start.
The client now retries and handles reconnection, but a short wake‑up delay is still expected.
