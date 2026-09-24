# ADR 013 — user_id on every record from day one

**Status:** Proposed

## Context

Step 1 is single-user. Step 2 adds multiple users. Adding a `user_id` column to every table after the fact means migrating data and updating every query.

## Decision

Every context table row carries a `user_id` from the start. In step 1, this is a fixed value read from config (for example `"local"`). In step 2, it comes from the authenticated API key.

## Consequences

- No data migration when multi-user support is added.
- Every query in core already filters by `user_id`, so data isolation in step 2 is a config change, not a rewrite.
- Slightly more verbose queries in step 1, but the cost is negligible.
