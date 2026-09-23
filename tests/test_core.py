import hashlib
import hmac
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.comments import classify_comment, may_auto_reply
from app.security import verify_admin_key, verify_meta_signature
from app.state import TRANSITIONS
from app.approvals import ALLOWED_ACTIONS, create_approval, decide, queue_from_instagram, set_proposed_text
from app.database import ApprovalRequest, init_db, session_scope
from app import executor


def test_signature_verification():
    body, secret = b'{"ok":true}', "secret"
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    assert verify_meta_signature(body, f"sha256={digest}", secret)
    assert not verify_meta_signature(body, "sha256=bad", secret)


def test_admin_key_verification():
    assert verify_admin_key("secret", "secret")
    assert not verify_admin_key("wrong", "secret")
    assert not verify_admin_key(None, "secret")
    assert not verify_admin_key("secret", "")


@pytest.mark.parametrize(("text", "category"), [
    ("Bu qanday ishlaydi?", "QUESTION"),
    ("Zo'r video, rahmat", "PRAISE"),
    ("payment refund kerak", "NEEDS_HUMAN_REVIEW"),
    ("Follow me https://spam.test", "SPAM"),
])
def test_comment_classification(text, category):
    assert classify_comment(text) == category


def test_sensitive_comment_never_auto_replied():
    assert not may_auto_reply("NEEDS_HUMAN_REVIEW")


def test_state_machine_blocks_skips():
    assert "PUBLISHED" not in TRANSITIONS["UPLOADED"]
    assert "VALIDATING" in TRANSITIONS["UPLOADED"]


def test_public_actions_require_approval_queue():
    assert {"dm_reply", "comment_reply", "publish_post", "publish_reel"} <= ALLOWED_ACTIONS


def test_instagram_dm_is_queued_for_human_input():
    init_db()
    payload = {
        "entry": [{
            "messaging": [{
                "sender": {"id": "sender-1"},
                "message": {"mid": "test-mid-approval", "text": "Salom"},
            }]
        }]
    }
    queued = queue_from_instagram(payload)
    assert len(queued) in {0, 1}
    with session_scope() as session:
        row = session.query(ApprovalRequest).filter_by(source_ref="dm:test-mid-approval").one()
        assert row.action_type == "dm_reply"
        assert row.status == "PENDING_INPUT"
        assert row.proposed_text is None


class FakeInstagramClient:
    calls: list[tuple] = []

    def send_message(self, recipient_id, text):
        self.calls.append(("dm", recipient_id, text))
        return "dm-result"

    def reply_to_comment(self, comment_id, text):
        self.calls.append(("comment", comment_id, text))
        return "comment-result"


def test_approved_dm_is_executed_once(monkeypatch):
    init_db()
    FakeInstagramClient.calls = []
    monkeypatch.setattr(executor, "InstagramClient", FakeInstagramClient)
    request = create_approval("dm_reply", f"test-dm:{uuid4()}", {"sender_id": "ig-user-1"})
    set_proposed_text(request.id, "Assalomu alaykum")
    decide(request.id, True)

    result = executor.execute_approval(request.id)
    repeated = executor.execute_approval(request.id)

    assert result["status"] == "EXECUTED"
    assert repeated["status"] == "EXECUTED"
    assert FakeInstagramClient.calls == [("dm", "ig-user-1", "Assalomu alaykum")]


def test_future_content_stays_scheduled(monkeypatch):
    init_db()
    FakeInstagramClient.calls = []
    monkeypatch.setattr(executor, "InstagramClient", FakeInstagramClient)
    future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    request = create_approval(
        "publish_post",
        f"test-post:{uuid4()}",
        {"media_url": "https://example.com/image.jpg", "scheduled_at": future},
    )
    set_proposed_text(request.id, "Test caption")
    decide(request.id, True)

    result = executor.execute_approval(request.id)

    assert result["status"] == "SCHEDULED"
    assert FakeInstagramClient.calls == []


def test_echo_dm_is_not_queued():
    init_db()
    payload = {"entry": [{"messaging": [{
        "sender": {"id": "self"},
        "message": {"mid": f"echo-{uuid4()}", "text": "sent", "is_echo": True},
    }]}]}
    assert queue_from_instagram(payload) == []
