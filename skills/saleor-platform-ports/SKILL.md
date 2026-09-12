---
name: saleor-platform-ports
description: Port and domain rules for the local Saleor environment (saleor-platform). Use whenever changing ports or domains, debugging app installs ("auth data ... fetch app ID", "App with provided identifier not found"), or when any service reports the wrong Saleor URL (e.g. http://localhost:8000/graphql/).
---

# Saleor platform: ports & domain rules

## Example local port map (authoritative)

| Port | Service | Owner |
| ---- | ------- | ----- |
| 8001 | Saleor API host port (container 0.0.0.0:8001->8000) | `saleor-platform` compose `api` |
| 9001 | Saleor Dashboard (nginx container) | `saleor-platform` compose `dashboard` |
| 3001 | Dummy Payment App (runs on Windows host, Next.js) | `saleor-apps/apps/dummy-payment-app` |
| 3000 | Paper storefront | `storefront-paper` |
| 8000 | **Dummy (unrelated legacy service)** — NEVER hand this to Saleor | external |
| 5433 | PostgreSQL 18 (db `saleor`, user/password `saleor`) container `infrastructure-postgres-1` | external |

Rule: **port 8000 is not available.** Any config, env var, or DB row still pointing Saleor
at `localhost:8000` is stale and must be fixed, not treated as an option.

## Every place the Saleor URL / domain is encoded

When changing the API port or domain, check/update ALL of these:

1. `saleor-platform/docker-compose.yml`
   - `api.environment.PUBLIC_URL` (e.g. `http://localhost:8001/`)
   - `worker.environment.PUBLIC_URL` — **must be identical to api**. `install_app_task`
     (celery, runs in worker) builds the `Saleor-API-Url` header sent to apps from
     `get_domain()`, which prefers `settings.PUBLIC_URL`. Without it the worker falls
     back to the stale `django_site` domain and app installs fail with:
     "The auth data given during registration request could not be used to fetch app ID…
     Saleor URL that App tried to connect: http://localhost:8000/graphql/".
     The same setting also determines the JWT issuer for app tokens (worker signs,
     api validates) — they must match.
   - `api.environment.DASHBOARD_URL`
   - `dashboard.environment.API_URL` (e.g. `http://localhost:8001/graphql/`)
2. `django_site` table (db `saleor`): row id 1 `domain` is the fallback used when
   `PUBLIC_URL` is unset. Keep it in sync or ensure PUBLIC_URL is always set.
3. `saleor-apps/apps/dummy-payment-app/.env.local` (and `.env.example`):
   - `APP_IFRAME_BASE_URL` — browser-facing app URL (`http://localhost:3001`)
   - `APP_API_BASE_URL` — URL the Saleor backend/worker uses to reach the app
     (`http://host.docker.internal:3001` — host name required because the API is containerized)
   - Manifest URL pasted into the Dashboard: `http://host.docker.internal:3001/api/manifest`
4. Storefront / other consumers' API URL env vars.

## Two directions, two hostnames

- **Host browser / host node → containerized services**: use `localhost:<mapped port>`.
- **Docker container → Windows host** (worker → Dummy Payment App): use
  `http://host.docker.internal:<host port>`. Never `localhost` inside compose.

## Change-port checklist

When the Saleor API host port (or app port) changes:

1. Update the compose `ports:` mapping.
2. Update `api` + `worker` `PUBLIC_URL`, `api` `DASHBOARD_URL`, `dashboard` `API_URL`
   to the new API port.
3. Restart only affected containers:
   `docker compose -f saleor-platform/docker-compose.yml up -d api worker dashboard`
   (a changed `environment:` requires container recreation, not just restart).
4. Sync `django_site` domain (or rely on PUBLIC_URL everywhere) — DB update.
5. Update app `.env.local` (`APP_IFRAME_BASE_URL` / `APP_API_BASE_URL`) if the app
   host port changed; restart the app's dev server; manifest picks it up automatically.
6. Reinstall apps if a failed install left a stale `http://localhost:8000/...` in the
   last `app_appinstallation` row — apps store the URL handed to them at install time.

## Verification commands

```bash
# Worker resolves the right URL (the #1 install-failure check)
docker exec saleor-platform-worker-1 sh -c "python -c \"
import os, django; os.environ.setdefault('DJANGO_SETTINGS_MODULE','saleor.settings'); django.setup()
from saleor.core.utils import get_domain, build_absolute_uri
from django.urls import reverse
print(get_domain(), build_absolute_uri(reverse('api'), get_domain()))\""

# Expected: localhost:8001  http://localhost:8001/graphql/

# App state in the DB
docker exec infrastructure-postgres-1 psql -U saleor -d saleor -c \
  "select id, status, message from app_appinstallation order by id desc limit 1;"
docker exec infrastructure-postgres-1 psql -U saleor -d saleor -c \
  "select identifier, app_url, is_active, is_installed from app_app;"

# APL file must contain the new saleorApiUrl after install:
# saleor-apps/apps/dummy-payment-app/.saleor-app-auth.json

# Reachability checks
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8001/graphql/   # 200 = saleor
curl -s http://localhost:3001/api/manifest | head -c 300                  # manifest ok
```

## Known failure signatures → cause

| Symptom | Cause |
| ------- | ----- |
| Install fails: "auth data given during registration request could not be used to fetch app ID … Saleor URL that App tried to connect: http://localhost:8000/graphql/" | Worker lacks `PUBLIC_URL` (falls back to stale `django_site` domain); or app host port no longer serving Saleor |
| "Payment initialization error: App with provided identifier not found." (`transaction_initialize.py`) | No app with that identifier is installed/active — install problem, not gateway config |
| App registered but webhooks 401/404 | `APP_API_BASE_URL` wrong (must be `host.docker.internal` from the backend's view) |
| Dashboard "cannot connect to API" | `API_URL` in dashboard container env wrong |

## Safety

- Do NOT touch port 8000 (When already in use) or external Postgres containers.
- Changing `PUBLIC_URL`/domain requires container recreation; no DB migration needed
  except the optional `django_site` sync.
- After any port change, re-verify the worker output above BEFORE (re)installing apps.
