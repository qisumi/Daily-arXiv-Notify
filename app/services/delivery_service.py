from __future__ import annotations

from datetime import datetime, timezone

from app.clients.email_client import EmailClient
from app.config import Settings
from app.models import RenderedDigest


class DeliveryService:
    def __init__(self, settings: Settings, email_client: EmailClient) -> None:
        self.settings = settings
        self.email_client = email_client

    def deliver(
        self,
        digest: RenderedDigest,
        *,
        dry_run: bool,
    ) -> tuple[str, datetime | None, str | None]:
        if dry_run:
            return "dry_run", None, None

        attachments = [digest.markdown_path] if self.settings.digest.attach_markdown else []
        provider_message_id = self.email_client.send_digest(
            subject=digest.subject,
            markdown_body=digest.markdown,
            html_body=digest.html,
            attachments=attachments,
        )
        return "sent", datetime.now(timezone.utc), provider_message_id
