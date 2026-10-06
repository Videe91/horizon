# World-Model Snapshot 018 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: use
> superpowers:executing-plans and implement task-by-task with RED → GREEN.

**Goal:** Assemble Horizon's existing claims, assessments and assertions
into one immutable deterministic snapshot, then render that snapshot as the
same human-readable semantic shape used by Horizon Cards.

**Architecture:** 018 has two units. `snapshot.py` validates and freezes
existing truth objects without reasoning about them. `render.py` performs
only caller-directed lookup and formatting over a valid snapshot. It never
infers relations, status, ownership, conflict or reconciliation.

**Tech Stack:** Python 3.14, frozen dataclasses, enums, canonical JSON /
SHA-256 identity, pytest.

**Spec:** `docs/superpowers/specs/2026-10-06-world-model-snapshot-018-design.md`

## Global Constraints

- Snapshot is a container, not a brain.
- No new assertions or epistemic states are inferred.
- No reconciliation, conflict detection, supersession or winner selection.
- `CALLS` never implies `OWNS_RESPONSIBILITY_FOR`.
- Cards/rendered snapshots are views, never truth storage.
- Missing justified content is displayed as absent/unknown, never invented.
- Frozen Prefect repository remains unchanged.

## Review Focus

- Duplicate IDs must be rejected rather than silently deduplicated.
- Missing claim/assessment links must fail closed.
- `dataclasses.replace` forged objects retaining old IDs must be rejected.
- Input ordering must not affect snapshot or rendering identity/content.
- Renderer requests for assertion IDs outside the snapshot must fail closed.

---

## Task 1 — Immutable World-Model Snapshot

**Files**
- Create: `src/horizon/world_model/snapshot.py`
- Test: `tests/unit/world_model/test_snapshot.py`

**Produces**

```python
@dataclass(frozen=True, slots=True)
class WorldModelSnapshot:
    claims: tuple[EvidenceBackedClaim, ...]
    assessments: tuple[EpistemicAssessment, ...]
    assertions: tuple[WorldModelAssertion, ...]
    snapshot_id: str

def make_world_model_snapshot(
    *,
    claims: Iterable[EvidenceBackedClaim],
    assessments: Iterable[EpistemicAssessment],
    assertions: Iterable[WorldModelAssertion],
) -> WorldModelSnapshot: ...

TDD sequence
- [ ] RED: valid linked objects produce a snapshot with exact four fields.
- [ ] RED: same logical inputs in different order produce identical snapshot.
- [ ] RED: duplicate claim, assessment or assertion identity is rejected.
- [ ] RED: assessment whose claim is absent is rejected.
- [ ] RED: assertion whose claim or assessment is absent is rejected.
- [ ] RED: assertion/assessment claim mismatch is rejected.
- [ ] RED: forged claim, assessment and assertion objects are rejected.
- [ ] RED: changing membership changes snapshot_id.
- [ ] GREEN: implement only canonicalization, integrity checks and identity.
- [ ] Verify focused snapshot tests.
- [ ] Verify full Horizon suite.
No query, inference, reconciliation or derived architecture method belongs
on WorldModelSnapshot.
Task 2 — Pure Card-Shaped Renderer
Files
- Create: src/horizon/world_model/render.py
- Test: tests/unit/world_model/test_render.py
Produces
class WorldModelCardSection(str, Enum):    WHAT_IT_IS = "WHAT_IT_IS"    WHERE_IT_SITS = "WHERE_IT_SITS"    WHAT_IT_OWNS = "WHAT_IT_OWNS"    WHAT_IT_DEPENDS_ON = "WHAT_IT_DEPENDS_ON"    WHAT_MUST_REMAIN_TRUE = "WHAT_MUST_REMAIN_TRUE"def render_world_model_card(    snapshot: WorldModelSnapshot,    *,    title: str,    question: str,    sections: Mapping[WorldModelCardSection, Iterable[str]],) -> str: ...


sections contains explicit assertion IDs selected by the caller. The
renderer does not decide which assertion belongs in which section.
For every selected assertion it follows existing links and renders:
- epistemic status;
- structured subject / relation / object;
- claim proposition;
- assertion ID;
- claim ID;
- assessment ID;
- assessment basis evidence-reference IDs.
It also emits HOW WE KNOW from those already-linked evidence references.
For a semantic section with no selected assertion it renders an explicit
absence instead of creating a fact.
TDD sequence
- [ ] RED: exact Card section order is stable.
- [ ] RED: selected assertion renders its exact epistemic stamp.
- [ ] RED: claim proposition and structured relation are both readable.
- [ ] RED: exact assertion → claim → assessment → evidence chain is shown.
- [ ] RED: empty section displays absence without inventing an assertion.
- [ ] RED: unknown assertion ID is rejected.
- [ ] RED: section assignment is caller-controlled, not relation-inferred.
- [ ] RED: input mapping/order does not destabilize rendered output.
- [ ] GREEN: implement lookup, validation and formatting only.
- [ ] Verify focused renderer tests.
- [ ] Verify full Horizon suite.
Prefect Certification
After Tasks 1–2 are green, build one snapshot from real frozen-Prefect
facts and render the answer to:
Who decides whether a failed Prefect flow retries?
The readable output must contain, with their actual epistemic states:
1. server retry-rule behavioural effect;
2. engine participation in re-execution;
3. narrowly scoped architectural ownership hypothesis;
4. competing/unresolved ownership assertion.
The output must visibly distinguish PROVEN,
SUPPORTED_HYPOTHESIS, DISPUTED, and UNKNOWN where warranted and show
the evidence chain for every rendered semantic line.
Certification must prove that 018 preserves disagreement without resolving
it and leaves frozen Prefect unchanged.
019 begins only after this certification and defines
AGREE / CONFLICT / COEXIST / SUPERSEDE from an observed real conflict.
