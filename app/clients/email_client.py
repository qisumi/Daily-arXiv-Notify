from __future__ import annotations

import smtplib
from email.message import EmailMessage
from email.utils import formataddr
from pathlib import Path

from app.config import EmailSettings


class EmailClient:
    def __init__(self, settings: EmailSettings) -> None:
        self.settings = settings

    def send_digest(
        self,
        *,
        subject: str,
        markdown_body: str,
        html_body: str,
        attachments: list[Path] | None = None,
    ) -> str | None:
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = formataddr((self.settings.from_name, self.settings.from_address))
        msg["To"] = ", ".join(self.settings.recipients)
        msg.set_content(markdown_body)
        msg.add_alternative(html_body, subtype="html")

        for attachment in attachments or []:
            msg.add_attachment(
                attachment.read_bytes(),
                maintype="text",
                subtype="markdown",
                filename=attachment.name,
            )

        with smtplib.SMTP(
            self.settings.smtp_host,
            self.settings.smtp_port,
            timeout=60,
        ) as smtp:
            if self.settings.smtp_use_tls:
                smtp.starttls()
            if self.settings.smtp_username:
                smtp.login(self.settings.smtp_username, self.settings.smtp_password)
            send_result = smtp.send_message(msg)
        return None if not send_result else str(send_result)
