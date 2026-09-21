# Deployment

Production needs a Python 3.12 service, FFmpeg/FFprobe, PostgreSQL, object storage with HTTPS-accessible media URLs, a worker process, and a public HTTPS hostname. Configure secrets only in the hosting provider's encrypted secret store.

## Railway baseline

The included `railway.toml` builds the Dockerfile, uses Railway's assigned `PORT`, checks `/health`, and restarts failed processes. Add managed PostgreSQL and set its generated `DATABASE_URL`. Raw and rendered videos should ultimately use object storage; do not rely on the container filesystem for production media retention.

Before enabling public actions:

1. Deploy with `AUTO_PUBLISH=false` and `AUTO_REPLY_COMMENTS=false`.
2. Run a real raw-video dry run.
3. Configure the Meta app, Instagram professional account, required permissions, callback URL, and webhook subscription using current official Meta documentation.
4. Run one controlled Reel test and one controlled comment test.
5. Enable each public action separately.
