# Prefect Card Baseline — Pre 022

This artifact measures Horizon's current understanding before autonomous investigation.

It contains no model-generated architecture and no manually prepared Prefect architecture map.

## Frozen Target

- repository: `PrefectHQ/prefect`
- commit: `2338265f658845a9bef8ce7baf07519b89846dc8`
- repository observation: `git-observation:735c214acf83e7b08e03886c558275f0aaa2c3d0d03d618be9e974edf4b52435`
- snapshot: `world-model-snapshot:6a08193a943398485db7f22264549715a31089caba992b4cf3ef02db6c152738`

## Repository Census

- tracked blobs: 5438
- Python files under `src/prefect`: 851
- Python test files: 559
- first-level source areas discovered: 54

### First-level source areas

- `__main__`
- `_experimental`
- `_flow_run_suspension`
- `_internal`
- `_sdk`
- `_vendor`
- `agent`
- `analytics`
- `artifacts`
- `assets`
- `automations`
- `blocks`
- `bundles`
- `cache_policies`
- `cli`
- `client`
- `concurrency`
- `context`
- `deployments`
- `docker`
- `engine`
- `events`
- `exceptions`
- `filesystems`
- `flow_engine`
- `flow_runs`
- `flows`
- `futures`
- `infrastructure`
- `input`
- `locking`
- `logging`
- `main`
- `plugins`
- `results`
- `runner`
- `runtime`
- `schedules`
- `serializers`
- `server`
- `settings`
- `states`
- `task_engine`
- `task_runners`
- `task_runs`
- `task_worker`
- `tasks`
- `telemetry`
- `testing`
- `transactions`
- `types`
- `utilities`
- `variables`
- `workers`

## Existing Horizon Package Evidence

- project name: `prefect`
- package path: `src/prefect`
- import root: `src`
- top-level package: `prefect`
- package-layout evidence: `python-import-root:7ad6b0b4ddcd123b600b8b92a02204ae16882e05ebd3e18a5c6ae4765f105390`
- pyproject blob evidence: `git-blob-evidence:927a4cb2a45fd9b51f47926c0484991876b47eaf1558de5b85d840f943d6a1d0`
- declared direct project dependencies: 57

## Card Coverage

- justified sections: 2/5
- unsupported sections: 3/5

### Currently unsupported

- `WHAT_IT_IS`
- `WHAT_IT_OWNS`
- `WHAT_MUST_REMAIN_TRUE`

These sections are deliberately left unfilled. Repository topology alone is not architectural proof.

## Rendered Horizon Card

```text
TITLE: Prefect Codebase - Pre-022 Baseline
QUESTION: What can Horizon justify about this codebase before autonomous investigation?

WHAT IT IS
NO JUSTIFIED ASSERTION SELECTED

WHERE IT SITS
[PROVEN] At frozen commit 2338265f658845a9bef8ce7baf07519b89846dc8, the declared Python package path is 'src/prefect', under import root 'src', with top-level package 'prefect'. | evidence=claim-evidence-reference:d4fb9419ecedaddf1ec11d4a8548560e3624bdc83d751cf063a698899020ed24
  relation: python-package:prefect DEPENDS_ON python-import-root:src
  rationale: Horizon derived the package layout from the exact observed pyproject.toml blob at the frozen commit.
  trace: assertion_id=world-model-assertion:46c657b572cb5b0ce0e5f51096da11e3bd5195956f161256dbc600e08f60d3e6 | claim_id=evidence-backed-claim:59b4dcc9fbad3a86efe4519b99c4f0868f5843bad9841d40a997e19c099e7a4b | assessment_id=epistemic-assessment:3924f7e8bbccffd7126001c5fbdab9e108de45fd9634dadd145d82f6ceda2365
  claim="At frozen commit 2338265f658845a9bef8ce7baf07519b89846dc8, the declared Python package path is 'src/prefect', under import root 'src', with top-level package 'prefect'."

WHAT IT OWNS
NO JUSTIFIED ASSERTION SELECTED

WHAT IT DEPENDS ON
[PROVEN] At frozen commit 2338265f658845a9bef8ce7baf07519b89846dc8, project 'prefect' declares 57 direct project dependencies in pyproject.toml. | evidence=claim-evidence-reference:d56b6c18684011d996b0972ce10d43546cf02c450237dbaac1fdd7b6f5dc1593
  relation: python-package:prefect DEPENDS_ON declared-python-dependency-set:2fa7b21971fcddf875f757244befd1e7f4c78f1468a1c8244cf7b73d0cea300b
  rationale: The dependency count and declarations come directly from Horizon's exact pyproject.toml blob evidence.
  trace: assertion_id=world-model-assertion:2059a9dd0a005e777c64f069f2fa59692e4278fb65042230ed81f7b26e87d9f8 | claim_id=evidence-backed-claim:b5f278355b96297e2d703a1dfa37ad943feeb667bfb65194159b0787823bd49c | assessment_id=epistemic-assessment:a96afbbe87a2d156aece38c3dd93170a45e667012c540e1d7b0d648d5a228dc8
  claim="At frozen commit 2338265f658845a9bef8ce7baf07519b89846dc8, project 'prefect' declares 57 direct project dependencies in pyproject.toml."

WHAT MUST REMAIN TRUE
NO JUSTIFIED ASSERTION SELECTED

HOW WE KNOW
[PROVEN] At frozen commit 2338265f658845a9bef8ce7baf07519b89846dc8, project 'prefect' declares 57 direct project dependencies in pyproject.toml.
  rationale: The dependency count and declarations come directly from Horizon's exact pyproject.toml blob evidence.
  evidence: claim-evidence-reference:d56b6c18684011d996b0972ce10d43546cf02c450237dbaac1fdd7b6f5dc1593
  trace: assertion_id=world-model-assertion:2059a9dd0a005e777c64f069f2fa59692e4278fb65042230ed81f7b26e87d9f8 | claim_id=evidence-backed-claim:b5f278355b96297e2d703a1dfa37ad943feeb667bfb65194159b0787823bd49c | assessment_id=epistemic-assessment:a96afbbe87a2d156aece38c3dd93170a45e667012c540e1d7b0d648d5a228dc8
[PROVEN] At frozen commit 2338265f658845a9bef8ce7baf07519b89846dc8, the declared Python package path is 'src/prefect', under import root 'src', with top-level package 'prefect'.
  rationale: Horizon derived the package layout from the exact observed pyproject.toml blob at the frozen commit.
  evidence: claim-evidence-reference:d4fb9419ecedaddf1ec11d4a8548560e3624bdc83d751cf063a698899020ed24
  trace: assertion_id=world-model-assertion:46c657b572cb5b0ce0e5f51096da11e3bd5195956f161256dbc600e08f60d3e6 | claim_id=evidence-backed-claim:59b4dcc9fbad3a86efe4519b99c4f0868f5843bad9841d40a997e19c099e7a4b | assessment_id=epistemic-assessment:3924f7e8bbccffd7126001c5fbdab9e108de45fd9634dadd145d82f6ceda2365
```

## Baseline Interpretation

Horizon can currently establish repository identity, package placement, and declared dependency facts.

It cannot yet justify, for the whole Prefect codebase, what the system is architecturally, what it owns, or which invariants must remain true without further investigation.

That gap is the input to Capability 022.
