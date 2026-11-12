"""Guardrails for PawPal+.

Two layers:
1. ``validate_task_input`` checks that task fields are sane.
2. ``check_safety`` scans free text (task names and any model output)
   for pet-safety problems and unsafe instructions.

Severity levels:
- ``block``: the task or text is rejected / replaced with a safe message.
- ``warn``:  allowed, but a visible warning is attached.
- ``ok``:    nothing found.

These are simple, transparent rules (regex), not a medical system. PawPal+
never gives dosages and always points to a veterinarian for health decisions.
"""
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

VET_NOTE = (
    "PawPal+ is not a veterinarian. For health or medication "
    "questions, contact your vet."
)

# (pattern, level, reason). First match of the highest severity wins.
SAFETY_RULES = [
    (
        r"\b(ignore|disregard|forget)\b.{0,30}\b(previous|prior|above|all)\b"
        r".{0,30}\b(instruction|rule|prompt)s?\b",
        "block",
        "Text looks like an attempt to override the assistant's rules.",
    ),
    (
        r"\b(ibuprofen|advil|motrin|acetaminophen|paracetamol|tylenol|"
        r"naproxen|aleve|aspirin)\b",
        "block",
        "Human pain medicines can be toxic to pets. Ask a veterinarian.",
    ),
    (
        r"\b(seizure|seizing|not breathing|can't breathe|cannot breathe|"
        r"collapsed|unconscious|poisoned|ate poison|bloat)\b",
        "block",
        "This sounds like an emergency. Call a veterinarian or an animal "
        "poison control line now instead of scheduling a task.",
    ),
    (
        r"\b(chocolate|grapes?|raisins?|xylitol|macadamia)\b",
        "warn",
        "These foods are toxic to dogs. Do not feed them.",
    ),
    (
        r"\b(onions?|garlic)\b",
        "warn",
        "Onion and garlic can be harmful to dogs and cats.",
    ),
    (
        r"\b\d+(\.\d+)?\s?(mg|mcg|ml|cc|tablets?|pills?)\b",
        "warn",
        "Dosage found. PawPal+ cannot verify doses. Follow the exact "
        "amount on your vet's prescription label.",
    ),
    (
        r"\b(stop|skip|double)\b.{0,20}\b(medication|meds|dose|pills?)\b",
        "warn",
        "Never skip, double, or stop medication without asking your vet.",
    ),
]

DOSE_IN_OUTPUT = re.compile(
    r"\b\d+(\.\d+)?\s?(mg|mcg|ml|cc|tablets?|pills?)\b", re.IGNORECASE
)


@dataclass
class SafetyResult:
    level: str = "ok"
    reasons: List[str] = field(default_factory=list)

    @property
    def blocked(self) -> bool:
        return self.level == "block"

    @property
    def warned(self) -> bool:
        return self.level == "warn"


def check_safety(text: Optional[str]) -> SafetyResult:
    """Scan free text and return the most severe finding."""
    result = SafetyResult()
    if not text or not text.strip():
        return result

    order = {"ok": 0, "warn": 1, "block": 2}
    for pattern, level, reason in SAFETY_RULES:
        if re.search(pattern, text, re.IGNORECASE):
            if reason not in result.reasons:
                result.reasons.append(reason)
            if order[level] > order[result.level]:
                result.level = level
    return result


def check_model_output(text: Optional[str]) -> SafetyResult:
    """Stricter check for generated text: no dosages, no unsafe advice.

    Anything that gives a dose is blocked because PawPal+ must never
    produce dosing instructions, even if a model wrote them.
    """
    result = check_safety(text)
    if text and DOSE_IN_OUTPUT.search(text):
        result.level = "block"
        result.reasons.append("Generated text contained a dosage.")
    return result


def validate_task_input(
    name: str,
    duration: int,
    priority: int,
    start_time: Optional[str] = None,
) -> List[str]:
    """Return a list of human-readable problems (empty list = valid)."""
    problems = []

    if not name or not name.strip():
        problems.append("Task name is required.")
    elif len(name.strip()) > 80:
        problems.append("Task name must be 80 characters or fewer.")

    try:
        duration = int(duration)
        if not 1 <= duration <= 240:
            problems.append("Duration must be between 1 and 240 minutes.")
    except (TypeError, ValueError):
        problems.append("Duration must be a whole number.")

    if priority not in (1, 2, 3):
        problems.append("Priority must be 1 (low), 2 (medium) or 3 (high).")

    if start_time:
        try:
            datetime.strptime(start_time, "%H:%M")
        except ValueError:
            problems.append("Start time must look like HH:MM, e.g. 08:00.")

    return problems
