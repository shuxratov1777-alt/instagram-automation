import hashlib
import hmac

import pytest

from app.comments import classify_comment, may_auto_reply
from app.security import verify_admin_key, verify_meta_signature
from app.state import TRANSITIONS


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
