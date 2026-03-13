from screensense.core.window_context import is_blocked_title


def test_blocked_title_matches_case_insensitive_token() -> None:
    assert is_blocked_title("Genshin Impact", ["genshin impact"])


def test_blocked_title_returns_false_for_non_match() -> None:
    assert not is_blocked_title("Visual Studio Code", ["genshin impact"])

