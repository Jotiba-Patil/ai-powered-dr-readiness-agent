"""Contact directory and recipient resolution: order, untrusted owners, domain allow-list."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from history_support import MOCK

from dr_agent.notify.directory import EmptyContactDirectory, StaticContactDirectory
from dr_agent.notify.recipients import RecipientPolicy, RecipientSource, resolve_recipients
from dr_agent.utils.errors import ConfigError, NotFoundError

DIRECTORY = StaticContactDirectory(
    {"Alice Chen": "alice.chen@example.com", "Mallory": "mallory@evil.org"}
)
POLICY = RecipientPolicy(frozenset({"example.com"}), default="dr-team@example.com")


class BrokenDirectory:
    async def email_for(self, name: str) -> str | None:
        raise NotFoundError("directory offline")


async def test_directory_lookup_ignores_case_and_spacing() -> None:
    assert await DIRECTORY.email_for("  alice   CHEN ") == "alice.chen@example.com"
    assert await DIRECTORY.email_for("Bob") is None
    assert await EmptyContactDirectory().email_for("Alice Chen") is None


def test_bundled_contacts_file_loads(tmp_path: Path) -> None:
    StaticContactDirectory.from_file(MOCK / "contacts.json")
    bad = tmp_path / "c.json"
    bad.write_text(json.dumps({"A": "not-an-address"}), encoding="utf-8")
    with pytest.raises(ConfigError, match="not email addresses"):
        StaticContactDirectory.from_file(bad)
    bad.write_text("[1, 2]", encoding="utf-8")
    with pytest.raises(ConfigError, match="not a JSON object"):
        StaticContactDirectory.from_file(bad)
    with pytest.raises(ConfigError):
        StaticContactDirectory.from_file(tmp_path / "missing.json")


async def test_owner_from_the_directory() -> None:
    result = await resolve_recipients(
        override=None, owner="Alice Chen", directory=DIRECTORY, policy=POLICY
    )
    assert (result.addresses, result.source) == (
        ("alice.chen@example.com",),
        RecipientSource.DIRECTORY,
    )
    assert result.owner_found


async def test_override_wins_and_is_filtered_and_deduplicated() -> None:
    result = await resolve_recipients(
        override=["a@example.com", "a@example.com", "b@EXAMPLE.com", "c@evil.org"],
        owner="Alice Chen",
        directory=DIRECTORY,
        policy=POLICY,
    )
    assert result.addresses == ("a@example.com", "b@EXAMPLE.com")
    assert (result.source, result.dropped, result.owner_found) == (
        RecipientSource.OVERRIDE,
        1,
        True,
    )


@pytest.mark.parametrize(
    "owner",
    [
        None,
        "Unspecified",
        "team",
        "Bob Unknown",
        "alice.chen@example.com",  # an address in the runbook is never used as one
        "Mallory",  # directory knows them, but the domain is not allowed
    ],
)
async def test_untrusted_or_unknown_owners_fall_back_to_the_default(owner: str | None) -> None:
    result = await resolve_recipients(
        override=None, owner=owner, directory=DIRECTORY, policy=POLICY
    )
    assert (result.addresses, result.source) == (("dr-team@example.com",), RecipientSource.DEFAULT)


async def test_directory_outage_falls_back_to_the_default() -> None:
    result = await resolve_recipients(
        override=None, owner="Alice Chen", directory=BrokenDirectory(), policy=POLICY
    )
    assert result.source is RecipientSource.DEFAULT


async def test_nobody_when_nothing_resolves() -> None:
    policy = RecipientPolicy(frozenset({"example.com"}))
    none = await resolve_recipients(override=None, owner="Bob", directory=DIRECTORY, policy=policy)
    assert (none.addresses, none.source) == ((), RecipientSource.NONE)
    blocked = await resolve_recipients(
        override=["x@evil.org"], owner=None, directory=DIRECTORY, policy=policy
    )
    assert (blocked.addresses, blocked.source, blocked.dropped) == ((), RecipientSource.NONE, 1)
