from screensense.integrations.voice import parse_yes_no_intent, stylize_message


def test_stylize_message_humorous_adds_persona() -> None:
    msg = stylize_message("Type error on line 10.", "humorous")
    assert "Type error on line 10." in msg
    assert "help" in msg.lower() or "backup" in msg.lower()


def test_stylize_message_neutral_keeps_text() -> None:
    msg = stylize_message("All good.", "neutral")
    assert msg == "All good."


def test_stylize_message_adds_low_confidence_suffix_when_adaptive() -> None:
    msg = stylize_message(
        "Potential issue found.",
        "friendly",
        context="VS Code",
        confidence=0.6,
        adaptive_mode=True,
    )
    assert "VS Code." in msg
    assert "double-check before acting" in msg


def test_parse_yes_no_intent_accepts_phrases() -> None:
    assert parse_yes_no_intent("yes please do it") is True
    assert parse_yes_no_intent("no stop this") is False
