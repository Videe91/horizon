# Horizon Grand Challenge 001
## Brownfield Architectural Understanding — Prefect

### Target

Repository:

    PrefectHQ/prefect

Frozen commit:

    2338265f658845a9bef8ce7baf07519b89846dc8

Target role:

    HORIZON_BROWNFIELD_LAB_001

The target repository is immutable for this challenge.

---

# The Question

Starting only from the frozen Prefect repository:

> Explain what happens end-to-end when a user executes a Prefect flow.

Horizon must go beyond listing files, imports, or calls.

It must identify the important architectural participants, what responsibilities
they appear to own, where important decisions are actually made, how state and
control move through the system, and which parts of that understanding are
proven versus inferred.

---

# Required Output

Horizon must eventually produce an answer containing:

## 1. Execution Narrative

A coherent end-to-end explanation of flow execution.

Not:

    file A calls file B calls file C

But something closer to:

    user action
        ->
    runtime responsibility
        ->
    orchestration responsibility
        ->
    state/effect
        ->
    completion/failure behavior

The exact architecture must be discovered from evidence.

---

## 2. Architectural Participants

For each important participant Horizon identifies:

    name
    type of architectural entity
    responsibility
    what it owns
    what it depends on
    why Horizon believes it matters

Possible entity types may include:

    system
    subsystem
    component
    service
    engine
    API
    adapter
    persistence layer
    state machine
    runtime
    other discovered concept

This list is not an ontology requirement.

Horizon may discover better abstractions.

---

## 3. Decision Ownership

Horizon must distinguish:

    participates in a call path

from:

    owns an architectural decision

Examples of questions it should eventually be able to address:

    Who decides whether an operation proceeds?

    Who owns important state transitions?

    Who merely transports or adapts information?

    Where is policy enforced?

No answer should be assumed from naming alone.

---

## 4. State and Behavior

Horizon should identify important state involved in flow execution and explain:

    where it originates
    who may change it
    what governs transitions
    what important effects occur

If Horizon cannot establish these facts, it must say so.

---

## 5. Evidence

Every meaningful architectural claim must be traceable to evidence.

Evidence may eventually include:

    source code
    compiler/type information
    tests
    configuration
    Git history
    documentation
    runtime observations
    experiments
    other observable project artifacts

A model statement by itself is not evidence.

---

# Epistemic States

Every meaningful claim must have one of:

## PROVEN

The available evidence satisfies Horizon's current proof requirements.

## SUPPORTED_HYPOTHESIS

Evidence materially supports the claim, but proof is incomplete.

## DISPUTED

Relevant evidence supports incompatible conclusions.

## UNKNOWN

Horizon currently lacks enough information for a useful conclusion.

Horizon may change a claim's state as investigation proceeds.

---

# Knowledge Gaps

The final answer must explicitly identify important unknowns.

For every important UNKNOWN, Horizon should attempt to state:

    what is missing

    why the missing information matters

    what investigation could reduce the uncertainty

This is part of the challenge, not a failure condition.

---

# Investigation

Horizon is allowed to investigate.

It may eventually:

    search repository content
    inspect source
    inspect tests
    inspect types/compiler information
    inspect Git history
    inspect project documentation
    run targeted tests
    execute code in isolation
    instrument runtime behavior
    perform reversible experiments

But every investigation must preserve provenance.

---

# Prohibited Shortcuts

Horizon must not:

    hardcode Prefect architecture

    encode answers taken from Prefect documentation as internal truth

    treat filenames as architectural proof

    treat function names as effect proof

    treat a single call edge as ownership proof

    silently turn model inference into PROVEN fact

    modify the frozen target to make its answer easier

    use a manually prepared Prefect architecture map as input

---

# Evaluation Dimensions

The challenge will be scored across:

## Correctness

Are the conclusions actually supported?

## Architectural Depth

Does Horizon understand responsibilities and ownership rather than merely code
topology?

## Provenance

Can important conclusions be traced to evidence?

## Uncertainty Discipline

Does Horizon distinguish proof, hypothesis, dispute, and unknown?

## Investigation Quality

When uncertain, does Horizon identify useful ways to learn more?

## Compression

Can Horizon produce an architectural explanation substantially more useful to
an AI agent than raw repository exploration?

## Generality

Did the capability arise from general mechanisms rather than Prefect-specific
rules?

---

# Failure Severity

From least serious to most serious:

    UNKNOWN
    MISSED
    CORRECT_BUT_UNPROVEN
    INCORRECT
    FABRICATED_AS_PROVEN

Horizon should prefer UNKNOWN over fabricated certainty.

---

# Baseline Rule

Before building substantial Horizon machinery, we must establish what the
current minimal system can and cannot discover.

Each capability added after this point must correspond to an observed
understanding failure or investigation need.

---

# Exit Condition

Grand Challenge 001 is not complete because Horizon indexed the repository.

It is complete when Horizon can produce a useful architectural account of
Prefect flow execution that:

    separates evidence from inference

    identifies important responsibilities

    distinguishes participation from ownership

    exposes important unknowns

    can explain why its major conclusions should be trusted

and does so without Prefect-specific hardcoding.
