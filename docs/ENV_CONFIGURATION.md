# Environment Configuration Guide

## Overview

Contextkit now uses environment variables for configuration, loaded from `.env` file via `python-dotenv`.

## Files

### `.env.example`
Template file with all available configuration options and descriptions. Safe to commit to git.

**Use it to:**
- Understand all available settings
- Create your own `.env` file
- Document configuration options

### `.env`
**DO NOT COMMIT** - Contains actual values for your environment (already in `.gitignore`)

**Use it to:**
- Configure your local development environment
- Store sensitive values (database paths, API keys, etc.)
- Override defaults

## Environment Variables

### Core Settings

| Variable | Default | Purpose | Type |
|----------|---------|---------|------|
| `DEFAULT_USER_ID` | `default_user` | User ID for single-user mode (Step 1) | string |

### Database Configuration

| Variable | Default | Purpose |
|----------|---------|---------|
| `CONTEXTKIT_DB_PATH` | `./db.sqlite3` | Path to SQLite database |

**Examples:**
```bash
# Local project directory (default)
CONTEXTKIT_DB_PATH=./db.sqlite3

# Absolute path
CONTEXTKIT_DB_PATH=/data/contextkit.db

# Home directory
CONTEXTKIT_DB_PATH=~/.contextkit/contextkit.db
```

### Feature Flags

| Variable | Default | Purpose |
|----------|---------|---------|
| `REQUIRE_AUTH` | `False` | Reject tool calls without an API key (always on when `CONTEXTKIT_HOSTED=true`) |
| `GITHUB_MOCK` | unset | Local development only: answer GitHub calls locally (needs `DJANGO_DEBUG=true` and SQLite; see `web/README.md`) |

Secret redaction is always on; there is no setting to turn it off.

### Django Settings (Step 2+)

| Variable | Required | Purpose |
|----------|----------|---------|
| `DJANGO_SECRET_KEY` | Yes (if running Django) | Django secret key for cryptography |
| `DJANGO_DEBUG` | No | Debug mode (`True`/`False`) |
| `DJANGO_ALLOWED_HOSTS` | No | Comma-separated list of allowed hosts |

## Setup Instructions

### 1. Create `.env` from Template

```bash
cp .env.example .env
```

### 2. Update Values for Your Environment

```bash
# Edit .env with your values
nano .env
```

### 3. For Production

Never commit `.env` to git! Instead:

1. Copy `.env.example` to template
2. Store actual `.env` in secure location (CI/CD secrets, etc.)
3. Load at runtime from secure store

**Example for CI/CD:**
```bash
# GitHub Actions
- name: Create .env
  env:
    DJANGO_SECRET_KEY: ${{ secrets.DJANGO_SECRET_KEY }}
  run: |
    echo "DJANGO_SECRET_KEY=${DJANGO_SECRET_KEY}" > .env
    echo "DJANGO_DEBUG=False" >> .env
    # ... add other vars
```

## Loading Environment Variables

### Automatic Loading

The `.env` file is automatically loaded by:
- `api/api/settings.py` - Django settings
- `core/config.py` - Core configuration

### Manual Loading

```python
import os
from dotenv import load_dotenv

# Load from .env file
load_dotenv()

# Access variables
db_path = os.getenv('CONTEXTKIT_DB_PATH', './db.sqlite3')
```

## Configuration in Code

```python
from core.config import config, describe_core_database, resolve_database_url

user_id = config.get_default_user_id()
hosted = config.is_hosted()                 # CONTEXTKIT_HOSTED=true
key_required = config.auth_required()       # always True when hosted
url = resolve_database_url()                # DATABASE_URL (required, ADR 029)
print(describe_core_database())             # names the database without its URL
```

## Example Configurations

### Production (EC2 backend `.env`, Render environment)

```bash
DATABASE_URL='postgresql://…supabase…:5432/postgres?sslmode=require'   # required
CONTEXTKIT_HOSTED=true
DJANGO_SECRET_KEY='<generated, single-quoted>'   # quotes stop Compose expanding "$"
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS='localhost,127.0.0.1,.trycloudflare.com'
DJANGO_CSRF_TRUSTED_ORIGINS='https://*.trycloudflare.com'
DJANGO_CORS_ALLOWED_ORIGINS='https://<website>'
GITHUB_CLIENT_ID='…'
GITHUB_CLIENT_SECRET='…'
```

### Local development (SQLite and the GitHub mock)

```bash
export DATABASE_URL=""                 # empty, not unset: .env would fill it in
export CONTEXTKIT_ALLOW_SQLITE=true
export CONTEXTKIT_DB_PATH=~/.contextkit-local/core.sqlite3
export DJANGO_DB_PATH=~/.contextkit-local/django.sqlite3
export DJANGO_DEBUG=true GITHUB_MOCK=true
```

See `web/README.md` for the full local setup.

## Hardcoded Values Removed

### ✅ Before (Hardcoded)
```python
# core/models.py
user_id = Column(String(255), default="default_user")

# api/api/settings.py
SECRET_KEY = 'django-insecure-<redacted>'
DEBUG = True
ALLOWED_HOSTS = []
```

### ✅ After (Environment-based)
```python
# core/models.py
from core.config import config
user_id = Column(String(255), default=config.get_default_user_id)

# api/api/settings.py
SECRET_KEY = os.getenv('DJANGO_SECRET_KEY', 'dev-key')
DEBUG = os.getenv('DJANGO_DEBUG', 'False').lower() == 'true'
ALLOWED_HOSTS = os.getenv('DJANGO_ALLOWED_HOSTS', 'localhost').split(',')
```

## Accessing Configuration

### In Django

```python
import os
from django.conf import settings

# Environment variables are already loaded
debug_mode = settings.DEBUG
secret_key = settings.SECRET_KEY
allowed_hosts = settings.ALLOWED_HOSTS
```

## Best Practices

### ✅ DO

- ✅ Copy `.env.example` to `.env` for new environment
- ✅ Keep `.env` out of version control (it's in `.gitignore`)
- ✅ Document all settings in `.env.example`
- ✅ Use environment-specific values
- ✅ Rotate secrets in production regularly
- ✅ Store production secrets in secure location (CI/CD secrets, vault, etc.)

### ❌ DON'T

- ❌ Commit `.env` to git
- ❌ Hardcode sensitive values in code
- ❌ Use same secret in dev and production
- ❌ Leave DEBUG=True in production
- ❌ Share `.env` files via email or chat
- ❌ Store passwords in code comments

## Troubleshooting

### Environment Variables Not Loading

**Problem:** Changes to `.env` not reflected

**Solution:**
1. Restart the application
2. Ensure `.env` is in project root
3. Check file permissions: `chmod 644 .env`
4. Verify `python-dotenv` is installed: `pip install python-dotenv`

### Secret Key Error in Django

**Problem:** `DJANGO_SECRET_KEY` not set

**Solution:**
1. Generate a new key: 
   ```bash
   python -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())'
   ```
2. Add to `.env`:
   ```bash
   DJANGO_SECRET_KEY=<generated-key>
   ```

### Database Path Error

**Problem:** Database file not found

**Solution:**
1. Check `CONTEXTKIT_DB_PATH` in `.env`
2. Ensure directory exists and is writable
3. Use absolute paths or `~` for home directory

## Next Steps

1. ✅ Copy `.env.example` to `.env`
2. ✅ Update values for your environment
3. ✅ Ensure `.env` is in `.gitignore` (already done)
4. ✅ Test configuration loads correctly
5. ✅ Never commit `.env` to git

---

**Status:** ✅ Environment configuration fully implemented and documented
