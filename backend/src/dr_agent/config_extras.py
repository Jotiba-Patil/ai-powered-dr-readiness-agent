"""Settings for email, time display and runbook uploads; `Settings` in `config.py` inherits them.

Split out only to keep `config.py` small: the variables are read and validated
together at startup like every other setting.
"""

from __future__ import annotations

from typing import Literal
from urllib.parse import urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, SecretStr, ValidationInfo, field_validator
from pydantic_settings import BaseSettings

from dr_agent.scheduling.models import is_email


class NotifyAndUploadSettings(BaseSettings):
    # Email after scheduled runs (ADR 0011). `log` writes a log line instead of sending.
    notify_transport: Literal["log", "smtp"] = "log"
    smtp_host: str = Field(default="localhost", min_length=1)
    smtp_port: int = Field(default=1025, ge=1, le=65535)
    smtp_username: str | None = None
    smtp_password: SecretStr | None = None
    smtp_starttls: bool = False
    smtp_timeout_seconds: float = Field(default=10.0, gt=0)
    notify_from: str = "dr-agent@example.com"
    notify_default_email: str | None = None
    notify_allowed_domains: str = "example.com"
    notify_directory: Literal["static"] = "static"
    notify_contacts_file: str | None = None
    ui_base_url: str | None = None
    # CLI only: show times in this IANA zone instead of the machine's local time.
    display_timezone: str | None = None
    # Saved runbook uploads (Phase 18): a folder inside API_ALLOWED_DIR, never overwritten.
    runbook_uploads_enabled: bool = True
    runbook_upload_dir: str = Field(default="uploads", min_length=1, max_length=100)
    runbook_upload_max_files: int = Field(default=200, ge=1, le=10_000)

    @property
    def display_zone(self) -> ZoneInfo | None:
        """`DISPLAY_TIMEZONE` for the CLI; None means the machine's local time."""
        return ZoneInfo(self.display_timezone) if self.display_timezone else None

    @property
    def allowed_email_domains(self) -> frozenset[str]:
        """`NOTIFY_ALLOWED_DOMAINS` is comma-separated; matching is case-insensitive."""
        parts = self.notify_allowed_domains.split(",")
        return frozenset(part.strip().casefold() for part in parts if part.strip())

    @field_validator("display_timezone", mode="before")
    @classmethod
    def _blank_zone(cls, value: object) -> object:
        return value.strip() or None if isinstance(value, str) else value

    @field_validator("display_timezone")
    @classmethod
    def _check_display_zone(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"unknown timezone {value!r}") from exc
        return value

    @field_validator("notify_from", "notify_default_email")
    @classmethod
    def _check_address(cls, value: str | None, info: ValidationInfo) -> str | None:
        address = value.strip() if value else ""
        if not address and info.field_name == "notify_from":
            raise ValueError("is required")
        if address and not is_email(address):
            raise ValueError("must be an email address such as dr-agent@example.com")
        return address or None

    @field_validator("ui_base_url", "notify_contacts_file", "smtp_username")
    @classmethod
    def _blank_is_none(cls, value: str | None) -> str | None:
        return value.strip() or None if value else None

    @field_validator("ui_base_url")
    @classmethod
    def _check_ui_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("must be an http(s) URL such as http://localhost:8080")
        return value.rstrip("/")

    @field_validator("runbook_upload_dir")
    @classmethod
    def _plain_folder(cls, value: str) -> str:
        """One plain folder name: it is joined to API_ALLOWED_DIR and must stay inside it."""
        folder = value.strip().strip("/\\")
        if not folder or folder.startswith(".") or any(c in folder for c in "/\\:"):
            raise ValueError("must be a single folder name such as uploads")
        return folder
