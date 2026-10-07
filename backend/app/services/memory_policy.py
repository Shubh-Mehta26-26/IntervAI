"""Pure, versioned gap policy. No provider calls and no transcript inference."""

import re
from dataclasses import dataclass
from datetime import datetime

POLICY_VERSION = "memory-gap-v1"
CONCEPTS = {
    "normalization": ("normalization", "normalisation", "3nf", "third normal form"),
    "transactions": ("transactions", "transaction", "atomicity", "acid"),
    "indexing": ("indexing", "indexes", "b-tree"),
    "deadlocks": ("deadlock", "deadlocks"),
    "processes and threads": ("processes and threads", "process/thread", "process and thread"),
    "generators": ("generator", "generators", "yield"),
    "decorators": ("decorator", "decorators"),
    "binary search": ("binary search",),
    "hash tables": ("hash table", "hash tables"),
}


def normalized(value: str) -> str:
    return re.sub(r"[^\w+.# -]", "", " ".join(value.casefold().split()))[:240]


def concepts(value: str) -> list[str]:
    return [
        name
        for name, aliases in CONCEPTS.items()
        if any(
            re.search(r"(?<!\w)" + re.escape(alias) + r"(?!\w)", value.casefold())
            for alias in aliases
        )
    ]


def independent(observations):
    # The latest correction within a follow-up chain supersedes its earlier failure
    # for derived policy only. Historical records themselves are never changed.
    roots = {}
    for item in sorted(observations, key=lambda x: (x.observed_at, str(x.evaluation_id))):
        if item.grounded and item.confidence >= 0.7 and not item.assisted:
            roots[item.root_question_id] = item
    per_interview = {}
    for item in roots.values():
        per_interview.setdefault(item.interview_id, []).append(item)
    result = []
    for items in per_interview.values():
        result.extend(sorted(items, key=lambda x: x.observed_at)[-2:])
    return sorted(result, key=lambda x: (x.observed_at, str(x.evaluation_id)))


@dataclass(frozen=True)
class GapDecision:
    status: str
    reason: str
    weakness_index: float
    independent_count: int
    weak_interviews: int
    evidence_ids: list[str]


def gap_decision(observations, status="observed", baseline=None, resolved_at=None, now=None):
    items = independent(observations)
    now = now or max((x.observed_at for x in items), default=datetime.now().astimezone())
    weights = [
        x.confidence * 2.718281828 ** (-max(0, (now - x.observed_at).days) / 90) for x in items
    ]
    weakness = (
        sum(w * (1 - x.correctness) for w, x in zip(weights, items)) / sum(weights)
        if weights
        else 0.0
    )
    weak = [x for x in items if x.weak]
    weak_interviews = len({x.interview_id for x in weak})
    strong = []
    for item in reversed(items):
        if not item.strong:
            break
        strong.append(item)
    recent_weak = [x for x in weak if resolved_at is None or x.observed_at > resolved_at]
    next_status, reason = status, "Evidence recorded; persistence thresholds are not yet met."
    if status == "resolved":
        if len(recent_weak) >= 3 and len({x.interview_id for x in recent_weak}) >= 2:
            next_status, reason = (
                "confirmed",
                "Three new grounded weak root questions across two interviews reopened this gap.",
            )
    elif (
        len(strong) >= 3
        and len({x.interview_id for x in strong}) >= 2
        and len({x.root_question_id for x in strong}) >= 3
        and len({x.question_hash for x in strong}) >= 2
    ):
        next_status, reason = (
            "resolved",
            "Three independent strong concept checks across at least two interviews show sustained recovery.",
        )
    elif status in {"confirmed", "learning", "improving"}:
        if (
            len(strong) >= 2
            and baseline is not None
            and sum(x.correctness for x in strong) / len(strong) >= baseline + 0.15
        ):
            next_status, reason = (
                "improving",
                "Two new grounded strong observations exceed the confirmation baseline by at least 0.15.",
            )
        elif status == "improving" and items and items[-1].weak:
            next_status, reason = (
                "confirmed",
                "New grounded weakness interrupted the improvement streak.",
            )
    elif len(weak) >= 3 and weak_interviews >= 2 and weakness >= 0.4:
        next_status, reason = (
            "confirmed",
            "Three grounded weak root questions across at least two interviews and a weakness index of at least 0.40.",
        )
    return GapDecision(
        next_status,
        reason,
        round(weakness, 4),
        len(items),
        weak_interviews,
        [str(x.id) for x in items],
    )
