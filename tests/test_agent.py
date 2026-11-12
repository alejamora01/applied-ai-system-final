import pytest

from agent import CareAgent, apply_proposals
from pawpal_system import Owner, Pet, Task, Scheduler


def make_owner(tasks, minutes=120):
    owner = Owner("Test", minutes)
    pet = Pet("Milo", "Dog", 3)
    for t in tasks:
        pet.add_task(t)
    owner.add_pet(pet)
    return owner, pet


def run(owner):
    return CareAgent(use_model=False).run(owner)


def test_no_conflicts_means_no_proposals():
    owner, _ = make_owner([
        Task("Breakfast", 15, 3, "feeding", "08:00"),
        Task("Walk", 30, 2, "walking", "09:00"),
    ])
    assert run(owner).proposals == []


def test_conflict_moves_lower_priority_task():
    owner, _ = make_owner([
        Task("Breakfast", 15, 3, "feeding", "08:00"),
        Task("Walk", 30, 2, "walking", "08:10"),
    ])
    result = run(owner)
    assert len(result.proposals) == 1
    assert result.proposals[0].task_name == "Walk"


def test_agent_does_not_modify_tasks_before_approval():
    owner, pet = make_owner([
        Task("Breakfast", 15, 3, "feeding", "08:00"),
        Task("Walk", 30, 2, "walking", "08:10"),
    ])
    run(owner)
    assert pet.tasks[1].start_time == "08:10"


def test_approved_proposal_resolves_conflict():
    owner, _ = make_owner([
        Task("Breakfast", 15, 3, "feeding", "08:00"),
        Task("Walk", 30, 2, "walking", "08:10"),
    ])
    result = run(owner)
    assert apply_proposals(result.proposals, [0]) == 1
    scheduler = Scheduler()
    plan = scheduler.generate_plan(owner)["scheduled"]
    assert scheduler.detect_conflicts(plan) == []


def test_rejected_proposal_changes_nothing():
    owner, pet = make_owner([
        Task("Breakfast", 15, 3, "feeding", "08:00"),
        Task("Walk", 30, 2, "walking", "08:10"),
    ])
    result = run(owner)
    assert apply_proposals(result.proposals, []) == 0
    assert pet.tasks[1].start_time == "08:10"


def test_three_way_conflict_is_resolved_in_loop():
    owner, _ = make_owner([
        Task("A", 30, 3, "general", "08:00"),
        Task("B", 30, 2, "general", "08:10"),
        Task("C", 30, 1, "general", "08:20"),
    ])
    result = run(owner)
    assert result.unresolved_conflicts == []
    assert len(result.proposals) >= 2


def test_unsafe_task_is_blocked_and_reported():
    owner, _ = make_owner([
        Task("Give ibuprofen", 5, 3, "medication", "09:00"),
    ])
    result = run(owner)
    assert result.blocked_tasks
    assert result.advice == []


def test_unresolvable_conflict_is_flagged_for_human():
    # The whole window is occupied, so no free slot exists.
    owner, _ = make_owner([
        Task("All day", 600, 3, "general", "08:00"),
        Task("Short", 10, 1, "general", "09:00"),
    ], minutes=1000)
    result = run(owner)
    assert result.unresolved_conflicts


def test_advice_has_sources_and_confidence():
    owner, _ = make_owner([Task("Morning walk", 30, 2, "walking", "08:00")])
    advice = run(owner).advice[0]
    assert advice.sources and 0 < advice.confidence <= 1


def test_unknown_topic_gets_zero_confidence_and_vet_hint():
    owner, _ = make_owner([Task("Qwertyuiop", 10, 2, "general", "08:00")])
    advice = run(owner).advice[0]
    assert advice.confidence == 0.0
    assert "vet" in advice.text.lower()


def test_empty_owner_does_not_crash():
    result = run(Owner("Empty", 60))
    assert result.proposals == [] and result.advice == []
    assert result.confidence_label in {"low", "medium", "high"}


def test_summary_falls_back_when_model_unavailable(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    owner, _ = make_owner([Task("Walk", 30, 2, "walking", "08:00")])
    result = CareAgent(use_model=True).run(owner)
    assert result.used_model is False and result.summary


def test_model_output_with_dose_is_rejected(monkeypatch):
    import agent as agent_module
    monkeypatch.setattr(
        agent_module.llm, "write_explanation",
        lambda facts: "Give 10 mg of medicine twice a day.",
    )
    owner, _ = make_owner([Task("Walk", 30, 2, "walking", "08:00")])
    result = CareAgent(use_model=True).run(owner)
    assert result.used_model is False
    assert "10 mg" not in result.summary


def test_summary_uses_retrieved_guidance_and_cites_source():
    owner, _ = make_owner([Task("Morning walk", 30, 2, "walking", "08:00")])
    result = run(owner)
    assert "walking.md" in result.summary
    assert "Tip for Milo" in result.summary


def test_summary_admits_missing_guidance():
    owner, _ = make_owner([Task("Qwertyuiop", 10, 2, "general", "08:00")])
    assert "No guidance found" in run(owner).summary


@pytest.mark.xfail(
    reason="Known limitation: keyword retrieval cannot tell that 'vet visit' "
    "in a grooming tip is unrelated to scheduling a vet appointment.",
    strict=True,
)
def test_weak_keyword_match_is_not_presented_as_guidance():
    # "vet" appears in a grooming section, but that is not guidance
    # for an all-day vet visit.
    owner, _ = make_owner([Task("All-day vet visit", 60, 3, "general", "08:00")])
    advice = run(owner).advice[0]
    assert advice.sources == [] and advice.confidence == 0.0
