import streamlit as st
from datetime import date, datetime
from pawpal_system import Owner, Pet, Task, Scheduler
from agent import CareAgent, apply_proposals
from guardrails import check_safety, validate_task_input
import llm

st.set_page_config(
    page_title="PawPal+",
    page_icon="🐾",
    layout="wide"
)

st.title("🐾 PawPal+")
st.caption("Smart pet care, made simple.")

if "owner" not in st.session_state:
    st.session_state.owner = Owner("Alejandra", 120)

owner = st.session_state.owner
scheduler = Scheduler()

st.header("👤 Owner Profile")

with st.form("owner_form"):
    name = st.text_input("Owner name", value=owner.name)
    minutes = st.number_input(
        "Available minutes per day",
        min_value=0,
        value=owner.available_minutes
    )
    if st.form_submit_button("Save Profile"):
        if name.strip():
            owner.name = name.strip()
            owner.available_minutes = int(minutes)
            st.success("Profile updated!")
        else:
            st.error("Please enter a name.")

left, right = st.columns(2)

with left:
    st.header("🐶 Add a Pet")

    with st.form("pet_form", clear_on_submit=True):
        pet_name = st.text_input("Pet name")
        species = st.selectbox(
            "Species", ["Dog", "Cat", "Other"]
        )
        age = st.number_input(
            "Age", 0, 40, 1
        )

        if st.form_submit_button("Add Pet"):
            if pet_name.strip():
                owner.add_pet(
                    Pet(pet_name.strip(), species, int(age))
                )
                st.success("Pet added!")
            else:
                st.error("Enter a pet name.")

with right:
    st.header("📋 Add Care Task")

    if owner.pets:
        with st.form("task_form", clear_on_submit=True):
            pet_index = st.selectbox(
                "Choose pet",
                range(len(owner.pets)),
                format_func=lambda i: owner.pets[i].name
            )
            task_name = st.text_input("Task name")
            duration = st.number_input(
                "Duration (minutes)", 1, 240, 20
            )
            priority = st.selectbox(
                "Priority",
                ["High", "Medium", "Low"]
            )
            category = st.selectbox(
                "Category",
                ["feeding", "walking", "medication",
                 "grooming", "enrichment", "general"]
            )
            task_date = st.date_input(
                "Due date", value=date.today()
            )
            start_time = st.text_input(
                "Start time (HH:MM, optional)",
                placeholder="08:00"
            )
            recurrence = st.selectbox(
                "Repeat", ["none", "daily", "weekly"]
            )

            submitted = st.form_submit_button("Add Task")

        if submitted:
            valid_time = True

            if start_time.strip():
                try:
                    datetime.strptime(
                        start_time.strip(), "%H:%M"
                    )
                except ValueError:
                    valid_time = False

            safety = check_safety(task_name)
            problems = validate_task_input(
                task_name, int(duration),
                {"Low": 1, "Medium": 2, "High": 3}[priority],
                start_time.strip() or None,
            )

            if not task_name.strip():
                st.error("Enter a task name.")
            elif not valid_time:
                st.error("Use HH:MM, e.g. 08:00.")
            elif problems:
                for problem in problems:
                    st.error(problem)
            elif safety.blocked:
                st.error("Task not added: " + " ".join(safety.reasons))
            else:
                if safety.warned:
                    st.warning(" ".join(safety.reasons))
                priorities = {
                    "Low": 1,
                    "Medium": 2,
                    "High": 3
                }

                task = Task(
                    name=task_name.strip(),
                    duration=int(duration),
                    priority=priorities[priority],
                    category=category,
                    start_time=start_time.strip() or None,
                    recurrence=recurrence,
                    due_date=task_date
                )

                owner.pets[pet_index].add_task(task)
                st.success("Task added!")
    else:
        st.info("Add a pet first.")

st.divider()
st.header("🐾 My Pets")

if owner.pets:
    for pet in owner.pets:
        st.write(
            f"**{pet.name}** — {pet.species}, "
            f"age {pet.age}"
        )
else:
    st.info("No pets registered yet.")

st.divider()
st.header("📌 Task Manager")

pet_filter = st.selectbox(
    "Filter by pet",
    ["All"] + [pet.name for pet in owner.pets]
)

status_filter = st.selectbox(
    "Filter by status",
    ["All", "Pending", "Completed"]
)

status = {
    "All": None,
    "Pending": False,
    "Completed": True
}

filtered = scheduler.filter_tasks(
    owner.get_all_tasks(),
    pet_name=None if pet_filter == "All" else pet_filter,
    completed=status[status_filter]
)

filtered = scheduler.sort_by_time(filtered)

if filtered:
    rows = []

    for pet, task in filtered:
        rows.append({
            "Pet": pet.name,
            "Task": task.name,
            "Time": task.start_time or "Flexible",
            "Date": str(task.due_date),
            "Minutes": task.duration,
            "Priority": task.priority,
            "Repeat": task.recurrence,
            "Status": (
                "Completed" if task.completed else "Pending"
            )
        })

    st.dataframe(rows, use_container_width=True)
else:
    st.info("No tasks match your filters.")

pending = [
    (pet, task)
    for pet, task in owner.get_all_tasks()
    if not task.completed
]

if pending:
    st.subheader("Mark a Task Complete")

    selected_index = st.selectbox(
        "Select task",
        range(len(pending)),
        format_func=lambda i: (
            f"{pending[i][0].name} — "
            f"{pending[i][1].name} "
            f"({pending[i][1].due_date})"
        )
    )

    if st.button("Complete Selected Task"):
        pet, task = pending[selected_index]
        next_task = pet.complete_task(task)

        st.success(f"{task.name} completed!")

        if next_task:
            st.info(
                f"Next occurrence: {next_task.due_date}"
            )

st.divider()
st.header("📅 Today's Schedule")

if st.button("Generate Schedule"):
    result = scheduler.generate_plan(owner)
    scheduled = scheduler.sort_by_time(
        result["scheduled"]
    )

    if scheduled:
        for pet, task in scheduled:
            st.write(
                f"**{task.start_time or 'Flexible'}** "
                f"— {pet.name}: {task.name} "
                f"({task.duration} min)"
            )
    else:
        st.info("No tasks scheduled for today.")

    st.metric(
        "Remaining minutes",
        result["remaining_minutes"]
    )

    if result["deferred"]:
        st.warning(
            f"{len(result['deferred'])} task(s) deferred "
            "because of limited available time."
        )

        for pet, task in result["deferred"]:
            st.write(f"Deferred: {pet.name} — {task.name}")

    conflicts = scheduler.detect_conflicts(scheduled)

    if conflicts:
        for first, second in conflicts:
            st.warning(
                f"Time conflict: {first.name} overlaps "
                f"with {second.name}. Please review "
                "their scheduled times."
            )
    else:
        st.success("No time conflicts detected.")

st.divider()
st.header("🤖 Care Advisor")
st.caption(
    "The advisor plans your day, checks safety, proposes fixes for "
    "time conflicts, and cites its sources. It never changes anything "
    "until you approve."
)

mode = "model + local knowledge" if llm.is_available() else (
    "local knowledge base (no API key set)"
)
st.caption(f"Mode: {mode}")

if st.button("Run Care Advisor"):
    st.session_state.advisor_result = CareAgent().run(owner)

result = st.session_state.get("advisor_result")

if result:
    st.subheader("Summary")
    st.write(result.summary)
    st.metric(
        "Confidence",
        f"{result.confidence:.2f} ({result.confidence_label})"
    )
    if result.confidence_label == "low":
        st.warning(
            "Low confidence: please review this plan yourself "
            "or ask your vet."
        )

    for name, reasons in result.blocked_tasks:
        st.error(f"Blocked: {name}. {' '.join(reasons)}")

    if result.proposals:
        st.subheader("Proposed schedule changes")
        chosen = []
        for i, prop in enumerate(result.proposals):
            if st.checkbox(
                f"{prop.pet_name}: {prop.task_name} "
                f"{prop.old_time} → {prop.new_time}",
                key=f"proposal_{i}",
                help=prop.reason,
            ):
                chosen.append(i)
        if st.button("Apply approved changes"):
            applied = apply_proposals(result.proposals, chosen)
            st.session_state.pop("advisor_result", None)
            st.success(f"Applied {applied} change(s).")
    else:
        st.success("No schedule changes needed.")

    for a, b in result.unresolved_conflicts:
        st.warning(f"Needs your decision: {a} overlaps {b}.")

    if result.advice:
        st.subheader("Guidance for today's tasks")
        for adv in result.advice:
            with st.expander(
                f"{adv.pet_name}: {adv.task_name} "
                f"(confidence {adv.confidence:.2f})"
            ):
                st.write(adv.text)
                if adv.sources:
                    st.caption("Source: " + "; ".join(adv.sources))
                for note in adv.safety_notes:
                    st.warning(note)

    with st.expander("How the advisor decided (step log)"):
        for step, detail in result.steps:
            st.write(f"**{step}** — {detail}")

st.caption(
    "PawPal+ is not a veterinarian. For health or medication "
    "questions, contact your vet."
)
