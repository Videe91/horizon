from __future__ import annotations

import json
import os
import selectors
import subprocess
import time
import tokenize
from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from typing import Any

from horizon.languages.python.structure import (
    PythonStructureFact,
    PythonStructureKind,
)
from horizon.repository.git_blob import (
    GitBlobEvidence,
)
from horizon.repository.git_observation import (
    GitCommitObservation,
)


class PythonPyrightCalleeEvidenceError(
    Exception
):
    """Pyright could not establish callee type evidence."""


@dataclass(
    frozen=True,
    slots=True,
)
class PythonPyrightCalleeTypeEvidence:
    source_evidence_id: str
    call_evidence_id: str
    callee_evidence_id: str

    callee_expression: str

    pyright_version: str
    protocol_version: str

    computed_type_json: str
    raw_computed_type_json: str

    evidence_id: str


def _hash_parts(
    prefix: bytes,
    *parts: str,
) -> str:
    digest = sha256()

    digest.update(prefix)

    for part in parts:
        digest.update(
            part.encode(
                "utf-8",
                errors="surrogateescape",
            )
        )
        digest.update(b"\0")

    return digest.hexdigest()


def _run_git(
    repository: Path,
    *args: str,
) -> str:
    completed = subprocess.run(
        [
            "git",
            "-C",
            str(repository),
            *args,
        ],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    return completed.stdout.strip()


def _python_source(
    blob: GitBlobEvidence,
) -> str:
    try:
        encoding, _ = (
            tokenize.detect_encoding(
                BytesIO(
                    blob.content
                ).readline
            )
        )

        return blob.content.decode(
            encoding
        )

    except (
        SyntaxError,
        UnicodeDecodeError,
        LookupError,
    ) as exc:
        raise PythonPyrightCalleeEvidenceError(
            "unable to decode Python source"
        ) from exc


def _lsp_position(
    content: bytes,
    offset: int,
) -> dict[str, int]:
    if (
        offset < 0
        or offset > len(content)
    ):
        raise PythonPyrightCalleeEvidenceError(
            "callee byte offset is outside source"
        )

    try:
        encoding, _ = (
            tokenize.detect_encoding(
                BytesIO(
                    content
                ).readline
            )
        )

    except (
        SyntaxError,
        LookupError,
    ) as exc:
        raise PythonPyrightCalleeEvidenceError(
            "unable to detect Python encoding"
        ) from exc

    prefix = content[
        :offset
    ]

    line = prefix.count(
        b"\n"
    )

    line_start = (
        prefix.rfind(
            b"\n"
        )
        + 1
    )

    line_bytes = content[
        line_start:
        offset
    ]

    fragment_encoding = (
        "utf-8"
        if encoding.lower().replace(
            "_",
            "-",
        )
        == "utf-8-sig"
        else encoding
    )

    if (
        line == 0
        and encoding.lower().replace(
            "_",
            "-",
        )
        == "utf-8-sig"
        and line_bytes.startswith(
            b"\xef\xbb\xbf"
        )
    ):
        line_bytes = line_bytes[3:]

    try:
        text = line_bytes.decode(
            fragment_encoding
        )

    except UnicodeDecodeError as exc:
        raise PythonPyrightCalleeEvidenceError(
            "unable to convert source position"
        ) from exc

    utf16_units = (
        len(
            text.encode(
                "utf-16-le"
            )
        )
        // 2
    )

    return {
        "line": line,
        "character": utf16_units,
    }


def _typeserver_version(
    executable: str,
) -> str:
    resolved = Path(
        executable
    ).resolve()

    candidates = (
        resolved.parent,
        *resolved.parents,
    )

    for directory in candidates:
        package = (
            directory
            / "package.json"
        )

        if not package.is_file():
            continue

        try:
            data = json.loads(
                package.read_text(
                    encoding="utf-8"
                )
            )

        except (
            OSError,
            json.JSONDecodeError,
        ):
            continue

        if (
            data.get("name")
            == "pyright-typeserver"
        ):
            version = data.get(
                "version"
            )

            if (
                isinstance(
                    version,
                    str,
                )
                and version
            ):
                return version

    raise PythonPyrightCalleeEvidenceError(
        "unable to determine "
        "pyright-typeserver version"
    )


def _canonicalize_repository_uris(
    value: Any,
    *,
    root_uri: str,
) -> Any:
    if isinstance(
        value,
        dict,
    ):
        return {
            key: (
                _canonicalize_repository_uris(
                    item,
                    root_uri=root_uri,
                )
            )
            for key, item
            in value.items()
        }

    if isinstance(
        value,
        list,
    ):
        return [
            _canonicalize_repository_uris(
                item,
                root_uri=root_uri,
            )
            for item in value
        ]

    if (
        isinstance(
            value,
            str,
        )
        and value.startswith(
            root_uri
        )
    ):
        suffix = value[
            len(root_uri):
        ]

        return (
            "horizon-repository://"
            + (
                suffix
                if suffix
                else "/"
            )
        )

    return value


class _JsonRpc:
    def __init__(
        self,
        executable: str,
    ) -> None:
        self._process = subprocess.Popen(
            [
                executable,
                "--stdio",
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        self._next_id = 1

    def _send(
        self,
        payload: dict[str, Any],
    ) -> None:
        data = json.dumps(
            payload,
            separators=(",", ":"),
        ).encode(
            "utf-8"
        )

        header = (
            f"Content-Length: "
            f"{len(data)}\r\n\r\n"
        ).encode(
            "ascii"
        )

        if self._process.stdin is None:
            raise PythonPyrightCalleeEvidenceError(
                "type server stdin unavailable"
            )

        self._process.stdin.write(
            header + data
        )

        self._process.stdin.flush()

    def notify(
        self,
        method: str,
        params: Any,
    ) -> None:
        self._send(
            {
                "jsonrpc": "2.0",
                "method": method,
                "params": params,
            }
        )

    def request(
        self,
        method: str,
        params: Any = None,
        *,
        timeout: float = 20.0,
    ) -> Any:
        request_id = self._next_id
        self._next_id += 1

        self._send(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": method,
                "params": params,
            }
        )

        while True:
            message = self._read_message(
                timeout=timeout
            )

            if (
                message.get("id")
                != request_id
            ):
                continue

            if "error" in message:
                raise PythonPyrightCalleeEvidenceError(
                    "type server request failed: "
                    + json.dumps(
                        message["error"],
                        sort_keys=True,
                    )
                )

            return message.get(
                "result"
            )

    def _read_exact(
        self,
        size: int,
        *,
        deadline: float,
    ) -> bytes:
        if self._process.stdout is None:
            raise PythonPyrightCalleeEvidenceError(
                "type server stdout unavailable"
            )

        output = bytearray()

        selector = (
            selectors.DefaultSelector()
        )

        selector.register(
            self._process.stdout,
            selectors.EVENT_READ,
        )

        try:
            while len(output) < size:
                remaining = (
                    deadline
                    - time.monotonic()
                )

                if remaining <= 0:
                    raise PythonPyrightCalleeEvidenceError(
                        "timed out reading "
                        "type server"
                    )

                ready = selector.select(
                    remaining
                )

                if not ready:
                    raise PythonPyrightCalleeEvidenceError(
                        "timed out reading "
                        "type server"
                    )

                chunk = os.read(
                    self._process.stdout.fileno(),
                    size - len(output),
                )

                if not chunk:
                    raise PythonPyrightCalleeEvidenceError(
                        "type server closed stdout"
                    )

                output.extend(
                    chunk
                )

        finally:
            selector.close()

        return bytes(
            output
        )

    def _read_message(
        self,
        *,
        timeout: float,
    ) -> dict[str, Any]:
        deadline = (
            time.monotonic()
            + timeout
        )

        header = bytearray()

        while (
            b"\r\n\r\n"
            not in header
        ):
            header.extend(
                self._read_exact(
                    1,
                    deadline=deadline,
                )
            )

        raw_header, _ = bytes(
            header
        ).split(
            b"\r\n\r\n",
            1,
        )

        content_length: int | None = None

        for line in raw_header.split(
            b"\r\n"
        ):
            key, value = line.split(
                b":",
                1,
            )

            if (
                key.strip().lower()
                == b"content-length"
            ):
                content_length = int(
                    value.strip()
                )

        if content_length is None:
            raise PythonPyrightCalleeEvidenceError(
                "type server response is "
                "missing Content-Length"
            )

        body = self._read_exact(
            content_length,
            deadline=deadline,
        )

        try:
            return json.loads(
                body.decode(
                    "utf-8"
                )
            )

        except (
            UnicodeDecodeError,
            json.JSONDecodeError,
        ) as exc:
            raise PythonPyrightCalleeEvidenceError(
                "invalid type server JSON"
            ) from exc

    def close(
        self,
    ) -> None:
        try:
            if (
                self._process.poll()
                is None
            ):
                try:
                    self.request(
                        "shutdown",
                        None,
                        timeout=5.0,
                    )

                    self.notify(
                        "exit",
                        None,
                    )

                except (
                    PythonPyrightCalleeEvidenceError
                ):
                    pass

                try:
                    self._process.wait(
                        timeout=3.0
                    )

                except (
                    subprocess.TimeoutExpired
                ):
                    self._process.kill()
                    self._process.wait()

        finally:
            for stream in (
                self._process.stdin,
                self._process.stdout,
                self._process.stderr,
            ):
                if stream is not None:
                    stream.close()


def analyze_pyright_callee_type(
    *,
    repository: Path,
    observation: GitCommitObservation,
    blob: GitBlobEvidence,
    call_fact: PythonStructureFact,
    pyright_typeserver: str,
) -> PythonPyrightCalleeTypeEvidence:
    repository = Path(
        repository
    ).resolve()

    if (
        call_fact.kind
        != PythonStructureKind.CALL
    ):
        raise PythonPyrightCalleeEvidenceError(
            "Pyright callee evidence "
            "requires a CALL fact"
        )

    if (
        call_fact.source_evidence_id
        != blob.evidence_id
    ):
        raise PythonPyrightCalleeEvidenceError(
            "CALL fact and source blob "
            "do not match"
        )

    if (
        blob.commit_sha
        != observation.commit_sha
        or blob.repository_observation_id
        != observation.observation_id
    ):
        raise PythonPyrightCalleeEvidenceError(
            "source blob and repository "
            "observation do not match"
        )

    if (
        call_fact.callee_expression
        is None
        or call_fact.callee_byte_start
        is None
        or call_fact.callee_byte_end
        is None
        or call_fact.callee_evidence_id
        is None
    ):
        raise PythonPyrightCalleeEvidenceError(
            "CALL fact has no preserved "
            "callee expression"
        )

    head = _run_git(
        repository,
        "rev-parse",
        "HEAD",
    )

    if head != observation.commit_sha:
        raise PythonPyrightCalleeEvidenceError(
            "repository HEAD does not match "
            "the observed commit"
        )

    executable = Path(
        pyright_typeserver
    )

    if not executable.is_file():
        raise PythonPyrightCalleeEvidenceError(
            "pyright-typeserver executable "
            "was not found"
        )

    pyright_version = (
        _typeserver_version(
            str(executable)
        )
    )

    source = _python_source(
        blob
    )

    source_path = (
        repository
        / blob.path
    ).resolve()

    root_uri = (
        repository.as_uri()
    )

    source_uri = (
        source_path.as_uri()
    )

    start = _lsp_position(
        blob.content,
        call_fact.callee_byte_start,
    )

    end = _lsp_position(
        blob.content,
        call_fact.callee_byte_end,
    )

    rpc = _JsonRpc(
        str(executable)
    )

    try:
        rpc.request(
            "initialize",
            {
                "processId": os.getpid(),
                "rootUri": root_uri,
                "workspaceFolders": [
                    {
                        "uri": root_uri,
                        "name": (
                            repository.name
                        ),
                    }
                ],
                "capabilities": {},
            },
        )

        rpc.notify(
            "initialized",
            {},
        )

        rpc.notify(
            "textDocument/didOpen",
            {
                "textDocument": {
                    "uri": source_uri,
                    "languageId": "python",
                    "version": 1,
                    "text": source,
                }
            },
        )

        protocol_version = rpc.request(
            "typeServer/"
            "getSupportedProtocolVersion",
            None,
        )

        if not isinstance(
            protocol_version,
            str,
        ):
            raise PythonPyrightCalleeEvidenceError(
                "type server returned an "
                "invalid protocol version"
            )

        snapshot = rpc.request(
            "typeServer/getSnapshot",
            None,
        )

        if not isinstance(
            snapshot,
            int,
        ):
            raise PythonPyrightCalleeEvidenceError(
                "type server returned an "
                "invalid snapshot"
            )

        computed = rpc.request(
            "typeServer/getComputedType",
            {
                "arg": {
                    "uri": source_uri,
                    "range": {
                        "start": start,
                        "end": end,
                    },
                },
                "snapshot": snapshot,
            },
        )

    finally:
        rpc.close()

    if computed is None:
        raise PythonPyrightCalleeEvidenceError(
            "Pyright returned no computed "
            "type for the callee expression"
        )

    raw_computed_type_json = (
        json.dumps(
            computed,
            sort_keys=True,
            separators=(",", ":"),
        )
    )

    canonical = (
        _canonicalize_repository_uris(
            computed,
            root_uri=root_uri,
        )
    )

    computed_type_json = json.dumps(
        canonical,
        sort_keys=True,
        separators=(",", ":"),
    )

    evidence_id = (
        "python-pyright-callee-type:"
        + _hash_parts(
            b"horizon.python-pyright-callee-type.v1\0",
            blob.evidence_id,
            call_fact.evidence_id,
            call_fact.callee_evidence_id,
            call_fact.callee_expression,
            pyright_version,
            protocol_version,
            computed_type_json,
        )
    )

    return PythonPyrightCalleeTypeEvidence(
        source_evidence_id=(
            blob.evidence_id
        ),
        call_evidence_id=(
            call_fact.evidence_id
        ),
        callee_evidence_id=(
            call_fact.callee_evidence_id
        ),
        callee_expression=(
            call_fact.callee_expression
        ),
        pyright_version=(
            pyright_version
        ),
        protocol_version=(
            protocol_version
        ),
        computed_type_json=(
            computed_type_json
        ),
        raw_computed_type_json=(
            raw_computed_type_json
        ),
        evidence_id=evidence_id,
    )
