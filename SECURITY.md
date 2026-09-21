# Security

- No credentials are committed or stored in ordinary database tables.
- Upload extensions, size, FFprobe readability, and video-stream presence are validated.
- FFmpeg receives argument arrays; user input is never interpolated into a shell command.
- Source filenames are replaced with generated IDs.
- Webhook requests require `X-Hub-Signature-256` HMAC verification.
- Webhook events and source videos are deduplicated.
- Sensitive comments are routed to human review.
- Production admin endpoints must be placed behind platform authentication or an API gateway.

