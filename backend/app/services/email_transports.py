"""
Pluggable Email Transports (Phase 12)

Supports:
- Console / In-Memory Mock Transport (for local development & unit test assertions)
- SMTP Transport with STARTTLS / SSL & Attachment Support (standard mail servers)
- Resend Transport via async HTTP REST API
"""

from __future__ import annotations

import asyncio
import base64
import email.message
import logging
import mimetypes
import os
import smtplib
import uuid
from abc import ABC, abstractmethod
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class TransportSendResult:
    def __init__(self, success: bool, provider_message_id: str | None = None, error_message: str | None = None):
        self.success = success
        self.provider_message_id = provider_message_id
        self.error_message = error_message

    def __repr__(self) -> str:
        return f"<TransportSendResult success={self.success} id={self.provider_message_id} err={self.error_message}>"


class BaseEmailTransport(ABC):
    @abstractmethod
    async def send(
        self,
        recipient_email: str,
        subject: str,
        body_html: str,
        body_text: str | None = None,
        recipient_name: str | None = None,
        sender_email: str | None = None,
        sender_name: str | None = None,
        attachments: list[dict[str, Any]] | None = None,
    ) -> TransportSendResult:
        """Dispatches an email through this transport provider."""
        pass


class ConsoleEmailTransport(BaseEmailTransport):
    """
    Console & In-Memory Transport for testing and offline development.
    Stores dispatched messages for inspection in automated tests.
    """

    def __init__(self) -> None:
        self.sent_history: list[dict[str, Any]] = []

    async def send(
        self,
        recipient_email: str,
        subject: str,
        body_html: str,
        body_text: str | None = None,
        recipient_name: str | None = None,
        sender_email: str | None = None,
        sender_name: str | None = None,
        attachments: list[dict[str, Any]] | None = None,
    ) -> TransportSendResult:
        msg_id = f"mock-{uuid.uuid4().hex[:12]}"
        record = {
            "id": msg_id,
            "recipient_email": recipient_email,
            "recipient_name": recipient_name,
            "sender_email": sender_email or settings.DEFAULT_FROM_EMAIL,
            "sender_name": sender_name or settings.DEFAULT_FROM_NAME,
            "subject": subject,
            "body_html": body_html,
            "body_text": body_text,
            "attachments": attachments or [],
        }
        self.sent_history.append(record)
        logger.info(
            "EMAIL (console): to=%s subject=%s — not delivered; set EMAIL_PROVIDER=resend or smtp",
            recipient_email,
            subject,
        )
        return TransportSendResult(success=True, provider_message_id=msg_id)

    def clear(self) -> None:
        self.sent_history.clear()


class SMTPEmailTransport(BaseEmailTransport):
    """
    Standard RFC-compliant SMTP Transport with TLS/SSL and MIME attachment support.
    Executes in a threadpool executor to maintain FastAPI non-blocking async loops.
    """

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        user: str | None = None,
        password: str | None = None,
        use_tls: bool | None = None,
        use_ssl: bool | None = None,
    ) -> None:
        self.host = host or settings.SMTP_HOST
        self.port = port or settings.SMTP_PORT
        self.user = user or settings.SMTP_USER
        self.password = password or settings.SMTP_PASSWORD
        self.use_tls = use_tls if use_tls is not None else settings.SMTP_TLS
        self.use_ssl = use_ssl if use_ssl is not None else settings.SMTP_SSL

    def _send_sync(
        self,
        from_header: str,
        to_email: str,
        msg: MIMEMultipart,
    ) -> str:
        if self.use_ssl:
            server = smtplib.SMTP_SSL(self.host, self.port, timeout=15)
        else:
            server = smtplib.SMTP(self.host, self.port, timeout=15)

        try:
            if self.use_tls and not self.use_ssl:
                server.starttls()
            if self.user and self.password:
                server.login(self.user, self.password)
            server.sendmail(from_header, [to_email], msg.as_string())
            msg_id = msg.get("Message-ID", f"smtp-{uuid.uuid4().hex[:12]}")
            return msg_id
        finally:
            try:
                server.quit()
            except Exception:
                pass

    async def send(
        self,
        recipient_email: str,
        subject: str,
        body_html: str,
        body_text: str | None = None,
        recipient_name: str | None = None,
        sender_email: str | None = None,
        sender_name: str | None = None,
        attachments: list[dict[str, Any]] | None = None,
    ) -> TransportSendResult:
        try:
            from_addr = sender_email or settings.DEFAULT_FROM_EMAIL
            from_display = sender_name or settings.DEFAULT_FROM_NAME
            from_header = f"{from_display} <{from_addr}>"
            to_header = f"{recipient_name} <{recipient_email}>" if recipient_name else recipient_email

            msg = MIMEMultipart("mixed")
            msg["Subject"] = subject
            msg["From"] = from_header
            msg["To"] = to_header
            msg["Message-ID"] = f"<{uuid.uuid4()}@{self.host}>"

            alt_part = MIMEMultipart("alternative")
            if body_text:
                alt_part.attach(MIMEText(body_text, "plain", "utf-8"))
            alt_part.attach(MIMEText(body_html, "html", "utf-8"))
            msg.attach(alt_part)

            # Process secure attachments
            if attachments:
                for att in attachments:
                    file_path = att.get("path")
                    filename = att.get("filename", os.path.basename(file_path or "attachment.dat"))
                    if file_path and os.path.exists(file_path):
                        with open(file_path, "rb") as f:
                            part = MIMEApplication(f.read(), Name=filename)
                        part["Content-Disposition"] = f'attachment; filename="{filename}"'
                        msg.attach(part)

            msg_id = await asyncio.to_thread(self._send_sync, from_addr, recipient_email, msg)
            return TransportSendResult(success=True, provider_message_id=msg_id)
        except Exception as e:
            return TransportSendResult(success=False, error_message=str(e))


class ResendEmailTransport(BaseEmailTransport):
    """
    Resend REST API transport using HTTPX asynchronous client.
    """

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or settings.RESEND_API_KEY
        self.endpoint = "https://api.resend.com/emails"

    async def send(
        self,
        recipient_email: str,
        subject: str,
        body_html: str,
        body_text: str | None = None,
        recipient_name: str | None = None,
        sender_email: str | None = None,
        sender_name: str | None = None,
        attachments: list[dict[str, Any]] | None = None,
    ) -> TransportSendResult:
        if not self.api_key:
            return TransportSendResult(success=False, error_message="Resend API key is not configured.")

        from_addr = sender_email or settings.DEFAULT_FROM_EMAIL
        from_display = sender_name or settings.DEFAULT_FROM_NAME
        from_header = f"{from_display} <{from_addr}>"
        to_header = f"{recipient_name} <{recipient_email}>" if recipient_name else recipient_email

        payload: dict[str, Any] = {
            "from": from_header,
            "to": [to_header],
            "subject": subject,
            "html": body_html,
        }
        if body_text:
            payload["text"] = body_text

        # Process attachments for Resend API
        if attachments:
            encoded_attachments = []
            for att in attachments:
                file_path = att.get("path")
                filename = att.get("filename", os.path.basename(file_path or "attachment.dat"))
                if file_path and os.path.exists(file_path):
                    with open(file_path, "rb") as f:
                        b64 = base64.b64encode(f.read()).decode("utf-8")
                        encoded_attachments.append({"filename": filename, "content": b64})
            if encoded_attachments:
                payload["attachments"] = encoded_attachments

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                res = await client.post(self.endpoint, json=payload, headers=headers)
                if res.status_code in (200, 201):
                    data = res.json()
                    return TransportSendResult(success=True, provider_message_id=data.get("id"))
                else:
                    return TransportSendResult(
                        success=False,
                        error_message=f"Resend HTTP {res.status_code}: {res.text}",
                    )
        except Exception as e:
            return TransportSendResult(success=False, error_message=str(e))


# Shared singleton instance for in-process usage and tests
_CONSOLE_TRANSPORT = ConsoleEmailTransport()


def get_email_transport(provider: str | None = None) -> BaseEmailTransport:
    """Returns the configured email transport implementation."""
    prov = (provider or settings.EMAIL_PROVIDER).lower()
    if prov == "smtp":
        return SMTPEmailTransport()
    elif prov == "resend":
        return ResendEmailTransport()
    return _CONSOLE_TRANSPORT

