# Start and stop IntervAI in VS Code (Windows CMD)

Open Docker Desktop and wait for its engine to be running. Open E:\IntervAI 1 in VS Code. In Terminal > New Terminal, use the dropdown to select Command Prompt (CMD), not PowerShell. Open four terminals.

## 1. Database and coding sandbox

```cmd
cd /d "E:\IntervAI 1"
docker compose -f compose.yaml -f compose.native.yaml up -d db sandbox
```

If docker is not recognized in CMD, first run:

```cmd
set "PATH=%LOCALAPPDATA%\Programs\DockerDesktop\resources\bin;%PATH%"
```

The Docker command returns to the prompt because it runs in the background. This is normal.

## 2. Backend API (leave terminal running)

```cmd
cd /d "E:\IntervAI 1"
.venv\Scripts\python.exe scripts\run_backend.py --port 8001
```

## 3. Background worker (leave terminal running)

```cmd
cd /d "E:\IntervAI 1\backend"
..\.venv\Scripts\python.exe -m app.worker
```

The worker can remain quiet while waiting for jobs. This is normal.

## 4. Frontend (leave terminal running)

```cmd
cd /d "E:\IntervAI 1\frontend"
set "API_INTERNAL_URL=http://127.0.0.1:8001"
npm run dev -- --port 3001
```

Open http://localhost:3001/login after Next.js reports Ready.

## Stop

Press Ctrl+C in frontend, worker and backend terminals. If CMD asks Terminate batch job (Y/N)?, enter Y. Then use the first terminal:

```cmd
cd /d "E:\IntervAI 1"
docker compose -f compose.yaml -f compose.native.yaml stop db sandbox
```

Do not delete Docker volumes. The stop command preserves accounts, resumes and application data. Once all services are stopped, you can close VS Code and Docker Desktop. Start commands assume the existing dependencies/configuration; no reinstall is required each time. Do not launch a second copy while the agent-started background services are already running.
