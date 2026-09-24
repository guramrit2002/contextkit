# ADR 003 — Django for browser backend only

**Status:** Accepted

## Context

contextkit needs user sign-up, API key management, and analytics dashboards for the hosted version. Django is the team's primary framework and handles these well.

## Decision

Django is used exclusively for the browser-facing backend: onboarding, API keys, and analytics. It is not on the agent request path and agents do not depend on it.

## Consequences

- If Django is down, agents keep working.
- Django follows standard MVT with business logic in `services.py` per app.
- Django reads context tables through models declared with `managed = False` and never writes them.
- Django is not part of step 1. It is introduced in step 2 when the hosted version is built.
