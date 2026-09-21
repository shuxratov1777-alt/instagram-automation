# Operations

Use `/health` for process liveness, `/ready` for configuration readiness, and `/status` for queue counts. A video is successful only in `READY` during dry run or `PUBLISHED` during live operation; failures retain a human-readable reason.

Recommended alerts: failed jobs, webhook signature failures, credential expiry, worker outage, database outage, storage failure, and low disk space.

