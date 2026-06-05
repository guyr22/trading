"""Transactional email over SMTP (stdlib only).

Configured via env so credentials never live in code:
- SMTP_HOST       e.g. smtp.gmail.com
- SMTP_PORT       default 587 (STARTTLS)
- SMTP_USER       login / sender address
- SMTP_PASSWORD   password or app password
- SMTP_FROM       From header (defaults to SMTP_USER)
- SMTP_FROM_NAME  display name (default "Portfolio Tracker")

When host/user/password are absent the service reports enabled=False and send()
is a no-op, so the digest feature stays inert rather than erroring.
"""
import os
import smtplib
import socket
import ssl
from email.message import EmailMessage
from email.utils import formataddr

from core.logging import get_logger

logger = get_logger(__name__)


class _IPv4SMTP(smtplib.SMTP):
    """SMTP client that connects over IPv4 only.

    Container platforms such as Railway often advertise an IPv6 address with no
    working IPv6 route, so smtplib's default dual-stack connect raises
    ``[Errno 101] Network is unreachable`` before it can even authenticate.
    Forcing IPv4 sidesteps that. ``self._host`` remains the hostname, so STARTTLS
    certificate verification is unaffected. Falls back to the default dual-stack
    behaviour if no IPv4 address can be reached.
    """

    def _get_socket(self, host, port, timeout):
        try:
            infos = socket.getaddrinfo(host, port, socket.AF_INET, socket.SOCK_STREAM)
        except OSError:
            infos = []
        for *_unused, sockaddr in infos:
            try:
                return socket.create_connection(sockaddr, timeout, self.source_address)
            except OSError:
                continue
        return super()._get_socket(host, port, timeout)


class EmailService:
    def __init__(self) -> None:
        self._host = os.environ.get("SMTP_HOST", "").strip()
        self._port = int(os.environ.get("SMTP_PORT", "587"))
        self._user = os.environ.get("SMTP_USER", "").strip()
        self._password = os.environ.get("SMTP_PASSWORD", "").strip()
        self._from = os.environ.get("SMTP_FROM", "").strip() or self._user
        self._from_name = os.environ.get("SMTP_FROM_NAME", "Portfolio Tracker").strip()
        if self.enabled:
            logger.info("Email service enabled (SMTP %s:%d)", self._host, self._port)
        else:
            logger.warning("Email service disabled — SMTP_HOST / SMTP_USER / SMTP_PASSWORD not set")

    @property
    def enabled(self) -> bool:
        return bool(self._host and self._user and self._password)

    def send_html(self, to: str, subject: str, html: str, text: str | None = None) -> bool:
        if not self.enabled:
            logger.warning("Email send skipped (service disabled): %s", subject)
            return False

        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = formataddr((self._from_name, self._from))
        msg["To"] = to
        msg.set_content(text or "Open this email in an HTML-capable client to view your digest.")
        msg.add_alternative(html, subtype="html")

        try:
            context = ssl.create_default_context()
            with _IPv4SMTP(self._host, self._port, timeout=30) as server:
                server.starttls(context=context)
                server.login(self._user, self._password)
                server.send_message(msg)
            logger.info("Email sent to %s — %s", to, subject)
            return True
        except Exception as e:  # noqa: BLE001 — never let a send failure crash the caller
            logger.warning("Email send failed to %s: %s", to, e)
            return False


# Module-level singleton — one SMTP config shared across the app.
email_service = EmailService()


def get_email_service() -> EmailService:
    return email_service
