We want to run Saleor locally for the first time using this `saleor-platform` repository.

There is a Docker Compose file in the root of this repository. We want to use the existing Compose setup as the basis for our custom local development environment and make the minimum necessary modifications.

# Existing PostgreSQL Infrastructure

PostgreSQL is already running separately in Docker.

The existing PostgreSQL configuration is:

```yaml
postgres:
  image: postgres:18
```

The PostgreSQL Docker network is:

```yaml
postgres-net:
  external: true
```

A dedicated database and user have already been created:

```text
Database: saleor
User: saleor
Password: saleor
```

This is a local development/test environment.

## Important

Do **not** create or start the PostgreSQL service included in the original Saleor Platform Compose configuration.

The original Compose configuration may reference PostgreSQL 15. That service must not be used because PostgreSQL is already managed separately and is running PostgreSQL 18.

Do not downgrade, replace, recreate, or modify the existing PostgreSQL container.

The Saleor API must connect to the existing PostgreSQL container through the external Docker network:

```text
postgres-net
```

The API should use the PostgreSQL Docker hostname/service name discovered from the running environment. Inspect the running container before making assumptions.

Inside the Docker network, normally use PostgreSQL's internal port rather than the host-mapped port.

---

# Docker Networks

We want all Docker networks used by this custom Saleor development environment to be **external networks**.

Do not allow Docker Compose to automatically create project-prefixed networks.

Instead:

1. Identify all networks required by the Saleor Platform Compose setup.
2. Provide separate Docker commands to create those networks.
3. Modify the Compose file so all required networks are declared as:

```yaml
external: true
```

For example:

```yaml
networks:
  saleor-backend-tier:
    external: true

  postgres-net:
    external: true
```

Do not create the networks automatically through Compose.

The required network creation commands should be provided separately, for example:

```bash
docker network create saleor-backend-tier
```

Do not recreate `postgres-net` if it already exists.

---

# API Network Configuration

The Saleor API service should join both:

```text
saleor-backend-tier
```

and:

```text
postgres-net
```

This allows the API to:

- Communicate with internal Saleor services.
- Connect to the externally managed PostgreSQL container.

Inspect the existing PostgreSQL container to verify its hostname/network aliases.

Use:

```bash
docker ps
docker network inspect postgres-net
docker inspect <postgres-container>
```

before finalizing the configuration.

---

# Existing Services

Before making changes, inspect:

- `README.md` in the repository root.
- The root Docker Compose file(s).
- `.env` files.
- `.env.example` files.
- Existing network definitions.
- Existing service dependencies.

Understand how the upstream Saleor Platform repository is intended to run before modifying it.

Preserve the existing architecture and make the smallest practical changes.

---

# Supporting Services

Do not assume PostgreSQL is the only dependency.

Keep all required Saleor services unless there is a clear reason to change them.

Check the existing Compose configuration for services such as:

- API
- Worker / Celery
- Dashboard
- Redis or Valkey
- Mailpit
- Jaeger or tracing services
- Other Saleor development dependencies

Only remove/disable the PostgreSQL service because PostgreSQL is externally managed.

Do not replace Redis/Valkey or other dependencies unless necessary.

---

# Environment Configuration

Update the appropriate environment configuration so Saleor uses:

```text
Database name: saleor
Database user: saleor
Database password: saleor
Database host: <actual PostgreSQL Docker hostname>
Database port: <PostgreSQL internal port>
```

Determine the actual hostname from the Docker environment.

Do not use `localhost` for the database host from inside the Saleor API container.

---

# Required Workflow

## Step 1 — Inspect

Before editing anything, inspect:

```bash
docker ps
docker network ls
docker network inspect postgres-net
```

Also inspect the PostgreSQL container:

```bash
docker inspect <postgres-container>
```

Then inspect:

- `README.md`
- Root Compose file(s)
- `.env` files
- Network definitions
- Service dependencies

---

## Step 2 — Report Before Changes

Briefly report:

1. The existing PostgreSQL container.
2. PostgreSQL version.
3. PostgreSQL hostname/network alias.
4. Networks currently used.
5. Networks required by Saleor.
6. Which external networks need to be created manually.

---

## Step 3 — Create Network Commands

Provide separate commands for creating all missing Saleor networks.

For example:

```bash
docker network create saleor-backend-tier
```

Check whether each network already exists before suggesting its creation.

Do not recreate:

```text
postgres-net
```

because it already exists.

---

## Step 4 — Modify Docker Compose

Modify the Compose configuration so:

- The upstream PostgreSQL service is disabled/removed from this custom local setup.
- The Saleor API connects to the existing PostgreSQL 18 container.
- The API joins `saleor-backend-tier`.
- The API joins `postgres-net`.
- Other required Saleor services remain functional.
- All Compose networks are declared as external networks.
- Docker Compose does not automatically create project-prefixed networks.

Preserve the upstream Compose structure wherever possible.

---

## Step 5 — Validate

Run:

```bash
docker compose config
```

Verify:

- No PostgreSQL 15 service is started.
- No duplicate PostgreSQL container will be created.
- All external networks are correctly declared.
- Environment variables are correct.
- Service dependencies remain valid.
- No obvious port conflicts exist.

---

## Step 6 — Start Saleor

Start the Saleor environment.

Do not modify unrelated application source code unless absolutely necessary.

---

## Step 7 — Verify

Verify that:

1. The Saleor API starts successfully.
2. The Saleor API connects to the existing PostgreSQL 18 database.
3. The `saleor` database is used.
4. Database migrations/setup complete successfully.
5. Required supporting services are healthy.
6. The Dashboard/API can be accessed.

---

# Important Constraints

- This is a local development/test environment.
- PostgreSQL is externally managed.
- PostgreSQL version is 18.
- Do not create another PostgreSQL container.
- Do not use the upstream PostgreSQL 15 service.
- Do not modify the existing PostgreSQL container.
- Do not delete existing Docker networks or volumes.
- `postgres-net` already exists and is external.
- All Saleor Compose networks should be external.
- Provide separate Docker commands to create missing networks.
- Do not rewrite the entire Compose configuration unnecessarily.
- Prefer minimal, understandable changes.
- Preserve compatibility with upstream Saleor Platform where possible.

---

# Documentation

Use the repository's root `README.md` as the primary reference.

If additional information is required, consult:

<https://docs.saleor.io/quickstart/running-locally>

Prefer repository-specific documentation when it conflicts with generic documentation.

---

# Final Output

When finished, provide:

## 1. Infrastructure discovered

- PostgreSQL container name
- PostgreSQL version
- PostgreSQL hostname
- PostgreSQL networks

## 2. Network setup

List all required external networks and provide the commands needed to create any missing networks.

## 3. Files changed

For every modified file:

- File name
- What changed
- Why

## 4. Final configuration

Explain how the Saleor API connects to:

- PostgreSQL
- Redis/Valkey
- Other internal services

## 5. Commands

Provide the exact commands to:

```bash
# Create required networks
# Start the Saleor environment
# Stop the Saleor environment
# View logs
```

## 6. URLs

Provide the URLs and ports for the running Saleor services.

## 7. Remaining manual steps

Clearly identify anything that still needs to be done before Saleor is ready for use.
