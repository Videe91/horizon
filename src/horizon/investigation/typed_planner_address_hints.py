"""Bounded deterministic repository address hints for typed planning.

The typed planner must often decide which exact source files to read.

Search observations remain canonical evidence about search results, but a
planner should not need to guess every likely implementation or test path
from scratch when the exact investigation question already contains useful
software vocabulary or symbol-like names.

This module derives navigation hints only from:

- the exact frozen Python repository index; and
- the exact investigation questions.

Hints are not evidence.
Hints are not claims.
Hints cannot support or contradict a hypothesis.
Hints do not read file contents.

They only make existing repository addresses easier for the planner to
select for later legal investigation operations.
"""

from __future__ import annotations

import hashlib
import json
import re

from dataclasses import dataclass

from horizon.repository.python_index import (
    PythonRepositoryIndex,
)


class TypedPlannerAddressHintsError(
    ValueError
):
    """Repository address hints could not be derived canonically."""


MAX_CANDIDATES_PER_QUESTION = 6
MIN_MATCHED_PATH_TOKENS = 2


_STOP_TOKENS = {
    "the",
    "and",
    "or",
    "at",
    "that",
    "which",
    "what",
    "how",
    "into",
    "from",
    "over",
    "than",
    "only",
    "beyond",
    "visible",
    "this",
    "with",
    "for",
    "are",
    "was",
    "were",
    "is",
    "be",
    "been",
    "being",
    "of",
    "to",
    "in",
    "by",
    "if",
    "any",
    "its",
    "their",
    "then",
    "rather",
}


@dataclass(
    frozen=True,
    slots=True,
)
class TypedPlannerAddressCandidate:
    path: str
    lexical_score: int

    matched_tokens: tuple[
        str,
        ...,
    ]

    test_path: bool


@dataclass(
    frozen=True,
    slots=True,
)
class TypedPlannerQuestionAddressHints:
    question: str

    candidates: tuple[
        TypedPlannerAddressCandidate,
        ...,
    ]


@dataclass(
    frozen=True,
    slots=True,
)
class TypedPlannerRepositoryAddressHints:
    source_commit: str
    repository_observation_id: str
    python_repository_index_id: str

    question_hints: tuple[
        TypedPlannerQuestionAddressHints,
        ...,
    ]

    address_hints_id: str


def _canonical_bytes(
    value: object,
) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(
            ",",
            ":",
        ),
        ensure_ascii=True,
        allow_nan=False,
    ).encode(
        "utf-8"
    )


def _identity(
    prefix: str,
    value: object,
) -> str:
    return (
        prefix
        + hashlib.sha256(
            _canonical_bytes(
                value
            )
        ).hexdigest()
    )


def _tokens(
    value: str,
) -> tuple[
    str,
    ...,
]:
    expanded = re.sub(
        r"(?<=[a-z0-9])(?=[A-Z])",
        " ",
        value,
    )

    values = {
        token.lower()
        for token
        in re.findall(
            r"[A-Za-z0-9]+",
            expanded,
        )
        if (
            len(
                token
            )
            >= 3
            and token.lower()
            not in _STOP_TOKENS
        )
    }

    return tuple(
        sorted(
            values
        )
    )


def _is_test_path(
    path: str,
) -> bool:
    parts = tuple(
        value.lower()
        for value
        in path.split(
            "/"
        )
        if value
    )

    if not parts:
        return False

    name = parts[
        -1
    ]

    return (
        "test" in parts
        or "tests" in parts
        or name.startswith(
            "test_"
        )
        or name.endswith(
            "_test.py"
        )
    )


def _candidate(
    *,
    question_tokens: set[str],
    path: str,
) -> TypedPlannerAddressCandidate | None:
    path_tokens = set(
        _tokens(
            path
        )
    )

    matched = tuple(
        sorted(
            question_tokens
            & path_tokens
        )
    )

    if (
        len(
            matched
        )
        < MIN_MATCHED_PATH_TOKENS
    ):
        return None

    test_path = _is_test_path(
        path
    )

    lexical_score = (
        len(
            matched
        )
        * 10
    )

    #
    # Role signals are generic navigation signals.
    #
    # If the exact question asks for implementation,
    # non-test Python paths get a modest preference.
    #
    # If it asks for tests, conventional test paths
    # get a smaller preference.
    #
    if (
        "implementation"
        in question_tokens
        and not test_path
    ):
        lexical_score += 15

    if (
        "test"
        in question_tokens
        and test_path
    ):
        lexical_score += 5

    return TypedPlannerAddressCandidate(
        path=path,
        lexical_score=(
            lexical_score
        ),
        matched_tokens=(
            matched
        ),
        test_path=(
            test_path
        ),
    )


def compile_typed_planner_repository_address_hints(
    *,
    index: PythonRepositoryIndex,
    planning_questions: tuple[
        str,
        ...,
    ],
) -> TypedPlannerRepositoryAddressHints:
    """Compile bounded path-name navigation hints for exact questions."""

    if not isinstance(
        index,
        PythonRepositoryIndex,
    ):
        raise TypedPlannerAddressHintsError(
            "index must be a PythonRepositoryIndex"
        )

    if (
        not isinstance(
            planning_questions,
            tuple,
        )
        or not planning_questions
        or any(
            (
                not isinstance(
                    question,
                    str,
                )
                or not question.strip()
            )
            for question
            in planning_questions
        )
    ):
        raise TypedPlannerAddressHintsError(
            "planning_questions must be a nonempty tuple "
            "of nonempty strings"
        )

    if (
        len(
            planning_questions
        )
        != len(
            set(
                planning_questions
            )
        )
    ):
        raise TypedPlannerAddressHintsError(
            "planning_questions must be unique"
        )

    paths = tuple(
        sorted(
            {
                file.path
                for file
                in index.files
            }
        )
    )

    question_hints = []

    for question in planning_questions:
        question_tokens = set(
            _tokens(
                question
            )
        )

        candidates = []

        for path in paths:
            candidate = _candidate(
                question_tokens=(
                    question_tokens
                ),
                path=path,
            )

            if candidate is not None:
                candidates.append(
                    candidate
                )

        candidates.sort(
            key=lambda item: (
                -item.lexical_score,
                item.path,
            )
        )

        question_hints.append(
            TypedPlannerQuestionAddressHints(
                question=question,
                candidates=tuple(
                    candidates[
                        :MAX_CANDIDATES_PER_QUESTION
                    ]
                ),
            )
        )

    canonical_hints = tuple(
        question_hints
    )

    identity_payload = {
        "schema_version": 1,
        "source_commit": (
            index.commit_sha
        ),
        "repository_observation_id": (
            index.repository_observation_id
        ),
        "python_repository_index_id": (
            index.index_id
        ),
        "question_hints": [
            {
                "question": (
                    value.question
                ),
                "candidates": [
                    {
                        "path": (
                            candidate.path
                        ),
                        "lexical_score": (
                            candidate.lexical_score
                        ),
                        "matched_tokens": list(
                            candidate.matched_tokens
                        ),
                        "test_path": (
                            candidate.test_path
                        ),
                    }
                    for candidate
                    in value.candidates
                ],
            }
            for value
            in canonical_hints
        ],
    }

    return TypedPlannerRepositoryAddressHints(
        source_commit=(
            index.commit_sha
        ),
        repository_observation_id=(
            index.repository_observation_id
        ),
        python_repository_index_id=(
            index.index_id
        ),
        question_hints=(
            canonical_hints
        ),
        address_hints_id=(
            _identity(
                "typed-planner-repository-address-hints:",
                identity_payload,
            )
        ),
    )


def typed_planner_repository_address_hints_payload(
    hints: TypedPlannerRepositoryAddressHints,
) -> dict[
    str,
    object,
]:
    """Return the compact model-facing non-evidentiary hint payload."""

    if not isinstance(
        hints,
        TypedPlannerRepositoryAddressHints,
    ):
        raise TypedPlannerAddressHintsError(
            "hints must be TypedPlannerRepositoryAddressHints"
        )

    return {
        "address_hints_id": (
            hints.address_hints_id
        ),
        "source_commit": (
            hints.source_commit
        ),
        "python_repository_index_id": (
            hints.python_repository_index_id
        ),
        "questions": [
            {
                "question": (
                    value.question
                ),
                "candidates": [
                    {
                        "path": (
                            candidate.path
                        ),
                        "score": (
                            candidate.lexical_score
                        ),
                        "matched_tokens": list(
                            candidate.matched_tokens
                        ),
                        "test_path": (
                            candidate.test_path
                        ),
                    }
                    for candidate
                    in value.candidates
                ],
            }
            for value
            in hints.question_hints
        ],
    }
