"""Who gets a scheduled run's email (design scheduled-analysis section 7, ADR 0011).

Order: the schedule's override, then the directory entry for the runbook owner,
then `NOTIFY_DEFAULT_EMAIL`. The owner text comes from the runbook, so it is
untrusted: it is only ever a lookup key, never an address. Every address must
also be in an allowed domain, so the API cannot send mail anywhere it likes.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum

from dr_agent.notify.directory import ContactDirectory
from dr_agent.scheduling.models import MAX_RECIPIENTS, is_email
from dr_agent.utils.errors import AppError
from dr_agent.utils.logging import get_logger

_UNUSABLE_OWNERS = frozenset({"", "unspecified", "team", "tbd", "n/a", "none", "unknown"})
_log = get_logger("dr_agent.notify")


class RecipientSource(StrEnum):
    OVERRIDE = "override"
    DIRECTORY = "directory"
    DEFAULT = "default"
    NONE = "none"


@dataclass(frozen=True)
class Recipients:
    addresses: tuple[str, ...]
    source: RecipientSource
    owner_found: bool  # the runbook owner matched a directory entry
    dropped: int = 0  # addresses refused by the domain allow-list


@dataclass(frozen=True)
class RecipientPolicy:
    allowed_domains: frozenset[str]
    default: str | None = None

    def allows(self, address: str) -> bool:
        domain = address.rpartition("@")[2].casefold()
        return is_email(address) and domain in self.allowed_domains


async def resolve_recipients(
    *,
    override: Iterable[str] | None,
    owner: str | None,
    directory: ContactDirectory,
    policy: RecipientPolicy,
) -> Recipients:
    found = await _lookup(directory, owner)
    if override:
        return _allowed(override, RecipientSource.OVERRIDE, policy, owner_found=found is not None)
    if found is not None:
        direct = _allowed([found], RecipientSource.DIRECTORY, policy, owner_found=True)
        if direct.addresses:
            return direct
    if policy.default:
        return _allowed([policy.default], RecipientSource.DEFAULT, policy, owner_found=bool(found))
    return Recipients((), RecipientSource.NONE, owner_found=found is not None)


def usable_owner(owner: str | None) -> bool:
    return owner is not None and owner.strip().casefold() not in _UNUSABLE_OWNERS


async def _lookup(directory: ContactDirectory, owner: str | None) -> str | None:
    if owner is None or not usable_owner(owner):
        return None
    try:
        return await directory.email_for(owner)
    except (AppError, OSError) as exc:  # a directory outage falls back to the default
        _log.warning("contact_lookup_failed", error_type=type(exc).__name__)
        return None


def _allowed(
    candidates: Iterable[str],
    source: RecipientSource,
    policy: RecipientPolicy,
    *,
    owner_found: bool,
) -> Recipients:
    unique = list(dict.fromkeys(address.strip() for address in candidates))
    kept = tuple(address for address in unique if policy.allows(address))[:MAX_RECIPIENTS]
    dropped = len(unique) - len(kept)
    if dropped:
        _log.warning("recipients_dropped", count=dropped, source=source.value)
    if not kept:
        return Recipients((), RecipientSource.NONE, owner_found=owner_found, dropped=dropped)
    return Recipients(kept, source, owner_found=owner_found, dropped=dropped)
