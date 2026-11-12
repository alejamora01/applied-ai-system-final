# Model Card: PawPal+ Care Advisor

> **Draft written from the work session. Read each section and edit it so it
> reflects your own experience before submitting.**

## Intended use

Help a pet owner build a daily care schedule, fix time conflicts, and see short,
sourced care reminders. It is a planning aid for a class project, **not** a
veterinary tool.

## How it works (summary)

1. Rule-based planning and conflict repair (the original `Scheduler`).
2. Regex guardrails for safety and input validation.
3. Local TF-IDF retrieval over six short care guides in `knowledge/`.
4. An optional language model that only rewrites a summary of facts the system already verified. Its output is checked by an output guardrail.

## Limitations and biases

- **Small knowledge base.** Six short guides, mostly about dogs and cats. Birds, reptiles, rabbits and other pets get little or no guidance and a low confidence score. This is a coverage bias toward common pets.
- **Keyword retrieval can match unrelated text.** It matches words, not meaning. Testing found "vet visit" matching a grooming tip, and "Long appointment" matching an enrichment tip because both contain the word "long". The case is recorded as an `xfail` test. "Kibble" or "supper" would also miss a feeding guide that never uses those words.
- **Regex guardrails are incomplete.** They catch listed medicines and phrases. A misspelled drug name or an unlisted toxin can slip through. They are a safety net, not a medical check.
- **Conflict repair is simple.** It moves the lower-priority task to the next free slot and does not consider owner preferences, travel time, or the 08:00-18:00 window for tasks that start outside it.
- **Confidence is a heuristic.** It measures how well the text matched the knowledge base and whether conflicts were resolved. It does not measure whether the advice is medically correct.
- **Guides are general.** They were written for this project and should be reviewed by a veterinarian before real use.
- **Untested paths.** The Streamlit UI was not run under automation, and the optional model path was not tested against a live API.

## Misuse and prevention

| Risk | Mitigation |
|---|---|
| Owner enters human medicine or a dose | Blocked or warned, vet note added, no dosing ever generated |
| Emergency typed as a task | Blocked with a message to call a vet |
| Prompt-injection text in a task name | Blocked by the input guardrail |
| Model writes a dose or unsafe advice | Output guardrail rejects it and the template is used (tested with a mocked model) |
| Agent silently changes the schedule | It only proposes; a person approves each change |
| Overconfident answers | Score shown, low score triggers a warning, unknown topics get "no guidance found" |
| Someone treats it as vet advice | Every medication tip and the app footer say it is not a veterinarian |

## Testing results

| Test input | Evaluation criteria | Result |
|---|---|---|
| "Give ibuprofen to Milo" | Blocked by guardrail | Pass |
| "Feed grapes as a treat" | Warned, not blocked | Pass |
| "Ignore all previous instructions" | Blocked | Pass |
| duration=999, priority=7, time="25:99" | Three validation errors | Pass |
| Breakfast 08:00 overlaps Morning walk 08:10 | Lower-priority task moved, conflict gone after approval | Pass |
| Three overlapping tasks | All resolved within the loop | Pass |
| Whole day occupied | Flagged for a human, not guessed | Pass |
| "Qwertyuiop" task | Confidence 0.0, "no guidance found" | Pass (after fix) |
| "feed a puppy" | Retrieves `feeding.md` | Pass (after fix) |
| Model output containing "10 mg" | Rejected, template used | Pass |
| "vet visit" retrieval | No unrelated tip | Fail (known limitation, `xfail`) |

Totals: 67 pytest passed, 1 xfailed; `evaluate.py` 23/23 (see `evaluation_results.txt`).

## What surprised me during testing

- My first confidence score gave a nonsense task name 0.52 confidence. The query included the pet's species, so the word "Dog" matched dog-related guides. The number looked reasonable but was meaningless, and only a test that expected 0.0 caught it.
- A stemming detail ("puppies" became "puppi") silently broke a basic question. The search still returned results, so nothing crashed. I only noticed because the evaluation script compared the source file.
- Fixing one false match did not remove the problem. Two more unrelated matches appeared (see Limitations), so I documented the limit instead of adding more special cases.

## AI collaboration

**How I used AI.** I used an AI assistant to plan which Module 2 project to extend, to design the architecture (retriever, guardrails, agent loop, human approval), to write and run the code and tests, and to debug failures from the evaluation script.

**One suggestion I accepted.** The assistant suggested making the system work locally by default and using a language model only as an optional layer. I chose the recommended option. It kept the project runnable without an API key, made tests deterministic, and meant the demo cannot break because of a key or network problem.

**One suggestion I did not accept as written.** When my new repo was empty, the assistant suggested that I could start a small new project in it (and confirm with my instructor). I did not do that. I used my own PawPal+ repository instead, because the assignment asks me to extend an earlier project, and that kept my commit history.

**One suggestion that was revised after testing.** The assistant's first confidence design searched with the task name, the pet species and the category. The evaluation showed this gave false confidence, so it was changed to search with the task's own words, cap category-only guidance at 0.3, and ignore weak matches.

## Future improvements

- Replace keyword search with embeddings, or add synonyms, so "kibble" finds feeding guidance.
- Have a veterinarian review and expand the knowledge base, including more species.
- Add a stronger medical-safety layer than regex, plus human review of blocked cases.
- Let the owner set preferences (preferred walk times, quiet hours) that the repair step respects.
- Automate a UI test for the Streamlit page and run the model path against a live API.
