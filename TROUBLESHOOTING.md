# Troubleshooting

- `Video cannot be read by ffprobe`: the file is corrupt or unsupported.
- `FFmpeg rendering failed`: inspect codecs and available disk space.
- `Invalid signature`: confirm `META_APP_SECRET` and ensure the raw request body is unchanged.
- `Meta publishing is not configured`: set the required credentials and public base URL in the deployment secret manager.
- Duplicate upload returns the original job ID by design.

