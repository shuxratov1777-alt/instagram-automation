from __future__ import annotations

import re


SENSITIVE = re.compile(r"\b(sud|advokat|politsiya|to'lov|payment|refund|parol|password|token|hacked|tahdid|threat)\b", re.I)
SPAM = re.compile(r"(https?://|follow\s*me|dm\s*me|crypto|giveaway)", re.I)
ABUSE = re.compile(r"\b(idiot|stupid|ahmoq)\b", re.I)


def classify_comment(text: str) -> str:
    text = text.strip()
    if not text:
        return "UNKNOWN"
    if SENSITIVE.search(text):
        return "NEEDS_HUMAN_REVIEW"
    if SPAM.search(text):
        return "SPAM"
    if ABUSE.search(text):
        return "ABUSE"
    if "?" in text:
        return "QUESTION"
    if re.search(r"\b(rahmat|zo'r|ajoyib|thanks|great)\b", text, re.I):
        return "PRAISE"
    return "DISCUSSION"


def may_auto_reply(category: str) -> bool:
    return category in {"QUESTION", "PRAISE", "DISCUSSION"}

