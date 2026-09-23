import hashlib
import hmac

import pytest

from app.comments import classify_comment, may_auto_reply
from app.security import verify_admin_key, verify_meta_signature
from app.state import TRANSITIONS
from app.approvals import ALLOWED_ACTIONS, queue_from_instagram
from app.database import ApprovalRequest, init_db, session_scope


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
