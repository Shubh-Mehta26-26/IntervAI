"""Versioned, conservative evidence policy. No provider scores or career ranking."""

import hashlib
import json
import re
from datetime import datetime, timezone

from app.services.memory_policy import independent

POLICY = "career-readiness-v1"
LABELS = ("DEMONSTRATED", "DEVELOPING", "LIMITED_EVIDENCE", "NOT_DEMONSTRATED")


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def key(value):
    return re.sub(r"[^a-z0-9]", "", value.casefold())


def matches(value, requirement):
    return key(value) in {
        key(requirement["skill"]),
        *(key(x) for x in requirement.get("aliases", [])),
    }


def readiness(requirement, observations, claims, gaps, *, now=None):
    now = now or datetime.now(timezone.utc)
    relevant = [row for row in observations if matches(row["subject"], requirement)]
    # Deduplicate evaluation/root chains using the established memory policy.
    from types import SimpleNamespace

    usable = independent([SimpleNamespace(**row) for row in relevant])
    usable = [row for row in usable if 0 <= (now - row.observed_at).total_seconds() <= 180 * 86400]
    recent = usable[-6:]
    claimed = [row for row in claims if matches(row["subject"], requirement)]
    active_gaps = [
        row
        for row in gaps
        if row["status"] in {"confirmed", "learning", "improving"}
        and any(matches(x, requirement) for x in [row["subject"], *row.get("related_subjects", [])])
    ]
    count = len(recent)
    varied = len({row.question_hash for row in recent}) >= 2
    status = "NOT_DEMONSTRATED"
    reason = "No matching evidence was recorded; this does not establish lack of knowledge."
    if claimed or relevant:
        status, reason = (
            "LIMITED_EVIDENCE",
            "Self-reported, stale, assisted, low-confidence, or insufficient independent evidence; proficiency is not established.",
        )
    if count:
        status, reason = (
            "DEVELOPING",
            "Independent grounded checks exist, but sustained demonstration thresholds are not met.",
        )
    if (
        count >= 3
        and len({row.interview_id for row in recent}) >= 2
        and varied
        and all(row.correctness >= 0.8 for row in recent[-3:])
        and not active_gaps
    ):
        status, reason = (
            "DEMONSTRATED",
            "Three recent independent grounded unassisted strong checks, across at least two interviews and two distinct questions, with no active related confirmed gap.",
        )
    if active_gaps:
        status, reason = (
            "DEVELOPING",
            "An existing confirmed, learning, or improving knowledge gap needs further checks.",
        )
    trend = "insufficient"
    if count >= 4 and len({row.interview_id for row in recent}) >= 2:
        split = count // 2
        delta = (
            sum(row.correctness for row in recent[split:]) / len(recent[split:])
            - sum(row.correctness for row in recent[:split]) / split
        )
        trend = "improving" if delta >= 0.15 else "declining" if delta <= -0.15 else "stable"
    evidence = [
        {
            "id": str(row.id),
            "kind": "interview_check",
            "interview_id": str(row.interview_id),
            "evaluation_id": str(row.evaluation_id),
            "observed_at": row.observed_at.isoformat(),
            "correctness": row.correctness,
            "confidence": row.confidence,
            "grounded": True,
            "assisted": False,
        }
        for row in recent
    ]
    evidence += [
        {
            "id": row["id"],
            "kind": row["kind"],
            "quote": row["quote"],
            "observed_at": row["observed_at"],
            "source_label": "Self-reported; not an independent proficiency check",
        }
        for row in claimed[:8]
    ]
    return {
        "skill": requirement["skill"],
        "requirement": requirement["requirement"],
        "status": status,
        "reason": reason,
        "evidence_count": count,
        "recorded_observation_count": len(relevant),
        "claim_count": len(claimed),
        "last_observed_at": max((row.observed_at for row in recent), default=None).isoformat()
        if recent
        else None,
        "trend": trend,
        "evidence": evidence,
        "gap_ids": [row["id"] for row in active_gaps],
        "gaps": active_gaps,
    }
