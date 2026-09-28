"""`ContactDirectory`: a person's name to an email address (ADR 0011).

The PoC reads a JSON file (`NOTIFY_CONTACTS_FILE`). Production directories
(LDAP, Entra ID, Okta, PagerDuty or Opsgenie on-call, ServiceNow CMDB) are other
implementations of the same protocol, chosen in `wiring.py`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from pydantic import TypeAdapter
from pydantic import ValidationError as PydanticValidationError

from dr_agent.loaders import read_text_file
from dr_agent.scheduling.models import is_email
from dr_agent.utils.errors import AppError, ConfigError

_CONTACTS = TypeAdapter(dict[str, str])


class ContactDirectory(Protocol):
    async def email_for(self, name: str) -> str | None:
        """The address for `name`, or None if the directory does not know it."""
        ...


class StaticContactDirectory:
    """Names matched case-insensitively, with surrounding spaces ignored."""

    def __init__(self, contacts: dict[str, str]) -> None:
        self._contacts = {_key(name): address.strip() for name, address in contacts.items()}

    @classmethod
    def from_file(cls, path: Path) -> StaticContactDirectory:
        """Raises `ConfigError` for an unreadable file, bad JSON or a bad address."""
        try:
            contacts = _CONTACTS.validate_json(read_text_file(path))
        except (AppError, PydanticValidationError) as exc:
            raise ConfigError(f"NOTIFY_CONTACTS_FILE {path.name!r} is not a JSON object") from exc
        bad = [name for name, address in contacts.items() if not is_email(address.strip())]
        if bad:
            raise ConfigError(
                "NOTIFY_CONTACTS_FILE has entries that are not email addresses",
                details={"names": bad[:10]},
            )
        return cls(contacts)

    async def email_for(self, name: str) -> str | None:
        return self._contacts.get(_key(name))


class EmptyContactDirectory:
    """No directory configured: every lookup misses, so the default recipient is used."""

    async def email_for(self, name: str) -> str | None:
        return None


def _key(name: str) -> str:
    return " ".join(name.split()).casefold()
