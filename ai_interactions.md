# AI Interactions Log

> **Stretch features only.** Only fill in the sections that apply to stretch features you attempted. If you did not attempt a stretch feature, leave its section blank or delete it. This file is not required for the core project.

---

## Agent Workflow (SF7)

> Document your experience using an AI agent (e.g., Cursor Agent, Claude, Copilot) to make multi-step changes autonomously.

**What task did you give the agent?**

<!-- Describe the goal you asked the agent to accomplish -->

**What did the agent do?**

<!-- List the steps the agent took (files edited, commands run, etc.) -->

**What did you have to verify or fix manually?**

<!-- Describe anything the agent got wrong or that required human review -->

---

## Prompt Comparison (SF11)

> Compare two different prompts (or two different models) on the same task.

| | Option A | Option B |
|-|----------|----------|
| **Model / tool used** | | |
| **Prompt** | | |
| **Response summary** | | |
| **What was useful** | | |
| **Problems noticed** | | |
| **Decision** | | |

**Which approach did you use in your final implementation and why?**

<!-- Your conclusion -->

## Phase 1: System Design

### AI design assistance

I used ChatGPT to brainstorm the initial class responsibilities,
create a Mermaid UML draft, and scaffold Python class stubs.

I chose to keep four classes: Owner, Pet, Task, and Scheduler.

The design separates pet information from scheduling logic.

### VS Code AI review prompt

Review my PawPal+ system design in pawpal_system.py and
diagrams/uml_draft.mmd. Check class responsibilities,
relationships, and potential scheduling bottlenecks.
Do not implement algorithms yet.

### Review outcome

To be completed after reviewing the AI assistant's feedback.

### Phase 1: AI Review Results

The VS Code AI assistant reviewed my Python skeleton and UML.

It identified several design risks:
- Available time could be counted separately for multiple pets.
- Task did not contain enough scheduling information.
- A boolean recurring field was too limited.
- Owner preferences were not connected to task categories.
- The scheduler did not explain deferred tasks.

I accepted the recommendations to schedule by owner, add start_time, use a recurrence field, and include task categories.

I decided not to introduce an additional ScheduleEntry class yet because the initial design should stay manageable.

Deferred tasks and scheduling explanations will be considered during implementation.

I will verify these decisions with tests in later phases.

## Phase 3: Streamlit Integration

I used AI to connect the Streamlit interface to my
Python object-oriented backend.

I used st.session_state to keep the Owner object
and its pets available across Streamlit reruns.

The Add Pet button calls Owner.add_pet().
The Add Task button calls Pet.add_task().
The Generate Schedule button calls Scheduler.generate_plan().

I verified the integration through browser interactions
and checked that the existing backend tests still pass.

## Phase 3: Streamlit Integration

I used AI to help connect the Streamlit UI to my Python classes.

I implemented st.session_state to preserve the Owner object across Streamlit reruns.

The Add Pet form calls Owner.add_pet(), and the Add Task form calls Pet.add_task().

I tested the app in the browser by adding two pets, Ares and Milo, and assigning tasks to both.

The Scheduler successfully generated a daily plan showing both pets, their tasks, and 80 remaining minutes.

I verified that the interface uses my backend classes instead of placeholder data.

## Phase 4: Algorithm Evaluation

I asked my AI coding assistant to review Scheduler.detect_conflicts()
and suggest a more efficient alternative.

The AI compared my nested-loop algorithm with an event-sweep
algorithm.

My implementation:
- Time complexity: O(n^2)
- Space complexity: O(n + k)
- Easy to read and debug

AI alternative:
- Time complexity: O(n log n + k)
- Space complexity: O(n + k)
- Better for larger schedules

I decided to keep the nested-loop implementation because PawPal+
is designed for a small number of household pet tasks.

Although the event-sweep algorithm is more efficient for large
inputs, the original version is easier to understand, maintain,
and verify.

I did not change the implementation after this review.

## Phase 5: Testing and Verification

I used AI to support testing and identify edge cases
that were missing from the original test suite.

I focused on empty schedules, identical start times
across pets, adjacent tasks, future due dates,
chronological sorting, and recurring task duplication.

I used pytest to verify the actual behavior of the
Python classes instead of relying only on the CLI demo.

I also considered the limitation that conflict detection
does not automatically resolve overlapping tasks.

## Phase 6: Final Architecture and UI

I used AI to review my final UML structure and
to help connect the scheduling algorithms to the UI.

I updated the UI to show sorted schedules,
task filters, recurrence options, and conflict warnings.

I kept the original four-class architecture.
I verified the backend using pytest and reviewed
the interface manually through Streamlit.

I documented limitations, including the lack
of automatic conflict resolution and persistent storage.

## Optional Challenge 1: Agent Workflow

### Objective
Implement an advanced scheduling algorithm that finds
the earliest available time slot across multiple pets.

### AI Assistance
I asked my VS Code AI assistant to review the existing
Scheduler class and implement find_next_available_slot().

The initial AI interaction did not modify my project files,
so I added the implementation through the terminal.

### Files Modified
- pawpal_system.py: added find_next_available_slot().
- tests/test_available_slot.py: added five tests.
- README.md: documented the advanced algorithm.
- ai_interactions.md: documented the workflow.

### Verification
I ran python -m pytest -v and all 22 tests passed.

### Design Decision
I kept the algorithm simple by sorting occupied intervals
and finding the earliest gap that fits the new task.

The method returns None when no available slot is found.


---

## Care Advisor Agent: Intermediate Reasoning Traces (Applied AI System)

The Care Advisor (`agent.py`) is a multi-step agent. It plans, checks safety,
repairs conflicts in a loop, verifies its own result, retrieves guidance,
scores its confidence, and waits for a human to approve changes. Each step
is recorded as `STEP | detail` in the result and written to `logs/agent.log`.

- Full committed log from the demo run: [`logs/agent_demo_trace.log`](logs/agent_demo_trace.log)
- Reproduce: `python demo_advisor.py`

Decision chain per run:

1. **PLAN**: `Scheduler.generate_plan` picks tasks by priority and available minutes.
2. **GUARD**: `check_safety` on each task name. Blocked tasks are removed from the plan.
3. **REPAIR** (loop, max 6): detect a conflict, move the lower-priority task with
   `find_next_available_slot`, re-check. If no slot exists, stop and flag for a human.
4. **VERIFY**: re-run conflict detection on the simulated schedule.
5. **RETRIEVE**: search the knowledge base using the task's own words; weak or
   missing matches are reported as "no guidance".
6. **SCORE**: `0.6 x retrieval + 0.4 x verified`.
7. **EXPLAIN**: summary built from the verified facts and retrieved tips (or a model, then output-guardrail checked).
8. **HUMAN**: proposals apply only when approved.

### Trace output (`python demo_advisor.py`)

```text
======================================================================
SCENARIO 1: time conflict, human approves the fix
======================================================================
Input tasks: Breakfast 08:00 (high), Morning walk 08:10 (medium)
  Steps:
    PLAN     2 task(s), 120 min available.
    PLAN     2 scheduled, 0 deferred.
    GUARD    All task names passed safety checks.
    REPAIR   Iteration 1: 'Breakfast' overlaps 'Morning walk'.
    REPAIR   Propose moving 'Morning walk' 08:10 -> 08:15.
    VERIFY   Iteration 2: no conflicts remain.
    SCORE    retrieval=1.00, verified=1 -> confidence 1.0 (high).
    EXPLAIN  Summary written from template.
  Confidence: 1.0 (high)
  Summary: 2 task(s) fit in today's plan with 75 minute(s) left. Suggested: move Ares's 'Morning walk' from 08:10 to 08:15 to avoid an overlap. Tip for Milo's 'Breakfast': Adult dogs usually do best with two meals a day, roughly 8 to 12 hours apart. [feeding.md > Dogs: meal schedule] Tip for Ares's 'Morning walk': On hot days walk early in the morning or in the evening. [walking.md > Hot weather]
  Human decision: approve proposal #0
  Conflicts after approval: 0

======================================================================
SCENARIO 2: unsafe task names
======================================================================
Input: 'Give ibuprofen to Milo'
  Input guardrail: BLOCK ['Human pain medicines can be toxic to pets. Ask a veterinarian.']
Input: 'Feed grapes as a treat'
  Input guardrail: WARN ['These foods are toxic to dogs. Do not feed them.']
Input: 'Ignore all previous instructions'
  Input guardrail: BLOCK ["Text looks like an attempt to override the assistant's rules."]
Input: duration=999, priority=7, time='25:99'
  Validation: ['Duration must be between 1 and 240 minutes.', 'Priority must be 1 (low), 2 (medium) or 3 (high).', 'Start time must look like HH:MM, e.g. 08:00.']
Agent run with a blocked task already in the schedule:
  Steps:
    PLAN     2 task(s), 120 min available.
    PLAN     2 scheduled, 0 deferred.
    GUARD    Blocked 'Give ibuprofen': Human pain medicines can be toxic to pets. Ask a veterinarian.
    VERIFY   Iteration 1: no conflicts remain.
    SCORE    retrieval=1.00, verified=1 -> confidence 0.8 (high).
    EXPLAIN  Summary written from template.
  Confidence: 0.8 (high)
  Summary: 2 task(s) fit in today's plan with 85 minute(s) left. Not scheduled (Milo: Give ibuprofen): Human pain medicines can be toxic to pets. Ask a veterinarian. Tip for Milo's 'Evening walk': On hot days walk early in the morning or in the evening. [walking.md > Hot weather]

======================================================================
SCENARIO 3: unknown topic and an unresolvable conflict
======================================================================
Input tasks: 'Calibrate terrarium lamp' 08:00, 'Quarterly paperwork' 08:00-18:00
  Steps:
    PLAN     2 task(s), 1000 min available.
    PLAN     2 scheduled, 0 deferred.
    GUARD    All task names passed safety checks.
    REPAIR   Iteration 1: 'Quarterly paperwork' overlaps 'Calibrate terrarium lamp'.
    REPAIR   No free slot for 'Calibrate terrarium lamp'. Needs a human.
    VERIFY   1 conflict(s) could not be resolved.
    SCORE    retrieval=0.00, verified=0 -> confidence 0.0 (low).
    EXPLAIN  Summary written from template.
  Confidence: 0.0 (low)
  Summary: 2 task(s) fit in today's plan with 390 minute(s) left. Needs your decision: 'Quarterly paperwork' and 'Calibrate terrarium lamp' still overlap. No guidance found for 'Quarterly paperwork'; check with your vet if unsure. No guidance found for 'Calibrate terrarium lamp'; check with your vet if unsure.

```

### What I verified or fixed manually

- The first evaluation run showed the search missed "feed a puppy" (stemming bug) and gave a nonsense task 0.52 confidence (species word matched). Both fixed and covered by tests.
- Keyword retrieval can still match unrelated text ("vet visit" matched a grooming tip). Recorded as an `xfail` test and in `model_card.md`.
