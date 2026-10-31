# Saleor production-style compose + Traefik

Configuration, local TLS and validation notes for the production-style
stack. **Nothing here has been deployed; the original `docker-compose.yml`
(local dev stack) is untouched and all running containers were left alone.**

## 1. Files and how the modes combine

| File | Purpose |
|---|---|
| `docker-compose.yml` | **Original dev stack — unchanged.** |
| `docker-compose.prod.yml` | Base production-style stack: `api`, `worker`, `dashboard`, `cache` (Valkey), `jaeger` (temporary), `mailpit` (temporary). No Traefik, **no published application ports**. |
| `docker-compose.traefik.local.yml` | Overlay: Traefik **local** mode (mkcert, 127.0.0.1:80/443), route labels for the two live domains, Jaeger loopback ports. |
| `docker-compose.traefik.prod.yml` | Overlay: Traefik **production** mode (Let's Encrypt ACME HTTP-01, public 80/443), same route labels. |
| `traefik/static/local/traefik.yaml` | Traefik static config, local mode (ports 80/443 on 127.0.0.1, HTTP→HTTPS redirect, file + docker providers, dashboard off-port). |
| `traefik/static/prod/traefik.yaml` | Traefik static config, production mode (80/443, ACME provider, `domains:` request list, unix socket endpoint). |
| `traefik/dynamic/local/traefik-local.yml` | Dynamic file provider: mkcert TLS (default + SNI cert) and `secure-headers` middleware. |
| `traefik/dynamic/prod/traefik-prod.yml` | Dynamic file provider, production: `secure-headers` with 1-year HSTS. Certs come from ACME, not files. |
| `traefik/certs/childnest-local.pem` | **Generated** local cert (all 4 domains). Git-ignored. |
| `traefik/certs/childnest-local-key.pem` | **Generated** local key. Git-ignored, chmod 600. |
| `traefik/host-services/dockerd-socket-tcp-bridge.py` | Helper for Docker-Desktop-only limitation (section 4). |
| `env/local.env.example` / `env/prod.env.example` | Copy to `.env` (git-ignored) and edit. |
| `docker-compose.traefik.*.yml` route labels | Prepared-but-commented storefront routing (section 3). |

Project name is pinned to `saleor-platform` (top-level `name:`), so the new
stack reuses the existing `saleor-platform_saleor-media` /
`saleor-platform_saleor-cache` volumes and keeps container naming consistent
when you eventually cut over from the dev stack.

### Startup commands (not executed in this task)

```bash
# prepare env (once) + RSA key (once)
cp env/local.env.example .env            # or env/prod.env.example
mkdir -p .secrets
openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:4096 \
  -out .secrets/saleor_rsa.pem

# 0. LOCAL mode only: start the Docker Engine API bridge in WSL
wsl -d Ubuntu-26.04 -- python3 \
  C:/imran/projects/saleor-ecommerce/saleor-platform/traefik/host-services/dockerd-socket-tcp-bridge.py &

# LOCAL (from repo root)
docker compose --env-file .env -f docker-compose.prod.yml \
  -f docker-compose.traefik.local.yml up -d

# PRODUCTION (on a Linux host with public DNS for the domains)
docker compose --env-file .env -f docker-compose.prod.yml \
  -f docker-compose.traefik.prod.yml up -d

# base stack only (internal networking, no proxy)
docker compose --env-file .env -f docker-compose.prod.yml up -d
```

> **Cut-over note:** the new base stack defines the same services as the dev
> stack under the same project name. Actually running it will recreate
> `saleor-platform-api-1` etc. with the new configuration. That is intended
> for when you switch over, but it was deliberately **not** done in this task.
> If you want both running side by side once, consider renaming one project
> (add `name:` to a copy) or bring the dev stack down.

## 2. Local DNS (Windows hosts file)

Add manually to `C:\Windows\System32\drivers\etc\hosts`
(do NOT rely on edits by tools; run editor as admin):

```
127.0.0.1 shop.childnest.co.uk
127.0.0.1 dashboard.childnest.co.uk
127.0.0.1 api.childnest.co.uk
127.0.0.1 store-fe.childnest.co.uk
127.0.0.1 traefik.childnest.co.uk      # optional: Traefik dashboard domain
```

Expected working URLs in local mode (mkcert root CA is already trusted in
your store, so browsers accept the certs):

```
https://api.childnest.co.uk/graphql/
https://dashboard.childnest.co.uk/
https://shop.childnest.co.uk/          (only once storefront exists)
https://store-fe.childnest.co.uk/      (only once that service exists)
```

## 3. Domains & services mapping

| Domain | Service | Status |
|---|---|---|
| `api.childnest.co.uk` | `api` (container 8000) | **Configured** |
| `dashboard.childnest.co.uk` | `dashboard` (container 80) | **Configured** |
| `shop.childnest.co.uk` | Paper storefront (future) | cert only; out of scope this phase |
| `store-fe.childnest.co.uk` | unassigned (out of scope) | cert only; no routing |

> Storefront work (Paper integration and the `store-fe` question) is
> **explicitly out of scope for this task** — a separate follow-up after the
> backend works. No storefront service/image exists here, and neither
> storefront domain is included in the production ACME domains list. The
> local mkcert certificate already covers all four domains, so no cert work
> is needed later.

### `store-fe.childnest.co.uk` — open question for the storefront task
There is **no service in any repo here that corresponds to `store-fe`**:
the only storefront is `storefront-paper` (Next.js, port 3000), and the
other running services are Medusa/Strapi (separate project). It is
**not routed in this phase**. When the storefront task starts, decide
whether it is a reserved alias for the Paper storefront (second `||` host
in the same future router) or a second frontend (older comments in the
monorepo reference a `medusa_storefront`).

The next subsection is **reference documentation for that future task**
only — nothing in it is implemented in this phase.

### Paper storefront — how it will connect (when its image is ready)
`storefront-paper` today `build:`s its own image (tag `saleor-storefront`);
**no published tag exists, so no image reference is used here.** Requirements
from that repo:

- Listens on container port **3000** (Next.js).
- Build args `NEXT_PUBLIC_SALEOR_API_URL`, `NEXT_PUBLIC_STOREFRONT_URL`,
  `NEXT_PUBLIC_DEFAULT_CHANNEL` are **baked into the Next.js build**.
- Joins an external network (it uses `saleor-backend-tier` in its own
  compose file) — our proxy stack will join it to `saleor-proxy-net`.
- Optional runtime var `SALEOR_APP_TOKEN` (for channel discovery /
  `/order/find`); set it in the service env if you enable it.

When an image is published (e.g. `admincareout/kidl:saleor-storefront-1.x`),
add a `storefront` service on `saleor-proxy-net`/`saleor-backend-tier`
exposing 3000, then uncomment the routing block in
`docker-compose.traefik.local.yml` (and mirror it in the prod overlay).

> Because local now uses plain 80/443 and the public domain has no port,
> the API URL that the storefront bakes in is **identical for local and
> production** (`https://api.childnest.co.uk/graphql/`), so a single build
> can serve both — as long as the local hosts file points the domain at
> 127.0.0.1.

## 4. Traefik → Docker provider on Docker Desktop (the one workaround)

**Verified on this host:** Docker Desktop for Windows can **not**
bind-mount the engine socket into a container — both
`\\wsl.localhost\docker-desktop\run\host-services\docker.proxy.sock` and
`\\wsl.localhost\Ubuntu-26.04\var\docker.sock` materialise as *regular
files* inside containers (`stat` shows non-socket; `connect()` →
ECONNREFUSED). So:

- **Local mode uses the engine API over TCP**: a small Python forwarder
  (`traefik/host-services/dockerd-socket-tcp-bridge.py`) runs in the
  `Ubuntu-26.04` WSL distro (which has a real `/var/run/docker.sock` via
  Desktop integration), bound to `127.0.0.1:23750`, and Traefik's docker
  provider points at `http://host.docker.internal:23750` (path verified
  end-to-end from a container in this task).
- **Security limitation (be aware):** the Docker Engine API over TCP has no
  read-only mode. Anything that can reach that port — i.e. *every*
  container on this host — can start containers / read logs / mount
  volumes. On a single-user dev machine this is acceptable; it is not
  acceptable in production. Kill the bridge when Traefik is down
  (`wsl -d Ubuntu-26.04 -- pkill -f dockerd-socket-tcp-bridge.py`).
- **Safer alternatives** (used when Traefik gets its own repo):
  1. Linux host + real `/var/run/docker.sock:ro` mount (what
     `docker-compose.traefik.prod.yml` already assumes).
  2. A restrictive API proxy exposing only `GET /containers*`,
     `GET /networks*` and events (all the docker provider needs).
  3. Drop the docker provider entirely and use Traefik's **file provider**
     with `url: http://api:8000`-style servers on a shared network — zero
     socket, static routes, no container discovery.

`exposedByDefault: false` is set in both static configs: only
`traefik.enable=true` labeled containers (api, dashboard, traefik itself,
future storefront) are ever exposed.

### Traefik dashboard
`api.insecure: false` in both static configs → it is never on a raw port.
It is reachable only via `Host(\`traefik.childnest.co.uk\`)` on websecure.
For anything beyond localhost add a `basic` auth middleware to the
`traefik-dashboard` router labels.

## 5. Environment requirements

All variable names, safe defaults and mode differences live in
`env/local.env.example` / `env/prod.env.example` (copy → `.env`,
git-ignored). Required (missing → `docker compose config` fails):

`SALEOR_SECRET_KEY`, `DATABASE_URL`, `PUBLIC_URL`, `DASHBOARD_URL`,
`DASHBOARD_API_URL`, `SALEOR_ALLOWED_HOSTS`, `SALEOR_ALLOWED_CLIENT_HOSTS`,
`DEFAULT_FROM_EMAIL` (+ `ACME_EMAIL` in prod mode).

Key Saleor production settings handled:
- `SECRET_KEY` — env (never in compose).
- `RSA_PRIVATE_KEY` — supplied via `RSA_PRIVATE_KEY_FILE=/app/saleor_rsa.pem`
  (PEM bind-mounted `:ro` from git-ignored `.secrets/saleor_rsa.pem`), same
  file for api **and** worker so worker-signed app JWTs validate on api.
- `ALLOWED_HOSTS` / `ALLOWED_CLIENT_HOSTS` / `CSRF_TRUSTED_ORIGINS` — the
  plain https domains in both modes (no port anywhere); plus the legacy
  `http://localhost:9001/8001` dev origins in the local sample.
- `DEBUG` — Saleor 3.23 has no DEBUG setting; the production posture comes
  from real secrets + `ALLOWED_CLIENT_HOSTS` set + `HTTP_IP_FILTER_ENABLED`.
- `HTTP_IP_FILTER_*` — local: `False`/loopback allowed (keeps local app dev
  working, same as `common.env`); prod sample: `True`.
- DB/cache/email: external Postgres via `postgres-net` (`postgres` host),
  internal Valkey (`cache:6379`), Mailpit (`mailpit:1025`) — none reachable
  from outside the Docker networks.
- URLs per mode exactly as specified (local URLs now carry **no port**,
  same form as production: `https://api.childnest.co.uk/…`).

## 6. What is deliberately NOT exposed

- No published ports on `api` / `dashboard` / `worker` / `cache` /
  `mailpit` in any new file (local overlay adds loopback-only Jaeger ports
  for testing convenience).
- Mailpit web UI (8025): not routed, not published. It is a temporary sink;
  for inspection add a temporary `127.0.0.1:8025:8025` mapping in the local
  overlay and remove it after.
- Jaeger: internal only; UI loopback-only in local mode; nothing in prod.
  To remove Jaeger later: delete its service + the `OTEL_*` env lines from
  the base file (Saleor's exporter failures are non-fatal).
- Valkey: no auth in this phase (same as dev stack, private bridge network).
  To add later: mount a `valkey.conf` with `requirepass` (or start
  `valkey-server --requirepass …`) and put `redis://:pass@cache:6379/…` in
  `CACHE_URL` / `CELERY_BROKER_URL` + worker env. Persistence =
  `saleor-cache` volume kept as-is.
- Media volume `saleor-media` is unchanged (api+worker, `/app/media`).
  Backup = back up that Docker volume + the Postgres DB (the DB lives in the
  external infrastructure project).

## 7. Validation performed (no services started/stopped/recreated)

| Check | Command (abridged) | Result |
|---|---|---|
| Original compose unchanged | `git diff docker-compose.yml` | empty |
| Original still parses | `docker compose -f docker-compose.yml config --quiet` | OK |
| Base prod config | `--env-file env/local.env.example -f docker-compose.prod.yml config --quiet` | OK |
| Local stack config | `+ -f docker-compose.traefik.local.yml` | OK |
| Prod stack config | `--env-file env/prod.env.example -f … -f … .prod.yml` | OK |
| Required-var enforcement | env file without `SALEOR_SECRET_KEY` | fails with clear message |
| Local published ports | `config` grep | only 127.0.0.1:80/443 + loopback Jaeger |
| Prod published ports | `config` grep | only 80, 443 |
| API/worker image consistency | `config` grep | both `admincareout/kidl:saleor-api-1.0` |
| Celery command preserved | diff of `command:` lines | byte-identical incl. scheduler |
| No postgres service | `grep -i postgres compose files` | none |
| Valkey/mailpit/jaeger not published | `config` grep | no non-loopback app ports (jaeger: loopback local only) |
| Cert covers 4 domains | `openssl x509 -ext subjectAltName` | all 4 SANs present |
| Key matches cert | public-key hash compare | MATCH |
| Keys git-ignored | `git check-ignore` | `.pem` + key + `.env` + `.secrets/` all ignored |
| Root CA key untouched | `ls %LOCALAPPDATA%\mkcert` | still outside repo, never copied |
| Engine reachability (for bridge) | throwaway container → `host.docker.internal:23750` → `GET /_ping` | 200 |
| Ports 80/443 free on host (before binding) | `netstat` | nothing listening; no container published them |

Follow-up revalidation (after switching local mode to 127.0.0.1:80/443 and
removing the storefront domains from the prod ACME `domains:` list):
both compose combinations re-parsed OK; local published ports are exactly
127.0.0.1:80/443 (+ loopback Jaeger), prod exactly 80/443; ACME requests
api + dashboard only.

All `docker compose` commands above used `config` only — no `up/down/
restart/create`.

## 8. Manual runbook — RSA key, database test, local start

Nothing here was executed in the configuration task; these are the exact
commands to run when you are ready to start the platform.

### 8.1 RSA private key (PowerShell, from the repo root)

Required: 2048-bit RSA, PKCS#8 PEM (the `BEGIN PRIVATE KEY` header that
`openssl genpkey` produces). File location: `.secrets/saleor_rsa.pem`
(git-ignored). **Do not display the key contents.**

```powershell
# (1) check openssl is available (Git for Windows provides it; if the
#     first command is empty, install Git/openssl first)
Get-Command openssl

# (2) generate the key (2048-bit RSA, PKCS#8 PEM)
New-Item -ItemType Directory -Force .secrets | Out-Null
openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 `
    -out .secrets/saleor_rsa.pem

# (3) verify: key is parseable + 2048 bits + header is PKCS#8
& openssl pkey -in .secrets/saleor_rsa.pem -noout -text |
    Select-Object -First 2          # expect: "Private-Key: (2048 bit,
#                                            2 primes)"
Get-Content .secrets/saleor_rsa.pem -TotalCount 1
                                # expect: "-----BEGIN PRIVATE KEY-----"
```

Both the **api** and the **worker** services bind-mount this exact file
read-only (`./.secrets/saleor_rsa.pem:/app/saleor_rsa.pem:ro`) and point
`RSA_PRIVATE_KEY_FILE=/app/saleor_rsa.pem` at it — verified in the composed
config, so tokens signed by the worker validate at the API.

### 8.2 PostgreSQL read-only connectivity test (manual, later)

No migration is run. From the host (uses a disposable `postgres:18` client
container with the same network + credentials the stack uses):

```bash
docker run --rm --network saleor-backend-tier \
  -e PGHOST=postgres -e PGUSER=saleor -e PGPASSWORD=saleor -e PGDATABASE=saleor \
  postgres:18-alpine psql -tAc "SELECT version(); SELECT count(*) FROM information_schema.tables WHERE table_schema='public';"
```

Assumptions encoded in the stack: host `postgres`, db `saleor`,
user `saleor`/`saleor` (per the still-running, working dev stack — do not
change these without checking where the external `infrastructure-postgres`
project lives).

### 8.3 Exact sequence to start the LOCAL platform later

```bash
# 0. (Windows editor as admin) add to C:\Windows\System32\drivers\etc\hosts:
#    127.0.0.1 api.childnest.co.uk
#    127.0.0.1 dashboard.childnest.co.uk
#    127.0.0.1 store-fe.childnest.co.uk   # optional; cert covers it
#    127.0.0.1 shop.childnest.co.uk        # optional; cert covers it
#    127.0.0.1 traefik.childnest.co.uk     # optional; traefik dashboard

# 1. env + key (once): see §8.1
Copy-Item env\local.env.example .env   # then edit .env (secrets!)

# 2. Docker Engine API bridge for the traefik docker provider (WSL),
#    in a separate terminal — must stay running while traefik runs:
wsl -d Ubuntu-26.04 -- python3 \
  C:/imran/projects/saleor-ecommerce/saleor-platform/traefik/host-services/dockerd-socket-tcp-bridge.py

# 3. start (bash or pwsh from repo root)
docker compose --env-file .env \
  -f docker-compose.prod.yml \
  -f docker-compose.traefik.local.yml up -d

# 4. test
curl -sS https://api.childnest.co.uk/graphql/ -d '{"query":"{ version { version displayName } }"}'
curl -sSI  https://dashboard.childnest.co.uk/ | Select-String -Pattern "^HTTP|^strict-transport"
# browser: https://dashboard.childnest.co.uk/ (login with Saleor admin creds)

# 5. stop (bridge too)
docker compose --env-file .env -f docker-compose.prod.yml \
  -f docker-compose.traefik.local.yml down --remove-orphans
wsl -d Ubuntu-26.04 -- pkill -f dockerd-socket-tcp-bridge.py
```

## 8. Extracting Traefik to its own repo later

The design keeps Traefik self-contained in `traefik/` + its overlay, so
extraction is mechanical:

1. Copy `traefik/` (static, dynamic, host-services) into the new repo.
   Copy the two Traefik overlays minus the Saleor service labels.
2. Move the Traefik **labels** from Saleor services into the Traefik repo as
   a `docker-compose` override applied *outside* Saleor (e.g. a small
   `traefik/labels/*.yml` consumed by `docker compose -f` per service), OR
   switch the provider to **file provider** with host-based servers
   (`http://api:8000` etc. — works because both projects can join the same
   external networks). File provider = no socket, no labels, full
   independence (recommended end state).
3. The Saleor side only ever needs: its services on `saleor-proxy-net`
   (make it `external: true` in the Saleor file once Traefik's project
   creates it first — one-line change) and its PUBLIC/DASHBOARD URLs.
   Nothing else in the Saleor apps changes.
4. On the Traefik host, replace the TCP bridge with a `:ro` socket mount
   (or drop sockets per step 2), keep `exposedByDefault: false`, keep the
   dashboard on its own hostname, and (prod) keep the ACME volume + email
   via env.

## 9. Outstanding decisions / notes

1. `store-fe.childnest.co.uk` purpose — decision belongs to the **future
   storefront task** (section 3); nothing in this phase depends on it.
2. `DEFAULT_FROM_EMAIL` / real SMTP provider for production (Mailpit is a
   temporary sink; production needs a real `EMAIL_URL`).
3. App installs under the domain setup: the Dummy Payment App manifest URL
   and `APP_IFRAME_BASE_URL` are `localhost`-based; under
   `https://dashboard.childnest.co.uk` the iframe app URL will need
   review (localhost app from a domain origin is a mixed/CSRF boundary).
   The dev stack (unchanged) remains the place for local app development
   until this is sorted.
4. `HTTP_IP_FILTER_ENABLED=True` (prod) blocks loopback-origin mutations;
   if you keep testing local apps against the *domain* stack, temporarily
   set `False` like the dev stack.
5. Valkey auth + Postgres credential hygiene for real production (kept at
   current levels here per scope).
6. Certificate expiry: the mkcert cert is valid until 31 Jan 2029; no
   renewal action needed for local use.
