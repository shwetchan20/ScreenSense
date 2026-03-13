from screensense.integrations.remote_approval import parse_approval_reply


def test_parse_approval_reply_accepts_yes_with_id() -> None:
    assert parse_approval_reply("yes A1B2C3", "A1B2C3") is True


def test_parse_approval_reply_accepts_no_with_id() -> None:
    assert parse_approval_reply("no A1B2C3", "A1B2C3") is False


def test_parse_approval_reply_ignores_other_ids() -> None:
    assert parse_approval_reply("yes ZZZ999", "A1B2C3") is None
