"""Shared command-line scanning for guard rules.

Rules across the guard package ask the same two questions of an argument list:
which arguments are not options, and does a given option appear. Both answers
depend on the same conventions — `--` ends the options, some options consume the
next argument, and short options cluster — so the conventions are implemented
once here rather than per rule.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator


def is_short_cluster(token: str) -> bool:
    """Whether the token is a short-option group such as `-rf`."""
    return token.startswith("-") and not token.startswith("--") and token != "-"


def has_option(args: list[str], long: Iterable[str] = (), *, short_letters: str = "") -> bool:
    """Whether an option appears before `--`.

    Short letters are matched inside a cluster too, so `rm -rf` carries both `r`
    and `f`, and `git push -uf` still counts as a force push.
    """
    long_options = set(long)
    for token in args:
        if token == "--":
            return False
        if token in long_options:
            return True
        if short_letters and is_short_cluster(token) and any(letter in token[1:] for letter in short_letters):
            return True
    return False


def iter_positionals(args: list[str], value_options: Iterable[str]) -> Iterator[tuple[int, str]]:
    """Index and text of each argument that is neither an option nor an option value."""
    options_with_values = set(value_options)
    long_options_with_values = [option for option in options_with_values if option.startswith("--")]
    index = 0
    while index < len(args):
        token = args[index]
        if token == "--":
            for rest_index in range(index + 1, len(args)):
                yield rest_index, args[rest_index]
            return
        if token in options_with_values:
            index += 2
            continue
        if token.startswith("--") and any(token.startswith(f"{option}=") for option in long_options_with_values):
            index += 1
            continue
        if token.startswith("-"):
            index += 1
            continue
        yield index, token
        index += 1


def positional_args(args: list[str], value_options: Iterable[str]) -> list[str]:
    return [token for _, token in iter_positionals(args, value_options)]


def first_positional(args: list[str], value_options: Iterable[str]) -> tuple[str | None, list[str]]:
    """The first non-option argument and everything after it, for `<tool> <action> ...`."""
    for index, token in iter_positionals(args, value_options):
        return token, args[index + 1 :]
    return None, []


def has_positional(args: list[str], value_options: Iterable[str]) -> bool:
    return first_positional(args, value_options)[0] is not None
