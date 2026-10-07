from dataclasses import dataclass

from app.schemas.interviews import EvaluationResult

POLICY_VERSION = "phase4-rules-v1"


@dataclass(frozen=True)
class Decision:
    action: str
    difficulty: int
    target_topic: str | None
    reason_codes: list[str]
    explanation: str


def decide(
    evaluation: EvaluationResult,
    *,
    current_difficulty: int,
    topic: str,
    answered_count: int,
    question_limit: int,
    topic_weak_count: int = 0,
    next_topic: str | None = None,
) -> Decision:
    if answered_count >= question_limit:
        return Decision(
            "end_interview",
            current_difficulty,
            None,
            ["question_limit"],
            "The configured question limit has been reached.",
        )
    if evaluation.misconceptions:
        return Decision(
            "test_missing_concept",
            max(1, current_difficulty - 1),
            topic,
            ["misconception"],
            "Check the identified misconception with a focused concept question.",
        )
    if evaluation.missing_concepts and evaluation.correctness < 0.75:
        return Decision(
            "test_missing_concept",
            current_difficulty,
            topic,
            ["missing_concept"],
            "Test an important concept missing from the answer.",
        )
    if topic_weak_count >= 2:
        return Decision(
            "revisit_topic",
            max(1, current_difficulty - 1),
            topic,
            ["repeated_weakness"],
            "Revisit the topic from a more foundational angle.",
        )
    if (
        evaluation.correctness >= 0.8
        and evaluation.completeness >= 0.75
        and evaluation.reasoning >= 0.7
    ):
        return Decision(
            "increase_difficulty",
            min(5, current_difficulty + 1),
            topic,
            ["strong_answer"],
            "The answer demonstrated enough command for a harder question.",
        )
    if evaluation.correctness < 0.4:
        return Decision(
            "decrease_difficulty",
            max(1, current_difficulty - 1),
            topic,
            ["weak_correctness"],
            "Ask a more foundational question at lower difficulty.",
        )
    if evaluation.correctness < 0.75 or evaluation.completeness < 0.65:
        return Decision(
            "ask_follow_up",
            current_difficulty,
            topic,
            ["partial_answer"],
            "Use a focused follow-up to resolve partial evidence.",
        )
    if next_topic and next_topic != topic:
        return Decision(
            "change_topic",
            current_difficulty,
            next_topic,
            ["topic_covered"],
            "Continue coverage with the next planned topic.",
        )
    return Decision(
        "maintain_difficulty",
        current_difficulty,
        topic,
        ["steady_progress"],
        "Continue at the current difficulty.",
    )
