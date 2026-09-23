# Instagram Automation

Production-oriented MVP for a safe Reels workflow. It accepts raw MP4/MOV/M4V video, detects duplicates by SHA-256, validates with FFprobe, renders a 1080×1920 H.264/AAC Reel, stores persistent job state, creates a dry-run content package, verifies Meta webhook signatures, and classifies risky comments for human review.

Public actions are disabled by default. `AUTO_PUBLISH=false` and `AUTO_REPLY_COMMENTS=false` remain mandatory until a dry run and one controlled live test pass.

## Owner approval via Telegram

DM replies, comment replies, posts, and Reels are always placed in an approval queue. The Telegram approval bot asks the owner to write the exact reply/caption, then shows a separate Confirm/Reject step. Approval does not bypass the action queue, and no public action is performed without an explicit owner decision.

Configure `TELEGRAM_BOT_TOKEN` and `TELEGRAM_OWNER_CHAT_ID` only through the hosting provider's secret-variable UI. Never commit or paste the bot token into chat.

## Run

```bash
python3 -m pip install -e '.[dev]'
cp .env.example .env
python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open `/docs`, `/health`, `/ready`, or `/status`.

Dry-run a local video:

```bash
python3 -m app.cli /absolute/path/video.mp4
```

## Current boundary

Local video processing, state management, duplicate prevention, API health, webhook authenticity, and comment triage are implemented and testable. Live transcription, publishing, replies, analytics, and cloud deployment require owner-approved provider credentials and a public HTTPS deployment. The service never pretends these integrations are active when credentials are absent.
