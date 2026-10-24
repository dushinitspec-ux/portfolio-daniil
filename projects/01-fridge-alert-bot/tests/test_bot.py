import pytest

from app.bot import CommandArgsError, parse_history_args, parse_setlimit_args


def test_history_args_default_hours() -> None:
    assert parse_history_args("bar-fridge") == ("bar-fridge", 24)


def test_history_args_with_hours() -> None:
    assert parse_history_args("bar-fridge 6") == ("bar-fridge", 6)


@pytest.mark.parametrize("args", [None, "", "a b c", "bar-fridge 0", "bar-fridge 999", "x 1.5"])
def test_history_args_invalid(args: str | None) -> None:
    with pytest.raises(CommandArgsError):
        parse_history_args(args)


def test_setlimit_args() -> None:
    assert parse_setlimit_args("freezer-1 -15") == ("freezer-1", -15.0)


def test_setlimit_accepts_decimal_comma() -> None:
    assert parse_setlimit_args("bar-fridge 4,5") == ("bar-fridge", 4.5)


@pytest.mark.parametrize("args", [None, "bar-fridge", "bar-fridge warm", "bar-fridge 99", "a b c"])
def test_setlimit_args_invalid(args: str | None) -> None:
    with pytest.raises(CommandArgsError):
        parse_setlimit_args(args)
