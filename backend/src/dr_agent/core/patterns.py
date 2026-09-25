"""Regex patterns and lookup tables shared by the runbook extractors."""

from __future__ import annotations

import re

from dr_agent.models.runbook import DependencyType

_MARKUP_RE = re.compile(r"[*_`]")


def clean_markup(text: str) -> str:
    """Strips bold/italic/inline-code markers so regexes can match plain text."""
    return _MARKUP_RE.sub("", text)


OWNER_RE = re.compile(r"owner\s*[:\-]\s*(.+)", re.IGNORECASE)
RTO_RE = re.compile(r"\bRTO\b\s*[:\-]?\s*(.+)", re.IGNORECASE)
RPO_RE = re.compile(r"\bRPO\b\s*[:\-]?\s*(.+)", re.IGNORECASE)
HANDLE_RE = re.compile(r"@([\w\-]+(?:\.[\w\-]+)*)")
PAREN_OWNER_RE = re.compile(r"\(([A-Z][\w .'\-]*)\)")
AFTER_STEP_RE = re.compile(
    r"after\s+steps?\s+(\d+(?:\s*(?:,|and|&)\s*(?:steps?\s*)?\d+)*)", re.IGNORECASE
)
VALIDATION_HINT_RE = re.compile(r"(?:validat|verify|check)\w*", re.IGNORECASE)
CODE_SPAN_RE = re.compile(r"`([^`]+)`")
TARGET_RE = re.compile(r"\btarget(?:\s+system)?\s*[:\-]\s*([^.,;]+)", re.IGNORECASE)
STEP_NUMBER_PREFIX_RE = re.compile(r"^\s*(?:step\s*)?(\d+)\s*[.:)]\s*", re.IGNORECASE)

DEPENDENCY_TYPE_KEYWORDS: dict[str, DependencyType] = {
    "postgres": DependencyType.DATABASE,
    "mysql": DependencyType.DATABASE,
    "database": DependencyType.DATABASE,
    "db": DependencyType.DATABASE,
    "redis": DependencyType.DATABASE,
    "cache": DependencyType.DATABASE,
    "kafka": DependencyType.MESSAGING,
    "queue": DependencyType.MESSAGING,
    "sqs": DependencyType.MESSAGING,
    "rabbitmq": DependencyType.MESSAGING,
    "messaging": DependencyType.MESSAGING,
    "vault": DependencyType.SECRETS,
    "secrets": DependencyType.SECRETS,
    "kms": DependencyType.SECRETS,
    "dns": DependencyType.NETWORK,
    "network": DependencyType.NETWORK,
    "load balancer": DependencyType.NETWORK,
    "lb": DependencyType.NETWORK,
    "s3": DependencyType.EXTERNAL,
    "external": DependencyType.EXTERNAL,
    "third-party": DependencyType.EXTERNAL,
    "saas": DependencyType.EXTERNAL,
    "ec2": DependencyType.COMPUTE,
    "compute": DependencyType.COMPUTE,
    "kubernetes": DependencyType.COMPUTE,
    "k8s": DependencyType.COMPUTE,
    "server": DependencyType.COMPUTE,
}


def infer_dependency_type(text: str) -> DependencyType:
    lowered = text.lower()
    for keyword, dep_type in DEPENDENCY_TYPE_KEYWORDS.items():
        if keyword in lowered:
            return dep_type
    return DependencyType.OTHER
