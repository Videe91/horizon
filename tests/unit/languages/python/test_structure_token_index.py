from __future__ import annotations

import horizon.languages.python.structure as structure_module

from horizon.languages.python.structure import (
    PythonStructureKind,
    analyze_python_blob,
)
from horizon.repository.git_blob import (
    GitBlobEvidence,
)


def _blob(
    content: bytes,
) -> GitBlobEvidence:
    return GitBlobEvidence(
        path="generated.py",
        commit_sha="a" * 40,
        repository_observation_id=(
            "git-observation:test"
        ),
        object_id="b" * 40,
        content=content,
        evidence_id=(
            "git-blob-evidence:test"
        ),
    )


def test_callee_token_position_work_is_bounded_by_file_size(
    monkeypatch,
) -> None:
    call_count = 160

    source = (
        "def generated():\n"
        + "".join(
            (
                f"    value_{index} = "
                f"service_{index}.execute("
                f"{index})\n"
            )
            for index
            in range(
                call_count
            )
        )
    ).encode(
        "utf-8"
    )

    position_calls = 0

    original = (
        structure_module
        ._StructureVisitor
        ._position_to_byte
    )

    def counted(
        self,
        position,
    ):
        nonlocal position_calls

        position_calls += 1

        return original(
            self,
            position,
        )

    monkeypatch.setattr(
        structure_module._StructureVisitor,
        "_position_to_byte",
        counted,
    )

    analysis = analyze_python_blob(
        _blob(
            source
        )
    )

    calls = [
        fact
        for fact
        in analysis.facts
        if fact.kind
        is PythonStructureKind.CALL
    ]

    assert (
        len(
            calls
        )
        == call_count
    )

    # A bounded token index should convert token positions roughly once
    # per token for the file, not once per token for every CALL.
    #
    # The old implementation is quadratic here and exceeds this bound
    # by a large margin. The indexed implementation stays comfortably
    # below it without relying on wall-clock timing.
    assert (
        position_calls
        < 10_000
    )


def test_indexed_lookup_preserves_multiline_callee_bytes() -> None:
    content = b"""\
def run():
    return (
        service
        .client
        .execute
    )(
        value
    )
"""

    analysis = analyze_python_blob(
        _blob(
            content
        )
    )

    calls = [
        fact
        for fact
        in analysis.facts
        if fact.kind
        is PythonStructureKind.CALL
    ]

    assert calls

    outer = max(
        calls,
        key=lambda fact: (
            fact.byte_end
            - fact.byte_start
        ),
    )

    assert (
        outer.callee_expression
        is not None
    )

    assert (
        content[
            outer.callee_byte_start:
            outer.callee_byte_end
        ].decode(
            "utf-8"
        )
        == outer.callee_expression
    )
