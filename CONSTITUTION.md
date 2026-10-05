# HORIZON CONSTITUTION

## Mission

Horizon gives AI agents a continuously maintained understanding of software.

It must understand software at both:

- code level
- architectural level

and make that understanding available to agents through dynamically compiled
Horizon Cards.

Horizon supports two starting conditions:

### Greenfield

Horizon is present while software is created.

It captures:

- requirements
- architectural decisions
- rejected alternatives
- responsibilities
- ownership
- constraints
- invariants
- implementation changes
- tests
- runtime behavior

It then continuously compares intended architecture with the software that
actually exists.

### Brownfield

Horizon enters software whose architecture, decisions, or intent may be
missing, incomplete, stale, or undocumented.

It reconstructs the software world model using available evidence and active
investigation.

---

## 1. The World Model Is The Product

Horizon maintains a living model of the software system.

The model may contain concepts such as:

- systems
- subsystems
- components
- capabilities
- responsibilities
- ownership
- dependencies
- APIs
- data
- state machines
- business rules
- invariants
- behaviors
- side effects
- decisions
- change history
- failure modes

Files and symbols are evidence about this world.

They are not themselves the complete world model.

---

## 2. Cards Are Views, Not Truth Storage

Horizon Cards are compiled from the current world model.

Cards exist to give AI agents the minimum high-value context required to
reason correctly about a task.

Possible views include:

- System Card
- Subsystem Card
- Component Card
- File Card
- Symbol Card
- Invariant Card
- Decision Card
- Change Card
- Task Card

A card must never become an independent stale copy of reality.

Update the world model; regenerate the card.

---

## 3. Horizon Has Epistemic States

Horizon does not force every conclusion into TRUE or UNKNOWN.

A claim may be:

### PROVEN

Available evidence satisfies the claim's proof requirements.

### SUPPORTED_HYPOTHESIS

There is meaningful evidence supporting the claim, but proof is incomplete.

### DISPUTED

Relevant evidence supports incompatible conclusions.

### UNKNOWN

Horizon does not currently have enough information for a useful conclusion.

Hypotheses are allowed.

Pretending hypotheses are proven facts is not.

---

## 4. The Model May Reason, But It Does Not Own Truth

AI models may:

- propose architecture
- identify patterns
- generate hypotheses
- rank explanations
- choose investigations
- interpret evidence
- discover possible relationships

They may not silently promote their own output into proven system truth.

Determinism belongs primarily in Horizon's trust kernel:

- evidence identity
- provenance
- snapshots
- proof dependencies
- coverage
- freshness
- contradiction tracking

Intelligence above that kernel may be probabilistic and exploratory.

---

## 5. Horizon Must Investigate

Horizon is not limited to passive indexing.

When it cannot answer an important question, it should determine:

1. what exact information is missing
2. what evidence could reduce that uncertainty
3. what investigation can obtain that evidence

Possible investigations include:

- inspect source
- inspect compiler/type information
- inspect tests
- inspect Git history
- inspect documentation
- inspect configuration
- trace runtime execution
- run targeted tests
- instrument behavior
- inspect persistence
- inspect network activity
- create a reversible experiment
- test a counterfactual

The fundamental loop is:

QUESTION
→ CURRENT KNOWLEDGE
→ KNOWLEDGE GAP
→ INVESTIGATION
→ NEW EVIDENCE
→ UPDATED WORLD MODEL
→ ANSWER

---

## 6. Greenfield Intent Is First-Class Evidence

For greenfield projects, Horizon must preserve why software was created.

Declared intent includes:

- requirement
- architectural decision
- intended responsibility
- intended ownership
- constraint
- invariant
- rejected alternative

Horizon must later be able to compare:

DECLARED INTENT
vs
CURRENT IMPLEMENTATION
vs
OBSERVED BEHAVIOR

This allows architectural drift and contradiction to be detected.

---

## 7. Brownfield Architecture Is Discovered, Not Assumed

For brownfield projects, documentation and names are evidence, not truth.

Horizon reconstructs understanding from multiple sources and keeps uncertainty
explicit.

It must be able to distinguish:

"This appears to own billing"

from:

"This has been established to own billing."

---

## 8. Architecture Must Be Understandable Above Code

Horizon should eventually answer questions such as:

- What does this system do?
- What are its major subsystems?
- Which component owns this responsibility?
- Where is a decision actually made?
- What state does this component own?
- What invariants must remain true?
- What happens end-to-end during this operation?
- Why does this abstraction exist?
- What would break if this changed?
- Which parts of this answer are not proven?

A list of files, imports, or calls is not sufficient architectural
understanding.

---

## 9. Real Problems Drive Horizon's Architecture

Horizon will not be built from a predetermined checklist of analyzers.

We will select real software and ask difficult understanding questions.

When Horizon fails, we determine why.

The missing capability becomes the next thing we build.

Do not build a capability merely because sophisticated static-analysis systems
usually contain it.

---

## 10. Generalization Is Mandatory

Project-specific hardcoding is failure.

A capability learned while understanding one project must be tested against an
unfamiliar project.

Horizon succeeds only when its understanding transfers.

---

## 11. Unknown Is Better Than Fabrication

Being unable to answer is acceptable.

Inventing architectural certainty is not.

A useful Horizon answer must make clear:

- what it knows
- why it knows it
- what it suspects
- what contradicts it
- what remains unknown
- how the unknown could be investigated

---

## North Star

Horizon should not try to know everything in advance.

It should know what it knows,
know why it knows it,
know what it only suspects,
know what it does not know,
and know how to investigate the difference.
