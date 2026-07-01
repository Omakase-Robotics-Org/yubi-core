"""Canonical storage-path computation from recording metadata.

Produces the same path structure as local-data-workflow's canonical_path.py,
but without the rebake dependency.  Uses airoa-metadata for JSON parsing.

Canonical prefix format::

    org={org}/site={site}/location={location}/date={date}/task={task}/
    robot_type={type}/robot_id={id}/ts={timestamp}/uuid={uuid}

The ``task=<id>`` segment lets the ingest side (omakase-data-infra ``task_routing``)
group episodes by the operator-selected task straight from the object key, without
opening the bag. ``task`` is a versioning slug (``[a-z0-9]+``); episodes recorded
with no task selected fall back to ``unassigned`` so the key never breaks.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone

UNKNOWN_PATH_VALUE = "unknown"
#: Task-id slug for episodes recorded without an operator-selected task. Matches
#: the ``task_routing`` slug rule (``[a-z0-9]+``) so it routes cleanly downstream.
UNASSIGNED_TASK_VALUE = "unassigned"
_PATH_VALUE_PATTERN = re.compile(r"[^\w.-]+", re.UNICODE)
_MULTI_DASH_PATTERN = re.compile(r"-{2,}")
#: A routable task id must be a lowercase-alnum slug (mirrors
#: ``omakase_data_infra.ingest.task_routing._TASK_SLUG_RE``). Anything else is
#: coerced to ``unassigned`` rather than emitting a key the router would ignore.
_TASK_SLUG_PATTERN = re.compile(r"[^a-z0-9]+")


@dataclass(frozen=True)
class CanonicalPathFields:
    """Metadata fields used to build canonical storage paths."""

    uuid: str
    organization: str
    site: str
    location: str
    robot_type: str
    robot_id: str
    started_at: datetime
    task_id: str = UNASSIGNED_TASK_VALUE

    @property
    def date(self) -> str:
        return self.started_at.date().isoformat()

    @property
    def timestamp_rfc3339(self) -> str:
        return self.started_at.isoformat(timespec="milliseconds").replace("+00:00", "Z")

    @property
    def canonical_prefix(self) -> str:
        return (
            f"org={_normalize_path_value(self.organization)}/"
            f"site={_normalize_path_value(self.site)}/"
            f"location={_normalize_path_value(self.location)}/"
            f"date={self.date}/"
            f"task={_normalize_task_id(self.task_id)}/"
            f"robot_type={_normalize_path_value(self.robot_type)}/"
            f"robot_id={_normalize_path_value(self.robot_id)}/"
            f"ts={self.timestamp_rfc3339}/"
            f"uuid={self.uuid.lower()}"
        )

    @classmethod
    def from_meta_json(cls, meta_json_text: str) -> CanonicalPathFields:
        """Parse a meta.json string (V2.0 schema) and extract path fields."""
        data = json.loads(meta_json_text)
        robot = data.get("robot", {})
        env = data.get("environment", {})
        runner = data.get("runner", {})
        episode = data.get("episode", {})
        task = data.get("task") or {}

        uuid = data.get("uuid")
        if not uuid:
            raise ValueError("meta.json missing required 'uuid' field")

        return cls(
            uuid=uuid,
            organization=runner.get("organization") or UNKNOWN_PATH_VALUE,
            site=env.get("site") or UNKNOWN_PATH_VALUE,
            location=env.get("location") or UNKNOWN_PATH_VALUE,
            robot_type=robot.get("type") or UNKNOWN_PATH_VALUE,
            robot_id=robot.get("id") or UNKNOWN_PATH_VALUE,
            started_at=_as_utc_timestamp(float(episode.get("start_time", 0.0))),
            task_id=(task.get("id") if isinstance(task, dict) else None) or UNASSIGNED_TASK_VALUE,
        )


def _normalize_path_value(value: str | None) -> str:
    """Normalize one metadata field into a stable object-key segment.

    Matches the normalization in local-data-workflow exactly:
    NFKC → lowercase → slashes to dashes → whitespace to dashes →
    non-word chars to dashes → collapse multi-dashes → strip edges.
    """
    if value is None:
        return UNKNOWN_PATH_VALUE

    normalized = unicodedata.normalize("NFKC", value).strip().lower()
    if not normalized:
        return UNKNOWN_PATH_VALUE

    normalized = normalized.replace("/", "-")
    normalized = re.sub(r"\s+", "-", normalized)
    normalized = _PATH_VALUE_PATTERN.sub("-", normalized)
    normalized = _MULTI_DASH_PATTERN.sub("-", normalized).strip("-.")
    return normalized or UNKNOWN_PATH_VALUE


def _normalize_task_id(value: str | None) -> str:
    """Normalize a task id into a routable slug (``[a-z0-9]+``).

    The ingest-side router (``omakase_data_infra.ingest.task_routing``) only
    accepts a lowercase-alnum slug in the ``task=`` segment; anything else is
    treated as "no task signal". So we NFKC → lowercase → strip every non-alnum
    char, and fall back to ``unassigned`` when nothing usable remains (empty,
    ``None``, or all punctuation). This keeps the object key valid and routable
    even if a malformed id slips through.
    """
    if value is None:
        return UNASSIGNED_TASK_VALUE

    normalized = unicodedata.normalize("NFKC", value).strip().lower()
    normalized = _TASK_SLUG_PATTERN.sub("", normalized)
    return normalized or UNASSIGNED_TASK_VALUE


def _as_utc_timestamp(timestamp_seconds: float) -> datetime:
    return datetime.fromtimestamp(timestamp_seconds, timezone.utc)
