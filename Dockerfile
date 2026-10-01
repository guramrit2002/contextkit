# syntax=docker/dockerfile:1
#
# Django image: admin, API key issuing, and the agent REST API. The MCP server is deployed
# separately (Render, ADR 027). Needs DATABASE_URL and DJANGO_SECRET_KEY at runtime; all
# configuration and secrets come from the environment.

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app \
    WEB_CONCURRENCY=2

WORKDIR /app
RUN useradd --create-home --uid 10001 contextkit

COPY requirements-api.txt ./
RUN pip install -r requirements-api.txt

# core (with its Alembic migrations) is needed by the Django views and the migrate step.
COPY core ./core
COPY alembic.ini ./
COPY api ./api

# The key and the SQLite opt-in only let settings import during the build; collectstatic
# never opens a database or uses the key.
RUN cd api && DJANGO_SECRET_KEY=collectstatic-only CONTEXTKIT_ALLOW_SQLITE=true \
    python manage.py collectstatic --noinput

USER contextkit
WORKDIR /app/api
EXPOSE 8000
CMD ["gunicorn", "api.wsgi:application", "--bind", "0.0.0.0:8000", "--access-logfile", "-"]
