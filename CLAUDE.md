# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is an **enterprise retail recommendation system** combining TF-IDF content-based recommendations with Google Cloud Retail API. It features a hybrid recommender, multi-level Redis caching, multi-language Knowledge Base (ES/EN), and Shopify integration.

**Key Technologies:**
- FastAPI + Uvicorn (Python 3.9+)
- Google Cloud Retail API + Cloud Storage
- Redis (caching with 5-level fallback)
- PostgreSQL (via asyncpg) for Knowledge Base
- Shopify API integration
- Anthropic Claude API for AI conversations
- Prometheus + GCP Cloud Monitoring for metrics
- Alembic for database migrations

## Development Commands

### Running the Application

```bash
# Development with auto-reload
uvicorn src.api.main_unified_redis:app --reload --port 8000

# Production (Cloud Run compatible)
uvicorn src.api.main_unified_redis:app --host 0.0.0.0 --port ${PORT:-8080} --workers 1 --timeout-keep-alive 300
```

### Testing

```bash
# All tests with coverage
pytest

# Specific test categories
pytest -m unit              # Unit tests only
pytest -m integration       # Integration tests
pytest -m e2e               # End-to-end tests
pytest -m "not slow"        # Exclude slow tests
pytest -m "not debug"       # Exclude debug tests (for CI)

# Single test file
pytest tests/unit/test_service_factory.py -v

# With coverage report
pytest --cov-report=html
```

### Database Migrations (Alembic)

```bash
# Check current version
alembic current

# View migration history
alembic history --verbose

# Apply all pending migrations
alembic upgrade head

# Dry-run (generate SQL without applying)
alembic upgrade head --sql

# Revert last migration
alembic downgrade -1

# Create new migration
alembic revision -m "description"
```

### Deployment

```bash
# Deploy to Cloud Run (unified version with Redis)
.\scripts\deployment\gcp\deploy_unified_redis.ps1

# Docker local build
docker build -t retail-recommender -f Dockerfile.cloudrun .
docker run -p 8080:8080 --env-file .env retail-recommender
```

## Architecture Overview

### Entry Point

**Main Application:** `src/api/main_unified_redis.py`
- Uses FastAPI lifespan pattern for startup/shutdown
- Configures structured logging (JSON for GCP, human-readable for local)
- Integrates Prometheus metrics (M2) and GCP Cloud Monitoring (M3)
- Initializes ServiceFactory for dependency injection

### Core Architecture Patterns

**1. ServiceFactory Pattern** (`src/api/factories/service_factory.py`)
- Centralized dependency injection using singleton pattern with async locks
- Provides: RedisService, ProductCache, InventoryService, KnowledgeBase, Recommenders
- Thread-safe initialization with circuit breaker pattern for Redis
- Key method: `await ServiceFactory.get_redis_service()`

**2. Hybrid Recommender** (`src/api/core/hybrid_recommender.py`)
- Combines TF-IDF (content-based) + Google Cloud Retail API (collaborative)
- Configurable weighting via `CONTENT_WEIGHT` env var (0.0-1.0)
- Diversity-aware caching to prevent recommendation bubbles

**3. 5-Level Cache Fallback** (`src/api/core/product_cache.py`)
```
Level 1: Redis Cache
Level 2: Local Catalog
Level 3: Shopify API
Level 4: External Gateway
Level 5: Minimum Product (placeholder)
```

**4. Knowledge Base v2** (`src/api/core/knowledge_base_v2.py`)
- Multi-language support (ES/EN) with auto-detection via Accept-Language header
- 13 sub-intents: policy_return, policy_shipping, product_care, etc.
- Syncs with Shopify CMS via `ShopifyKBSyncService`

### Directory Structure

```
src/
├── api/
│   ├── main_unified_redis.py      # FastAPI entry point
│   ├── factories/
│   │   └── service_factory.py     # DI container
│   ├── core/
│   │   ├── config.py              # Pydantic settings
│   │   ├── product_cache.py       # 5-level cache
│   │   ├── hybrid_recommender.py  # Main recommender
│   │   ├── knowledge_base_v2.py   # Multi-lang KB
│   │   ├── intent_detection.py    # ML + rule-based intent detection
│   │   ├── mcp_conversation_handler.py  # AI conversation logic
│   │   └── logging_config.py      # Structured logging (H1)
│   ├── integrations/
│   │   └── shopify_client.py      # Shopify API client
│   ├── inventory/
│   │   └── inventory_service.py   # Stock management
│   └── mcp/                       # MCP (Model Context Protocol) services
├── recommenders/
│   ├── tfidf_recommender.py       # Content-based
│   ├── retail_api.py              # Google Cloud Retail
│   └── hybrid.py                  # Weighted combination
└── frontend/                      # Widget frontend (Node/Vite)

tests/
├── unit/                          # Component tests
├── integration/                   # Multi-component tests
├── e2e/                          # End-to-end tests
└── performance/                   # Load tests (Locust)

alembic/                          # Database migrations
scripts/                          # Utility scripts
docs/                            # Architecture docs
config/markets/                  # Market-specific configs (ES, MX, US)
```

### Key Configuration Files

**Environment Variables** (`.env`):
```bash
# Core
GOOGLE_PROJECT_NUMBER, GOOGLE_LOCATION, GOOGLE_CATALOG, GOOGLE_SERVING_CONFIG
API_KEY

# Shopify
SHOPIFY_SHOP_URL, SHOPIFY_ACCESS_TOKEN

# Redis Cache
USE_REDIS_CACHE=true, REDIS_HOST, REDIS_PORT, REDIS_PASSWORD, REDIS_SSL

# Database (PostgreSQL)
DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME, DB_SSL

# Claude/Anthropic
ANTHROPIC_API_KEY, CLAUDE_MODEL_TIER, CLAUDE_TIMEOUT

# Features
DEBUG, METRICS_ENABLED, EXCLUDE_SEEN_PRODUCTS, DEFAULT_CURRENCY
LOG_LEVEL, LOG_JSON_FORMAT
```

**pytest.ini:**
- Async mode: `auto` (no need for @pytest.mark.asyncio)
- Coverage threshold: 40% (incrementing to 70%)
- Test markers: unit, integration, e2e, slow, redis, shopify, google, smoke, performance, kb, debug

## Key Implementation Details

### Redis Singleton Thread-Safety

The `ServiceFactory` uses async locks for singleton initialization:
```python
_redis_lock: Optional[asyncio.Lock] = None
_redis_service: Optional[RedisService] = None

@classmethod
async def get_redis_service(cls) -> RedisService:
    async with cls._get_redis_lock():
        if cls._redis_service is None:
            cls._redis_service = await create_redis_service()
        return cls._redis_service
```

### Intent Detection System

**Hybrid approach** (`src/api/core/intent_detection.py`):
- Rule-based patterns for common intents (fast, deterministic)
- ML classifier (scikit-learn) for complex cases
- Confidence threshold determines which to use
- 13 sub-intents across 4 categories: policies, products, account, general

### Multi-Language Knowledge Base

Auto-detection priority:
1. Explicit `language` query parameter
2. `Accept-Language` header (RFC 7231)
3. Browser language from user agent
4. Default: Spanish (es)

### Structured Logging (H1)

Configured in `main_unified_redis.py`:
- Local: Human-readable format
- Production (Cloud Run): JSON format for GCP Cloud Logging
- Use `structlog.get_logger(__name__)` for all logging
- Key fields: timestamp, level, event, module, metadata

### Testing Best Practices

- Use `pytest -m debug` for development/debug tests
- Use `pytest -m "not debug"` for CI/CD
- E2E tests require full environment (Redis, PostgreSQL)
- Mock external APIs in unit tests
- Coverage reports in `htmlcov/`

### Common Development Tasks

**Adding a new endpoint:**
1. Define Pydantic models in `src/api/core/models.py` or inline
2. Add route in `main_unified_redis.py` with proper tags
3. Use ServiceFactory for dependencies: `await ServiceFactory.get_X_service()`
4. Add tests in `tests/unit/` or `tests/integration/`

**Adding a database migration:**
1. Write SQL explicitly in `alembic/versions/`
2. Use `op.execute()` for DDL
3. Test with `alembic upgrade head --sql` (dry-run)
4. Apply with `alembic upgrade head`

**Modifying intent detection:**
- Edit `src/api/core/intent_detection.py`
- Update patterns in `RULE_PATTERNS` dictionary
- Retrain ML model if needed (see `models/intent_classifier/`)

## Important Notes

- **Pydantic v2**: Use `pydantic-settings` for `BaseSettings`, not `pydantic.BaseSettings`
- **Redis Connection**: Always use `ServiceFactory.get_redis_service()` - never instantiate directly
- **Database**: Uses `asyncpg` at runtime, SQLAlchemy only for Alembic migrations
- **Docker**: Copies `static/` (widget) and `models/` (ML) directories - don't forget to update Dockerfile when adding new static assets
- **Cloud Run**: Requires `PORT` environment variable, uses single worker due to Python GIL
