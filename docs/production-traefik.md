# Saleor production-style compose + Traefik

Configuration, local TLS and validation notes for the production-style
stack. **Nothing here has been deployed; the original `docker-compose.yml`
(local dev stack) is untouched and all running containers were left alone.**

## 1. Files and how the modes combine

| File | Purpose |
|---|---|
| `docker-compose.yml` | **Original dev stack — unchanged.** |
| `docker-compose.prod.yml` | Base production-style stack: `api`, `worker`, `dashboard`, `cache` (Valkey), `jaeger` (temporary), `mailpit` (temporary). No Traefik, **no published application ports**. |
| `docker-compose.traefik.local.yml` | Overlay: Traefik **local** mode (mkcert, 127.0.0.1:8080/8443), route labels for the two live domains, Jaeger loopback ports. |
| `docker-compose.traefik.prod.yml` | Overlay: Traefik **production** mode (Let's Encrypt ACME HTTP-01, public 80/443), same route labels. |
| `traefik/static/local/traefik.yaml` | Traefik static config, local mode (ports 8080/8443, HTTP→HTTPS redirect, file + docker providers, dashboard off-port). |
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
https://api.childnest.co.uk:8443/graphql/
https://dashboard.childnest.co.uk:8443/
https://shop.childnest.co.uk:8443/          (only once storefront exists)
https://store-fe.childnest.co.uk:8443/      (only once that service exists)
```

## 3. Domains & services mapping

| Domain | Service | Status |
|---|---|---|
| `api.childnest.co.uk` | `api` (container 8000) | **Configured** |
| `dashboard.childnest.co.uk` | `dashboard` (container 80) | **Configured** |
| `shop.childnest.co.uk` | Paper storefront (future image) | cert only; routing prepared (commented) |
| `store-fe.childnest.co.uk` | ??? — see below | cert only; no routing |

### `store-fe.childnest.co.uk` — needs your input
There is **no service in any repo here that corresponds to `store-fe`**:
the only storefront is `storefront-paper` (Next.js, port 3000), and the
other running services are Medusa/Strapi (separate project). I did not
invent a route for it. Two sensible readings:

1. It is a **reserved alias** for the Paper storefront (in which case I can
   add a second rule `Host(\`shop...\`) || Host(\`store-fe...\`)` to the same
   future router), or
2. It is a **second frontend** (e.g. the Medusa-style `medusa_storefront`
   referenced in old comments) that will get its own service/image later.

**Decision needed from you:** which frontend is `store-fe.childnest.co.uk`
for? Until then it has a valid certificate but no backing service (requests
will 404 in Traefik).

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

> **Two builds are required** (local vs production) because the public API
> URL is compiled into the client bundle: local builds bake
> `https://api.childnest.co.uk:8443/graphql/`, production builds bake
> `https://api.childnest.co.uk/graphql/`. A runtime env var cannot change a
> compiled `NEXT_PUBLIC_*` value.

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
- `ALLOWED_HOSTS` / `ALLOWED_CLIENT_HOSTS` / `CSRF_TRUSTED_ORIGINS` — per
  mode (local includes `:8443` hosts and legacy localhost dev URLs).
- `DEBUG` — Saleor 3.23 has no DEBUG setting; the production posture comes
  from real secrets + `ALLOWED_CLIENT_HOSTS` set + `HTTP_IP_FILTER_ENABLED`.
- `HTTP_IP_FILTER_*` — local: `False`/loopback allowed (keeps local app dev
  working, same as `common.env`); prod sample: `True`.
- DB/cache/email: external Postgres via `postgres-net` (`postgres` host),
  internal Valkey (`cache:6379`), Mailpit (`mailpit:1025`) — none reachable
  from outside the Docker networks.
- URLs per mode exactly as specified (local URLs carry `:8443`).

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
| Local published ports | `config` grep | only 127.0.0.1:8080/8443 + loopback Jaeger |
| Prod published ports | `config` grep | only 80, 443 |
| API/worker image consistency | `config` grep | both `admincareout/kidl:saleor-api-1.0` |
| Celery command preserved | diff of `command:` lines | byte-identical incl. scheduler |
| No postgres service | `grep -i postgres compose files` | none |
| Valkey/mailpit/jaeger unpublishered | `config` grep | no published ports (jaeger: loopback local only) |
| Cert covers 4 domains | `openssl x509 -ext subjectAltName` | all 4 SANs present |
| Key matches cert | public-key hash compare | MATCH |
| Keys git-ignored | `git check-ignore` | `.pem` + key + `.env` + `.secrets/` all ignored |
| Root CA key untouched | `ls %LOCALAPPDATA%\mkcert` | still outside repo, never copied |
| Engine reachability (for bridge) | throwaway container → `host.docker.internal:23750` → `GET /_ping` | 200 |

All `docker compose` commands above used `config` only — no `up/down/
restart/create`.

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

1. `store-fe.childnest.co.uk` purpose (section 3) — needs your answer.
2. `DEFAULT_FROM_EMAIL` / real SMTP provider for production (Mailpit is a
   temporary sink; production needs a real `EMAIL_URL`).
3. App installs under the domain setup: the Dummy Payment App manifest URL
   and `APP_IFRAME_BASE_URL` are `localhost`-based; under
   `https://dashboard.childnest.co.uk:8443` the iframe app URL will need
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
