# Capability 021 — AI Investigator

**Status:** design specification
**Principle:** **AI proposes. Horizon verifies. Evidence changes knowledge.**

## Purpose

021 introduces Horizon's first AI boundary. It consumes an unresolved `WorldModelOpenQuestion` plus a bounded, immutable evidence context and returns a **proposal for what Horizon should investigate or reconsider next**. The model never changes the world model directly.

The investigator is provider-neutral. Capability 021 supports two production-capable model adapters: **Anthropic Opus 5.5** and **OpenAI GPT-6 Astra**. Both implement the same investigator contract behind one Horizon AI Middleware. No provider-specific semantics may enter the Horizon domain model.

The Horizon AI Middleware is the only model-facing entrypoint. It may read bounded Horizon state required for an investigation request, compile the deterministic canonical request, invoke a selected provider adapter, validate the returned proposal, and record model-run provenance. Provider adapters do not receive unrestricted Horizon access and may not read or mutate Horizon state directly.

No generic autonomous-agent runtime, hidden routing policy, unrestricted tool-use layer, or multi-agent system is introduced in 021.

## Contract

The investigator receives one `InvestigationRequest` containing the open question, relationship, relevant assertions, claims, assessments, evidence references, and the canonical evidence record for every referenced evidence item. The model therefore receives the evidence content Horizon actually has, not only opaque IDs. The canonical request is deterministic and content-addressed.

Existing identifiers form a closed reference set: any assertion, claim, assessment, evidence, relationship, or question ID emitted by the model that was not present in the request causes the entire proposal to be rejected and the rejection recorded. New `REFINE_OBJECT` candidates are the only exception, and they are candidate definitions rather than pre-existing world-model IDs.

For certification, leave-one-evidence-record-out ablations are recorded for the referenced evidence set so Horizon can measure which evidence materially affects the proposal. Ablation results are evidence about context usefulness; they may not be used to cherry-pick a more favorable certification request.

The output is a strict discriminated schema with exactly four proposal types:

1. `PROPOSE_INVESTIGATION` — identifies additional static, runtime, or causal evidence that would reduce the stated uncertainty.
2. `PROPOSE_HYPOTHESIS` — proposes a candidate interpretation for later evidence testing; it is not a claim or epistemic assessment.
3. `REFINE_OBJECT` — states that the disputed world-model object is too coarse and proposes candidate sub-objects that should be investigated separately.
4. `DECLARE_INSUFFICIENT_EVIDENCE` — records that the supplied context does not justify a narrower proposal and identifies what evidence is missing.

Anything outside this vocabulary is invalid. There is no generic `answer`, `winner`, `conclusion`, `status`, or unrestricted rationale field. Natural-language values are allowed only in semantically typed candidate labels and investigation/missing-evidence questions; they are non-authoritative and cannot enter claim or assessment factories.

For `REFINE_OBJECT`, existing IDs must still come from the request. New candidate objects are **not model-authored world-model IDs**: the model proposes typed candidate definitions and Horizon deterministically assigns candidate identities after schema validation.

## Safety and authority boundary

An `InvestigationProposal` is never an `EvidenceBackedClaim`, `EpistemicAssessment`, or `WorldModelAssertion`. It cannot promote, demote, delete, replace, or prove anything.

In particular, `REFINE_OBJECT` only creates candidate objects. Each refined object becomes a real assertion only after the existing 013–017 evidence pipeline independently supports it. The old coarse assertions may then be replaced only through the explicit supersession event introduced in 019, citing the evidence that justified the replacement.

021 does not decide which proposed investigation actually runs. For this capability that choice belongs to a human or the Grand Challenge script. Autonomous investigation selection remains a named future gap.

## Instruction, context, and provenance

The investigator has **one semantic instruction file and no instruction layering**. Its exact bytes are hashed and the hash is stored with every run. Provider adapters may perform mechanical API wrapping but may not add semantic instructions.

No new context field enters `InvestigationRequest` without an ablation demonstrating that the field changes the investigator's proposal on a registered case. A changed instruction or context contract requires a new hash and recertification.

Every model call produces an immutable run record whose first operational fields are the monetary cost and the pre-registered per-run cost cap, followed by provider, the exact model ID returned by the API, temperature, instruction hash, canonical input hash, canonical output hash, token usage, API/request identity when available, validation result, and rejection reason when invalid. The cost cap is fixed before the call; a certification run that cannot be made within that cap must not be started and is recorded as not run rather than silently raising the budget.

## Provider boundary

The Horizon domain depends on one `InvestigatorModel` port and one provider-neutral Horizon AI Middleware, never directly on Anthropic or OpenAI APIs.

Capability 021 has two production-capable adapters:

- Anthropic Opus 5.5;
- OpenAI GPT-6 Astra.

Both adapters receive the same canonical `InvestigationRequest`, the same single semantic investigator instruction, the same closed identifier set, the same proposal schema, and the same validation boundary. Provider-specific request and response mechanics remain inside the adapters.

The middleware chooses a provider only when explicitly instructed by the caller. Capability 021 does not introduce autonomous routing, model ranking, fallback retries, silent provider substitution, or winner selection.

A failed or invalid Claude result may not be silently retried through OpenAI, and a failed or invalid OpenAI result may not be silently retried through Claude. Every attempted run remains first-class recorded evidence.

For certification adjudication, the scoring model must be independent of the investigator run being scored. The adjudication rubric and adjudicator's single semantic instruction are separately sealed and hashed before live certification. Both hashes are stored with every adjudication result. The adjudicator may not receive hidden semantic instruction layers.

Multi-provider agreement or disagreement is itself observable evidence. It does not directly promote, demote, replace, or prove a Horizon claim.

## Pre-registered Prefect certification

The first live certification uses the frozen Prefect conflict produced by 019:

> Who owns responsibility for prefect retry eligibility decision?

Before the investigator run, the expected proposal class is registered as `REFINE_OBJECT`. Passing requires the proposal to distinguish, semantically rather than by exact wording:

- **retry policy / eligibility ownership**, and
- **retry mechanism / scheduling / re-execution ownership**,

and its missing-evidence questions must identify the unresolved distinction between **who schedules the state transition** and **who triggers the next user-code attempt**.

Certification uses exactly three independent Anthropic Opus 5.5 investigator runs and exactly three independent OpenAI GPT-6 Astra investigator runs at temperature `0`, all with the same sealed investigator instruction, canonical request, provider-neutral semantic contract, and pre-registered per-run cost cap. Temperature zero is a variance-control setting, not a determinism claim.

All six investigator runs are retained, validated, scored, and reported; no run may be discarded, replaced, silently retried through the other provider, or omitted because another result is preferable. Proposal-class or semantic instability within one provider or disagreement across providers is itself a certification finding.

Each live result is scored against the pre-sealed rubric by an adjudicator independent of the investigator run being scored, using the pre-sealed adjudicator instruction. The rubric hash and adjudicator-instruction hash are recorded with every score. The adjudicator judges semantic equivalence; substring or phrase matching is forbidden.

The investigator receives one registered instruction/context contract. Failure is preserved as evidence and investigated; there is no hidden repair prompt, prompt stacking, or cherry-picked retry.

Successful certification requires all six investigator runs and all six adjudications to be reported. Certification proves only that 021 can generate and faithfully record evidence-grounded next-step proposals for this frozen question through both supported providers, including any observed within-provider variance and cross-provider disagreement. It does not certify that a proposal is true.
