# Architecture

The API receives a video or a storage-triggered job. The pipeline stores the immutable source, hashes it, validates it, moves through a guarded state machine, renders a Reel-safe asset, and creates a content package. SQLite is used for the local dry run; `DATABASE_URL` supports migration to managed PostgreSQL.

Meta webhooks are acknowledged only after HMAC verification and durable deduplication. Long-running comment analysis belongs in a background worker for production. Publishing is isolated behind `InstagramClient` so it can be tested independently.

Storage stages: `incoming`, `processing`, `ready`, `published`, `failed`, `archive`.

