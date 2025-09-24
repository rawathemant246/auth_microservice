# auth_microservice

Polyglot persistence FastAPI service that powers authentication, Google SSO, and fine-grained RBAC policy enforcement for the OneOrg platform. The service combines:

- **PostgreSQL** for transactional user, billing, and RBAC data.
- **MongoDB** for organization specific configuration documents.
- **pycasbin** to evaluate role/permission policies stored in Postgres.
- **Casdoor** (Google SSO) integration for federated login flows.

## Features

- FastAPI-based REST API with JWT authentication and Google SSO via Casdoor.
- Polyglot persistence: PostgreSQL for transactional data, MongoDB for organization settings.
- Alembic migrations including seeded RBAC roles/permissions.
- RBAC enforcement using pycasbin with policies pulled from Postgres.
- Taskiq worker for background jobs with RabbitMQ and Redis integration.
- Prometheus metrics endpoint and pre-configured Grafana dashboards.

## Quick start with Docker Compose

1. Copy the provided `.env` and adjust secrets as needed (JWT, Casdoor credentials, etc.).
2. Build images and pull dependencies:
   ```bash
   docker compose build
   ```
3. Apply the database schema and RBAC seed data:
   ```bash
   docker compose run --rm migrator
   ```
4. Bring up the API, worker, and monitoring stack (Prometheus & Grafana):
   ```bash
   docker compose up -d api taskiq-worker prometheus grafana
   ```
5. Tail logs or inspect health:
   ```bash
   docker compose logs -f api
   ```
6. Open the interactive docs at [http://localhost:8000/api/docs](http://localhost:8000/api/docs).

> **Tip:** `docker compose down -v` tears down the stack and removes persisted Postgres/Mongo volumes.

### Services started by the compose stack

| Service            | Container name                | Purpose                                    |
|--------------------|-------------------------------|--------------------------------------------|
| `api`              | `auth_microservice`           | FastAPI application serving REST endpoints |
| `taskiq-worker`    | `auth_microservice-worker`    | Background worker for Taskiq jobs          |
| `db`               | `auth_microservice-db`        | PostgreSQL 16 with application schema      |
| `mongo`            | `auth_microservice-mongo`     | MongoDB 6 for organization documents       |
| `redis`            | `auth_microservice-redis`     | Redis cache / Taskiq backend               |
| `rmq`              | `auth_microservice-rmq`       | RabbitMQ broker                            |
| `prometheus`       | `auth_microservice-prometheus`| Metrics collection (/metrics scrape)       |
| `grafana`          | `auth_microservice-grafana`   | Pre-provisioned Prometheus datasource      |

### Observability dashboards

- Prometheus UI: [http://localhost:9090](http://localhost:9090)
- Grafana UI: [http://localhost:3000](http://localhost:3000) (default credentials `admin` / `admin`).

Grafana automatically discovers the Prometheus datasource configured in `deploy/grafana/provisioning/datasources/datasource.yml`. Import any preferred FastAPI dashboards or create custom panels using the `Prometheus` datasource.

### Metrics endpoint

- FastAPI exposes metrics at `http://localhost:8000/metrics` (the same endpoint Prometheus scrapes by default).
- Update `deploy/prometheus/prometheus.yml` if you change the API port or add additional scrape targets.

### Prebuilt dashboards

- Grafana auto-loads the `Auth Microservice Overview` dashboard from `deploy/grafana/dashboards/auth_microservice_overview.json`.
- The dashboard appears under the *General* folder—duplicate it before customizing to keep the JSON source intact.

### Alerting rules

- Prometheus evaluates alert definitions in `deploy/prometheus/alerts.yml` (API down, high error rate, high latency).
- Extend the Prometheus configuration to wire these alerts into Alertmanager, Slack, PagerDuty, etc.
- After editing dashboards or alert rules, refresh the monitoring services:
  ```bash
  docker compose up -d prometheus grafana
  ```



## Environment variables

All configuration is driven through the `.env` file (autoloaded by docker-compose). Key variables:

| Variable | Description |
| --- | --- |
| `AUTH_MICROSERVICE_DB_*` | PostgreSQL connection details used by the API and migrator. |
| `AUTH_MICROSERVICE_MONGODB_URI` / `AUTH_MICROSERVICE_MONGODB_DATABASE` | Connection target for the Mongo document store. |
| `AUTH_MICROSERVICE_JWT_SECRET_KEY` / `USERS_SECRET` | Secrets for issuing/validating access tokens. Change for production. |
| `AUTH_MICROSERVICE_CASDOOR_*` | Casdoor endpoint and client credentials for Google SSO. |
| `GRAFANA_ADMIN_USER` / `GRAFANA_ADMIN_PASSWORD` | Override Grafana's admin credentials (defaults to `admin`/`admin`). |

Update these values before deploying to any shared environment. Casdoor itself is not part of this compose stack—you must supply credentials for your hosted Casdoor instance.

## Database migrations

Migrations are handled with Alembic. Typical workflows:

- **Apply migrations (already done in the quick start):** `docker compose run --rm migrator`
- **Create a new migration after model changes:**
  ```bash
  docker compose run --rm api alembic revision --autogenerate -m "describe change"
  docker compose run --rm migrator
  ```

## Local development without Docker

Poetry remains available for direct execution:

```bash
poetry install
poetry run python -m auth_microservice
```

You will need equivalent Postgres, Mongo, Redis, and RabbitMQ instances available locally and the `.env` updated to point to them.

## Testing

Run the test suite inside Docker:

```bash
docker compose run --rm api pytest -vv
```

Or locally after installing dependencies with Poetry:

```bash
pytest -vv
```

---

For additional project details (logging, task queues, etc.), explore the source under `auth_microservice/` or review configuration in `settings.py`.
