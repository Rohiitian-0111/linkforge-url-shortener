# Run Linkforge on Windows

## 1. Install prerequisites

Install Python 3.11 or newer from <https://www.python.org/downloads/windows/> and Docker Desktop from <https://docs.docker.com/desktop/setup/install/windows-install/>. Follow Docker's current Windows / WSL 2 requirements. Launch Docker Desktop and wait until its engine is running. Use Linux containers.

Open PowerShell and check:

```powershell
py -3 --version
docker --version
docker compose version
```

If Python works as `python` but not `py -3`, use `python` in the commands below. If Docker is not found, finish installation and open a new terminal. Node.js is unnecessary for the Docker route.

## 2. Extract the project

Right-click the ZIP, choose **Extract All**, and open the extracted `linkforge` directory. You should see `README.md`, `docker-compose.yml`, `backend`, `frontend`, and `scripts`.

Open PowerShell in this folder. You can type `powershell` in File Explorer's address bar and press Enter. Check the location:

```powershell
Get-Location
Get-ChildItem
```

Do not run the project from inside the ZIP preview.

## 3. Generate configuration

```powershell
py -3 scripts/setup.py
```

This creates `.env` with new random secrets and the local URLs. It will preserve an existing configuration. There is no need to paste a JWT key or database password from the internet. Do not upload your `.env` to GitHub.

## 4. Start the full application

```powershell
docker compose up --build
```

Leave this terminal open. The first run downloads dependencies and creates the database schema. When the frontend and API are running, open <http://localhost:8080>.

An alternative is double-clicking `start_windows.bat`; it runs the same setup and Docker commands. If Windows prevents opening the batch file, use the explicit PowerShell commands above. You do not need to disable Windows security controls.

## 5. Complete your first end-to-end workflow

1. Choose the registration option in the dashboard.
2. Enter a name, a valid email format, and a password of at least 10 characters.
3. Create a link with destination `https://example.com/` and a title such as “My first link”.
4. Optionally enter a custom alias, such as `first-link-2026`.
5. Copy the generated `http://localhost:8080/r/...` URL and open it in another tab.
6. Return to the dashboard, wait a moment for the worker, and refresh the analytics.
7. Edit the title, pause the link, and verify the paused link no longer redirects.
8. Resume it, then test the redirect again.

`localhost` addresses work only on your computer. To share links with others, deploy to a server and set `PUBLIC_BASE_URL` to its HTTPS hostname. Merely changing this value does not deploy anything.

## 6. Stop and restart

If Docker is running in the foreground, press **Ctrl+C** once. To stop it from another terminal:

```powershell
docker compose down
```

Your data stays in Docker's named volumes. Restart in the background:

```powershell
docker compose up -d
```

Show logs:

```powershell
docker compose ps
docker compose logs --tail=100 api worker
```

Only use `docker compose down -v` when you deliberately want to erase all local accounts, links, and analytics.

## Common problems

| Symptom | What to check |
| --- | --- |
| “Cannot connect to the Docker daemon” | Open Docker Desktop and wait for the engine. Check its WSL 2 configuration. |
| “no configuration file provided” | Change directory to the folder containing `docker-compose.yml`. |
| “POSTGRES_PASSWORD required” or similar | Run `py -3 scripts/setup.py` from that folder. |
| Setup says `.env` has placeholder secrets | If this is an unused configuration, rename it and rerun setup. Preserve a configuration attached to existing data. |
| Port 8080 already allocated | Change `FRONTEND_PORT=8081` and `PUBLIC_BASE_URL=http://localhost:8081` in `.env`; also change origins to that URL. Restart with `docker compose up -d`. |
| Port 8000 already allocated | Change `API_PORT=8001`; the dashboard's internal API routing stays the same. Open docs on port 8001. |
| Database password authentication failed | Do not generate new database credentials while keeping old database volumes. Restore the original `.env`, or intentionally reset disposable data. |
| Login/create returns 503 | Check `docker compose ps` and Redis logs. Production write limits fail closed when Redis is unavailable. |
| Too many requests / 429 | Wait for `Retry-After`. Authentication and creation have different windows. |
| Redirect works but clicks remain zero | Check worker logs, then refresh analytics. Verify `ANALYTICS_MODE=stream` and worker availability. |
| A deleted/paused link briefly redirects after an outage | A cache invalidation may have failed during the outage. Wait for the configured cache TTL; see architecture notes. |
| Dashboard is blank after source changes | Rebuild using `docker compose up --build -d` and reload the browser. |

## Run the HTTP smoke test

Create a separate Python environment for test tooling from the project root:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install httpx
.\.venv\Scripts\python.exe scripts/smoke_test.py
```

This avoids changing PowerShell's script-execution policy because you call the interpreter directly instead of activating the environment. A successful test prints `PASS` after exercising the running services.

## Before pushing to GitHub

Push the source folder, not Docker volumes, `.venv`, `node_modules`, `.env`, generated databases, or benchmark output containing private URLs. The included `.gitignore` excludes these common local files. Create a new empty GitHub repository and follow its “push an existing repository” instructions. Run the test commands in `README.md` first.
