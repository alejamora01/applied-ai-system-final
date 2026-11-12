"""PawPal+ Care Advisor: an agentic loop around the existing Scheduler.

Pipeline (orchestration):
  1. PLAN      build today's priority plan with ``Scheduler.generate_plan``.
  2. GUARD     scan every task name with ``guardrails.check_safety``.
  3. REPAIR    loop: find a time conflict, propose moving the lower-priority
               task to the next free slot, re-check. Stops when no conflicts
               remain or after ``max_iterations``.
  4. VERIFY    re-run conflict detection on the simulated schedule.
  5. RETRIEVE  look up grounded guidance (RAG) for each scheduled task.
  6. EXPLAIN   write a summary (template, or a model if configured), then
               check that text with the output guardrail.

The agent only *proposes* changes. Nothing is modified until a person
approves them via ``apply_proposals`` (human-in-the-loop).
"""
import copy
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import llm
from guardrails import check_model_output, check_safety, VET_NOTE
from pawpal_system import Owner, Scheduler
from retriever import Retriever

LOG_PATH = Path(__file__).parent / "logs" / "agent.log"
GENERIC_CAP = 0.3  # max confidence for category-only guidance
MIN_MATCH = 0.35  # weaker name matches are treated as "no guidance"


def get_logger() -> logging.Logger:
    """File logger that never crashes the app if the log can't be written."""
    logger = logging.getLogger("pawpal.agent")
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    try:
        LOG_PATH.parent.mkdir(exist_ok=True)
        handler = logging.FileHandler(LOG_PATH, encoding="utf-8")
        handler.setFormatter(
            logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
        )
        logger.addHandler(handler)
    except OSError:
        logger.addHandler(logging.NullHandler())
    return logger


@dataclass
class Proposal:
    pet_name: str
    task_name: str
    old_time: str
    new_time: str
    reason: str
    task_ref: object = field(repr=False, default=None)


@dataclass
class Advice:
    pet_name: str
    task_name: str
    text: str
    sources: List[str]
    confidence: float
    safety: str = "ok"
    safety_notes: List[str] = field(default_factory=list)


@dataclass
class AgentResult:
    plan: dict
    proposals: List[Proposal]
    advice: List[Advice]
    steps: List[Tuple[str, str]]
    unresolved_conflicts: List[Tuple[str, str]]
    blocked_tasks: List[Tuple[str, List[str]]]
    confidence: float
    confidence_label: str
    summary: str
    used_model: bool = False


def confidence_label(score: float) -> str:
    if score >= 0.7:
        return "high"
    if score >= 0.4:
        return "medium"
    return "low"


class CareAgent:
    def __init__(
        self,
        scheduler: Optional[Scheduler] = None,
        retriever: Optional[Retriever] = None,
        use_model: bool = True,
        max_iterations: int = 6,
    ):
        self.scheduler = scheduler or Scheduler()
        self.retriever = retriever or Retriever()
        self.use_model = use_model
        self.max_iterations = max_iterations
        self.log = get_logger()
        self.steps: List[Tuple[str, str]] = []

    def _step(self, name: str, detail: str):
        self.steps.append((name, detail))
        self.log.info("%s | %s", name, detail)

    # ---- step helpers -------------------------------------------------
    def _timed_scheduled(self, plan_pairs):
        return [(p, t) for p, t in plan_pairs if t.start_time]

    def _repair_conflicts(
        self, owner: Owner, scheduled
    ) -> Tuple[List[Proposal], List[Tuple[str, str]]]:
        """Simulate on a copy; return proposals and any leftover conflicts."""
        sim = copy.deepcopy(owner)
        originals = [t for _, t in owner.get_all_tasks()]
        sim_pairs = sim.get_all_tasks()
        index_of = {id(t): i for i, t in enumerate(originals)}
        sim_for = {
            id(t): sim_pairs[index_of[id(t)]][1] for _, t in scheduled
        }
        sim_scheduled = [(p, sim_for[id(t)]) for p, t in scheduled]
        pet_by_task = {id(t): p for p, t in scheduled}
        orig_by_sim = {id(sim_for[id(t)]): t for _, t in scheduled}

        proposals: Dict[int, Proposal] = {}

        for iteration in range(1, self.max_iterations + 1):
            conflicts = self.scheduler.detect_conflicts(
                self._timed_scheduled(sim_scheduled)
            )
            if not conflicts:
                self._step(
                    "VERIFY", f"Iteration {iteration}: no conflicts remain."
                )
                return list(proposals.values()), []

            first, second = conflicts[0]
            self._step(
                "REPAIR",
                f"Iteration {iteration}: '{first.name}' overlaps "
                f"'{second.name}'.",
            )

            # Move the lower-priority task; on a tie move the later one.
            if first.priority != second.priority:
                mover = first if first.priority < second.priority else second
            else:
                mover = max(
                    (first, second), key=lambda t: t.start_time or ""
                )

            slot = None
            try:
                slot = self.scheduler.find_next_available_slot(
                    self._without(sim, mover),
                    mover.duration,
                    window_start=mover.start_time,
                    target_date=mover.due_date,
                )
                if slot is None:
                    slot = self.scheduler.find_next_available_slot(
                        self._without(sim, mover),
                        mover.duration,
                        target_date=mover.due_date,
                    )
            except ValueError:
                slot = None

            if slot is None:
                self._step(
                    "REPAIR",
                    f"No free slot for '{mover.name}'. Needs a human.",
                )
                break

            orig = orig_by_sim[id(mover)]
            pet = pet_by_task[id(orig)]
            prior = proposals.get(id(orig))
            old_time = prior.old_time if prior else orig.start_time
            proposals[id(orig)] = Proposal(
                pet_name=pet.name,
                task_name=orig.name,
                old_time=old_time,
                new_time=slot,
                reason=(
                    f"Overlapped with a "
                    f"{'higher' if first.priority != second.priority else 'same'}"
                    f"-priority task; moved to the next free slot."
                ),
                task_ref=orig,
            )
            self._step(
                "REPAIR",
                f"Propose moving '{mover.name}' "
                f"{old_time} -> {slot}.",
            )
            mover.start_time = slot

        leftover = self.scheduler.detect_conflicts(
            self._timed_scheduled(sim_scheduled)
        )
        self._step(
            "VERIFY",
            f"{len(leftover)} conflict(s) could not be resolved.",
        )
        return list(proposals.values()), [(a.name, b.name) for a, b in leftover]

    @staticmethod
    def _without(sim_owner: Owner, task) -> Owner:
        """Copy of the owner with ``task`` hidden so it doesn't block itself."""
        clone = copy.copy(sim_owner)
        clone.pets = []
        for pet in sim_owner.pets:
            p = copy.copy(pet)
            p.tasks = [t for t in pet.tasks if t is not task]
            clone.pets.append(p)
        return clone

    def _advise(self, scheduled) -> List[Advice]:
        out = []
        for pet, task in scheduled:
            safety = check_safety(task.name)
            category = None if task.category == "general" else task.category
            # Confidence must come from the task's own words matching the
            # knowledge base. Species/category words alone are too generic.
            hits = self.retriever.search(task.name, k=1, category=category)
            hits = [h for h in hits if h.score >= MIN_MATCH]
            if not hits and category:
                generic = self.retriever.search(category, k=1, category=category)
                hits = [
                    type(g)(g.chunk, min(g.score, GENERIC_CAP))
                    for g in generic
                ]
            if hits:
                hit = hits[0]
                text = hit.chunk.text
                sources = [f"{hit.chunk.source} > {hit.chunk.title}"]
                conf = hit.score
            else:
                text = (
                    "No supporting guidance found in the knowledge base. "
                    "Treat this task with extra care and check with a vet "
                    "if unsure."
                )
                sources, conf = [], 0.0
            if task.category == "medication":
                text = f"{text} {VET_NOTE}"
            out.append(
                Advice(
                    pet_name=pet.name,
                    task_name=task.name,
                    text=text,
                    sources=sources,
                    confidence=round(conf, 2),
                    safety=safety.level,
                    safety_notes=safety.reasons,
                )
            )
        return out

    # ---- main entry point ---------------------------------------------
    def run(self, owner: Owner) -> AgentResult:
        self.steps = []
        self._step(
            "PLAN",
            f"{len(owner.get_all_tasks())} task(s), "
            f"{owner.available_minutes} min available.",
        )
        plan = self.scheduler.generate_plan(owner)
        scheduled = plan["scheduled"]
        self._step(
            "PLAN",
            f"{len(scheduled)} scheduled, {len(plan['deferred'])} deferred.",
        )

        blocked, allowed = [], []
        for pet, task in scheduled:
            safety = check_safety(task.name)
            if safety.blocked:
                blocked.append((f"{pet.name}: {task.name}", safety.reasons))
                self._step(
                    "GUARD",
                    f"Blocked '{task.name}': {'; '.join(safety.reasons)}",
                )
            else:
                allowed.append((pet, task))
                if safety.warned:
                    self._step(
                        "GUARD",
                        f"Warning on '{task.name}': "
                        f"{'; '.join(safety.reasons)}",
                    )
        if not blocked:
            self._step("GUARD", "All task names passed safety checks.")

        proposals, unresolved = self._repair_conflicts(owner, allowed)
        advice = self._advise(allowed)

        retrieval = (
            sum(a.confidence for a in advice) / len(advice) if advice else 0.0
        )
        verified = 1.0 if not unresolved else 0.0
        score = round(0.6 * retrieval + 0.4 * verified, 2)
        if blocked:
            score = round(score * 0.8, 2)
        label = confidence_label(score)
        self._step(
            "SCORE",
            f"retrieval={retrieval:.2f}, verified={verified:.0f} "
            f"-> confidence {score} ({label}).",
        )

        summary, used_model = self._explain(
            plan, proposals, advice, unresolved, blocked
        )
        self._step(
            "EXPLAIN",
            "Summary written by model." if used_model
            else "Summary written from template.",
        )

        return AgentResult(
            plan=plan,
            proposals=proposals,
            advice=advice,
            steps=list(self.steps),
            unresolved_conflicts=unresolved,
            blocked_tasks=blocked,
            confidence=score,
            confidence_label=label,
            summary=summary,
            used_model=used_model,
        )

    def _explain(self, plan, proposals, advice, unresolved, blocked):
        lines = [
            f"{len(plan['scheduled'])} task(s) fit in today's plan with "
            f"{plan['remaining_minutes']} minute(s) left"
        ]
        if plan["deferred"]:
            lines[0] += f"; {len(plan['deferred'])} deferred for lack of time"
        lines[0] += "."
        for p in proposals:
            lines.append(
                f"Suggested: move {p.pet_name}'s '{p.task_name}' from "
                f"{p.old_time} to {p.new_time} to avoid an overlap."
            )
        for a, b in unresolved:
            lines.append(
                f"Needs your decision: '{a}' and '{b}' still overlap."
            )
        for name, reasons in blocked:
            lines.append(f"Not scheduled ({name}): {' '.join(reasons)}")
        # RAG: the retrieved guidance is part of the answer, not a side note.
        for a in advice:
            if a.sources:
                tip = a.text.split(". ")[0].rstrip(".")
                lines.append(
                    f"Tip for {a.pet_name}'s '{a.task_name}': {tip}. "
                    f"[{a.sources[0]}]"
                )
            else:
                lines.append(
                    f"No guidance found for '{a.task_name}'; "
                    "check with your vet if unsure."
                )
        template = " ".join(lines)

        if self.use_model:
            facts = template + "\nGuidance:\n" + "\n".join(
                f"- {a.pet_name}/{a.task_name}: {a.text}" for a in advice
            )
            text = llm.write_explanation(facts)
            if text and not check_model_output(text).blocked:
                return text, True
            if text:
                self._step(
                    "GUARD",
                    "Model output rejected by guardrail; using template.",
                )
        return template, False


def apply_proposals(proposals: List[Proposal], approved: List[int]) -> int:
    """Apply only the proposals a person approved. Returns how many."""
    count = 0
    for i in approved:
        if 0 <= i < len(proposals):
            prop = proposals[i]
            if prop.task_ref is not None:
                prop.task_ref.start_time = prop.new_time
                get_logger().info(
                    "APPLY | %s '%s' %s -> %s",
                    prop.pet_name, prop.task_name,
                    prop.old_time, prop.new_time,
                )
                count += 1
    return count
