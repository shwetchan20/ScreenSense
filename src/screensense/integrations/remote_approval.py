from __future__ import annotations

import re
import time
import uuid
from dataclasses import dataclass

import requests


def parse_approval_reply(text: str, request_id: str) -> bool | None:
    normalized = re.sub(r"\s+", " ", text.strip().lower())
    if request_id.lower() not in normalized:
        return None
    yes_tokens = ("yes", "approve", "allow", "ok", "okay")
    no_tokens = ("no", "deny", "reject", "cancel")
    if any(token in normalized for token in no_tokens):
        return False
    if any(token in normalized for token in yes_tokens):
        return True
    return None


@dataclass(slots=True)
class RemoteApprovalSettings:
    provider: str
    enabled: bool
    timeout_seconds: int
    poll_seconds: float
    telegram_bot_token: str
    telegram_chat_id: str


class RemoteApprover:
    def request_approval(self, *, action_description: str, reason: str) -> bool | None:
        raise NotImplementedError

    def notify(self, text: str) -> bool:
        raise NotImplementedError


class NoopRemoteApprover(RemoteApprover):
    def request_approval(self, *, action_description: str, reason: str) -> bool | None:
        _ = (action_description, reason)
        return None

    def notify(self, text: str) -> bool:
        _ = text
        return False


class TelegramRemoteApprover(RemoteApprover):
    def __init__(self, *, bot_token: str, chat_id: str, timeout_seconds: int, poll_seconds: float) -> None:
        self._token = bot_token.strip()
        self._chat_id = str(chat_id).strip()
        self._timeout_seconds = max(15, timeout_seconds)
        self._poll_seconds = max(1.0, poll_seconds)
        self._offset = 0

    def request_approval(self, *, action_description: str, reason: str) -> bool | None:
        if not self._token or not self._chat_id:
            return None
        request_id = uuid.uuid4().hex[:6].upper()
        sent = self._send_message(
            (
                "ScreenSense approval required\n"
                f"ID: {request_id}\n"
                f"Reason: {reason}\n"
                f"Action: {action_description}\n\n"
                f"Reply exactly: YES {request_id} or NO {request_id}"
            )
        )
        if not sent:
            return None

        deadline = time.time() + self._timeout_seconds
        while time.time() < deadline:
            decision = self._poll_for_decision(request_id)
            if decision is not None:
                return decision
            time.sleep(self._poll_seconds)
        self._send_message(f"Approval window expired for {request_id}. Action skipped.")
        return None

    def notify(self, text: str) -> bool:
        return self._send_message(text)

    def _send_message(self, text: str) -> bool:
        try:
            response = requests.post(
                f"https://api.telegram.org/bot{self._token}/sendMessage",
                json={"chat_id": self._chat_id, "text": text},
                timeout=15,
            )
            response.raise_for_status()
            return True
        except Exception:
            return False

    def _poll_for_decision(self, request_id: str) -> bool | None:
        try:
            response = requests.get(
                f"https://api.telegram.org/bot{self._token}/getUpdates",
                params={"offset": self._offset, "timeout": 0},
                timeout=15,
            )
            response.raise_for_status()
            payload = response.json()
        except Exception:
            return None

        for item in payload.get("result", []):
            update_id = int(item.get("update_id", 0))
            self._offset = max(self._offset, update_id + 1)
            message = item.get("message") or {}
            chat = message.get("chat") or {}
            if str(chat.get("id")) != self._chat_id:
                continue
            text = str(message.get("text") or "")
            parsed = parse_approval_reply(text, request_id)
            if parsed is not None:
                return parsed
        return None


def build_remote_approver(settings: RemoteApprovalSettings) -> RemoteApprover:
    if not settings.enabled:
        return NoopRemoteApprover()
    if settings.provider == "telegram":
        return TelegramRemoteApprover(
            bot_token=settings.telegram_bot_token,
            chat_id=settings.telegram_chat_id,
            timeout_seconds=settings.timeout_seconds,
            poll_seconds=settings.poll_seconds,
        )
    return NoopRemoteApprover()
