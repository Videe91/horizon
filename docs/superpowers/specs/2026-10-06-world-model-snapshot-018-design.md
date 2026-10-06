# Capability 018 — World-Model Snapshot

## Goal

Assemble Horizon's existing evidence-backed claims, epistemic assessments,
and world-model assertions into one immutable, deterministic, internally
consistent software-world snapshot.

018 is a container and projection layer, not a reasoning engine.

## Inputs

A snapshot contains exact first-class objects already produced by Horizon:

- `EvidenceBackedClaim`
- `EpistemicAssessment`
- `WorldModelAssertion`

The snapshot stores those objects without changing their meaning or
duplicating their evidence, epistemic status, scope, or rationale.

## Snapshot Contract

`WorldModelSnapshot` contains:

- `claims`
- `assessments`
- `assertions`
- `snapshot_id`

The constructor must:

1. reject duplicate object identities;
2. reject forged claims, assessments, or assertions;
3. require every assessment to reference a claim present in the snapshot;
4. require every assertion to reference both its exact claim and exact
   assessment in the snapshot;
5. require the assertion's assessment to assess the same claim;
6. canonicalize object ordering;
7. produce deterministic identity from the exact canonical contents.

The same logical snapshot in a different input order must have the same
`snapshot_id`.

A changed claim, assessment, assertion, or membership set must change the
snapshot identity.

## Non-Goals

018 must not:

- infer new assertions;
- infer epistemic status;
- infer architectural ownership;
- convert `CALLS` into `OWNS_RESPONSIBILITY_FOR`;
- decide whether two assertions conflict;
- merge competing assertions;
- choose a winner between claims;
- supersede older claims;
- compute AGREE / CONFLICT / COEXIST / SUPERSEDE;
- inspect source code or execute software.

Those belong to later reasoning/reconciliation capabilities.

019 will define reconciliation semantics from the first real conflict case,
not from graph shape or abstract relation names.

## Readable Projection / Card Shape

018 also provides a pure renderer over an already-valid snapshot.

The renderer performs lookup, ordering, and formatting only. It must not
create or reinterpret assertions.

The readable view uses the same semantic shape as Horizon Cards:

- what it is;
- where it sits;
- what it owns;
- what it depends on;
- what must remain true;
- how we know.

Where the snapshot has no justified fact for a section, the renderer must
show that absence rather than invent content.

Every rendered semantic line must retain:

- epistemic stamp:
  `PROVEN`, `SUPPORTED_HYPOTHESIS`, `DISPUTED`, or `UNKNOWN`;
- exact world-model assertion identity;
- exact claim identity;
- exact assessment identity;
- evidence-reference identities reachable through that claim/assessment.

The renderer is a view. Cards remain views; neither cards nor rendered
snapshots become truth storage.

## Prefect Certification

Certification will answer:

> Who decides whether a failed Prefect flow retries?

The snapshot must contain multiple real Prefect facts, including at least:

- the server retry rule's demonstrated effect on retry eligibility;
- the engine's demonstrated participation in re-execution;
- a narrowly scoped architectural ownership claim with its actual
  epistemic status;
- a competing or unresolved ownership claim carrying a different
  epistemic state.

The rendered output must be human-readable and carry its stamps and
evidence chains.

Success is not merely "snapshot created." Success is that a person can read
the rendered snapshot and distinguish:

- what is proven;
- what is only supported;
- what is disputed;
- what remains unknown;
- why Horizon believes each line.

The certification must preserve the frozen Prefect repository unchanged.

## TDD / Implementation Boundary

Implementation order:

1. RED tests for snapshot closure, integrity, determinism, and immutability.
2. Minimal snapshot implementation.
3. RED tests for pure readable rendering.
4. Minimal renderer.
5. Full Horizon suite.
6. Real Prefect multi-assertion certification.
7. Commit only after all gates pass.

Expected new production surface is limited to the world-model snapshot and
its pure renderer. No reconciliation engine is part of 018.
