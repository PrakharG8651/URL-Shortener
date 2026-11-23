# URL Shortener

A simple URL shortener built with Flask, PostgreSQL, and Redis. Long URLs are stored in Postgres, encoded into short Base62 codes, and cached in Redis for fast redirects.

## Features

- Shorten long URLs into compact Base62 codes
- Redirect short codes back to the original URL
- Deduplicate: the same long URL always reuses the same short code
- Redis cache for fast redirects, with Postgres as the source of truth
- Fully containerized with Docker Compose

## Architecture

| Component | Role |
|-----------|------|
| **Flask** (`web`) | HTTP API — shorten URLs and handle redirects |
| **PostgreSQL** (`db`) | Permanent storage of URL mappings |
| **Redis** (`redis`) | Cache for short-code → long-URL lookups |

**Shorten flow:** request → check Postgres for existing URL → insert if new → Base62-encode the row ID → cache in Redis → return short URL.

**Redirect flow:** short code → Redis (cache hit) → or Postgres (cache miss, then warm Redis) → 302 redirect.

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/)
- [Docker Compose](https://docs.docker.com/compose/install/)

## Quick start

```bash
docker compose up --build
```

The API is available at `http://localhost:5000`.

Health check:

```bash
curl http://localhost:5000/health
```

To stop and remove containers (and wipe the database volume):

```bash
docker compose down -v
```

## API

### `POST /shorten`

Create a short URL (or return the existing one if the long URL was already shortened).

**Request**

```bash
curl -X POST http://localhost:5000/shorten \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com/very/long/path"}'
```

**Response (new URL — `201`)**

```json
{
  "short_code": "1",
  "short_url": "http://localhost:5000/1"
}
```

**Response (duplicate URL — `200`)**

Same body as above; the existing short code is reused.

### `GET /<short_code>`

Redirects to the original long URL (`302`). Returns `404` if the code is unknown.

```bash
curl -i http://localhost:5000/1
```

### `GET /health`

```json
{ "status": "healthy" }
```

## How short codes work

Each row in Postgres gets an auto-incrementing numeric `id`. That ID is converted to Base62 (`0-9`, `a-z`, `A-Z`) for a short alphanumeric code, and decoded back to the ID on redirect.

## Deduplication

`long_url` has a `UNIQUE` constraint. When you shorten a URL that already exists, the service returns the existing short code instead of inserting another row. Concurrent inserts for the same URL are handled with `ON CONFLICT`.

## Project structure

```
.
├── docker-compose.yml
├── README.md
└── app/
    ├── Dockerfile
    ├── app.py
    ├── init.sql
    └── requirements.txt
```

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `REDIS_HOST` | `redis` | Redis hostname |
| `REDIS_PORT` | `6379` | Redis port |
| `POSTGRES_HOST` | `db` | Postgres hostname |
| `POSTGRES_DB` | `urlshortener` | Database name |
| `POSTGRES_USER` | `postgres` | Database user |
| `POSTGRES_PASSWORD` | `postgres` | Database password |

These are set in `docker-compose.yml` for local development.
