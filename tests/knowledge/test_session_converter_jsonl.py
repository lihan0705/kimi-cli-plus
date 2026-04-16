from kosong.message import Message

from kimi_cli.knowledge import SessionConverter


def test_session_converter_jsonl_is_newline_delimited():
    messages = [
        Message(role="user", content="Hello"),
        Message(role="assistant", content="Hi"),
    ]

    result = SessionConverter.convert_session_to_jsonl(messages)

    assert result == (
        '{"role":"user","content":"Hello"}\n'
        '{"role":"assistant","content":"Hi"}\n'
    )
