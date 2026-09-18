"""Notifications for fills and stop-loss triggers.

Zero required dependencies: always logs, and optionally POSTs to a webhook
(Slack- or Discord-style incoming webhook) if ``NOTIFY_WEBHOOK_URL`` is set. The
payload includes both ``text`` (Slack) and ``content`` (Discord) so one URL works
for either.
"""
from __future__ import annotations

import json
import logging
import os
import urllib.request

log = logging.getLogger(__name__)


class Notifier:
    def __init__(self, webhook_url: str | None = None) -> None:
        self._webhook = webhook_url or os.getenv("NOTIFY_WEBHOOK_URL", "")

    def send(self, message: str) -> None:
        """Log always; also POST to the webhook when configured. Never raises."""
        log.info("NOTIFY: %s", message)
        if not self._webhook:
            return
        try:
            payload = json.dumps({"text": message, "content": message}).encode("utf-8")
            req = urllib.request.Request(
                self._webhook, data=payload, headers={"Content-Type": "application/json"}
            )
            urllib.request.urlopen(req, timeout=10)  # noqa: S310 - user-supplied webhook
        except Exception as e:  # noqa: BLE001 - a failed notification must not break trading
            log.warning("Notification webhook failed: %s", e)
