import json
from pathlib import Path

from kimi_cli.web.api.sessions import _extract_user_message_at_turn


def _write_wire(path: Path, records: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


def test_extract_user_message_at_turn_string_payload(tmp_path: Path) -> None:
    wire_path = tmp_path / "wire.jsonl"
    _write_wire(
        wire_path,
        [
            {"type": "metadata", "protocol_version": "1.0"},
            {"message": {"type": "TurnBegin", "payload": {"user_input": "first prompt"}}},
            {"message": {"type": "TurnBegin", "payload": {"user_input": "second prompt"}}},
        ],
    )

    assert _extract_user_message_at_turn(wire_path, 1) == "second prompt"


def test_extract_user_message_at_turn_content_parts_payload(tmp_path: Path) -> None:
    wire_path = tmp_path / "wire.jsonl"
    _write_wire(
        wire_path,
        [
            {"type": "metadata", "protocol_version": "1.0"},
            {
                "message": {
                    "type": "TurnBegin",
                    "payload": {
                        "user_input": [
                            {"type": "text", "text": "hello"},
                            {"type": "text", "text": "world"},
                        ]
                    },
                }
            },
        ],
    )

    assert _extract_user_message_at_turn(wire_path, 0) == "hello world"


def test_extract_user_message_at_turn_missing_message_returns_none(tmp_path: Path) -> None:
    wire_path = tmp_path / "wire.jsonl"
    _write_wire(
        wire_path,
        [
            {"type": "metadata", "protocol_version": "1.0"},
            {"message": {"type": "TurnBegin", "payload": {"user_input": "only"}}},
        ],
    )

    assert _extract_user_message_at_turn(wire_path, 1) is None
