"""Transactional email — Resend (HTTP API) preferred, SMTP fallback.

Railway and many other container platforms block outbound SMTP ports on their
lower tiers, so a raw SMTP send fails with "[Errno 101] Network is unreachable".
Resend sends over HTTPS (443), which is never blocked, so it's the default when
configured. SMTP (stdlib) remains as a fallback for environments that allow it.

Configured via env (no secrets in code):
- RESEND_API_KEY     enables the Resend HTTP transport (preferred)
- RESEND_FROM        From header, default "Portfolio Tracker <onboarding@resend.dev>"
- SMTP_HOST / SMTP_PORT / SMTP_USER / SMTP_PASSWORD / SMTP_FROM / SMTP_FROM_NAME

When neither is configured the service reports enabled=False and send() is a
no-op, so the digest feature stays inert rather than erroring.
"""
import json
import os
import smtplib
import socket
import ssl
import urllib.error
import urllib.request
from email.message import EmailMessage
from email.utils import formataddr

from core.logging import get_logger

logger = get_logger(__name__)

_RESEND_ENDPOINT = "https://api.resend.com/emails"
# Resend's API sits behind Cloudflare, which blocks the default "Python-urllib"
# User-Agent as a bot signature (HTTP 403, Cloudflare error 1010). A normal
# browser UA passes the check.
_USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"


class _IPv4SMTP(smtplib.SMTP):
    """SMTP client that connects over IPv4 only.

    Container platforms often advertise an IPv6 address with no working IPv6
    route, so smtplib's default dual-stack connect raises ``[Errno 101] Network
    is unreachable``. Forcing IPv4 sidesteps that. ``self._host`` remains the
    hostname, so STARTTLS certificate verification is unaffected. Falls back to
    the default dual-stack behaviour if no IPv4 address can be reached.
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
        # Resend (HTTP) is preferred — it works where outbound SMTP is blocked.
        self._resend_key = os.environ.get("RESEND_API_KEY", "").strip()
        self._resend_from = os.environ.get(
            "RESEND_FROM", "Portfolio Tracker <onboarding@resend.dev>"
        ).strip()

        self._host = os.environ.get("SMTP_HOST", "").strip()
        self._port = int(os.environ.get("SMTP_PORT", "587"))
        self._user = os.environ.get("SMTP_USER", "").strip()
        self._password = os.environ.get("SMTP_PASSWORD", "").strip()
        self._from = os.environ.get("SMTP_FROM", "").strip() or self._user
        self._from_name = os.environ.get("SMTP_FROM_NAME", "Portfolio Tracker").strip()

        if self._resend_key:
            logger.info("Email service enabled (Resend HTTP API)")
        elif self._smtp_configured:
            logger.info("Email service enabled (SMTP %s:%d)", self._host, self._port)
        else:
            logger.warning("Email service disabled — set RESEND_API_KEY or SMTP_HOST/USER/PASSWORD")

    @property
    def _smtp_configured(self) -> bool:
        return bool(self._host and self._user and self._password)

    @property
    def enabled(self) -> bool:
        return bool(self._resend_key) or self._smtp_configured

    def send_html(self, to: str, subject: str, html: str, text: str | None = None) -> bool:
        if self._resend_key:
            return self._send_resend(to, subject, html)
        if self._smtp_configured:
            return self._send_smtp(to, subject, html, text)
        logger.warning("Email send skipped (service disabled): %s", subject)
        return False

    # ---- Resend (HTTP API) --------------------------------------------------

    def _send_resend(self, to: str, subject: str, html: str) -> bool:
        body = json.dumps({"from": self._resend_from, "to": [to], "subject": subject, "html": html}).encode()
        req = urllib.request.Request(
            _RESEND_ENDPOINT,
            data=body,
            headers={
                "Authorization": f"Bearer {self._resend_key}",
                "Content-Type": "application/json",
                "User-Agent": _USER_AGENT,
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                if 200 <= resp.status < 300:
                    logger.info("Email sent to %s via Resend — %s", to, subject)
                    return True
                logger.warning("Resend send to %s returned status %s", to, resp.status)
                return False
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")[:300]
            logger.warning("Resend send failed to %s: HTTP %s %s", to, e.code, detail)
            return False
        except Exception as e:  # noqa: BLE001
            logger.warning("Resend send error to %s: %s", to, e)
            return False

    # ---- SMTP (fallback) ----------------------------------------------------

    def _send_smtp(self, to: str, subject: str, html: str, text: str | None) -> bool:
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
            logger.info("Email sent to %s via SMTP — %s", to, subject)
            return True
        except Exception as e:  # noqa: BLE001 — never let a send failure crash the caller
            logger.warning("SMTP send failed to %s: %s", to, e)
            return False


# Module-level singleton — one transport config shared across the app.
email_service = EmailService()


def get_email_service() -> EmailService:
    return email_service
