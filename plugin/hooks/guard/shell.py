"""Small shell tokenizer for command guard rule inputs."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import PurePosixPath


SEPARATORS = {"&&", "||", ";", "&", "|", "|&", "\n"}
WRAPPERS = {
    "sudo",
    "doas",
    "env",
    "command",
    "nohup",
    "timeout",
    "nice",
    "setsid",
    "stdbuf",
    "ionice",
    "exec",
}
SHELLS = {"bash", "sh", "zsh", "dash", "ksh", "mksh", "ash"}
SUDO_OPTIONS_WITH_VALUES = {
    "-A", "-a", "-b", "-C", "-c", "-D", "-g", "-h", "-p", "-R", "-r", "-T", "-t", "-U", "-u",
    "--chdir", "--chroot", "--close-from", "--command-timeout", "--group", "--host",
    "--other-user", "--prompt", "--role", "--type", "--user",
}
# Wrappers that take their own options before the real command: option flags that
# consume a following value, and how many positional arguments precede it.
WRAPPER_OPTIONS: dict[str, tuple[frozenset[str], int]] = {
    "timeout": (frozenset({"-k", "--kill-after", "-s", "--signal"}), 1),
    "nice": (frozenset({"-n", "--adjustment"}), 0),
    "ionice": (frozenset({"-c", "--class", "-n", "--classdata", "-p", "--pid"}), 0),
    "stdbuf": (frozenset({"-i", "--input", "-o", "--output", "-e", "--error"}), 0),
    "setsid": (frozenset(), 0),
    "doas": (frozenset({"-u", "-C"}), 0),
}
CONTROL_WORDS = {
    "!",
    "{",
    "}",
    "case",
    "coproc",
    "do",
    "done",
    "elif",
    "else",
    "esac",
    "fi",
    "for",
    "function",
    "if",
    "in",
    "select",
    "then",
    "time",
    "until",
    "while",
}


@dataclass(frozen=True)
class CommandSegment:
    words: list[str]
    env: dict[str, str] = field(default_factory=dict)
    wrappers: list[str] = field(default_factory=list)
    unsupported: list[str] = field(default_factory=list)

    @property
    def command(self) -> str | None:
        return self.words[0] if self.words else None

    @property
    def args(self) -> list[str]:
        return self.words[1:]


@dataclass(frozen=True)
class ShellParseResult:
    segments: list[CommandSegment]
    unsupported: list[str]
    separators: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Token:
    text: str
    quoted: bool = False


@dataclass(frozen=True)
class TokenizeResult:
    tokens: list[Token]
    unsupported: list[str]


def is_assignment(word: str) -> bool:
    if "=" not in word:
        return False
    name = word.split("=", 1)[0]
    if not name:
        return False
    if not (name[0].isalpha() or name[0] == "_"):
        return False
    return all(char.isalnum() or char == "_" for char in name)


def add_unsupported(unsupported: list[str], construct: str) -> None:
    if construct not in unsupported:
        unsupported.append(construct)


def read_heredoc_delimiter(command: str, index: int) -> tuple[str, int]:
    delimiter = ""
    quote = ""
    while index < len(command):
        char = command[index]
        if quote:
            if char == quote:
                quote = ""
            else:
                delimiter += char
            index += 1
            continue
        if char in {"'", '"'}:
            quote = char
            index += 1
            continue
        if char == "\\":
            index += 1
            if index < len(command):
                delimiter += command[index]
                index += 1
            continue
        if char.isspace() or char in {";", "&", "|", "<", ">"}:
            break
        delimiter += char
        index += 1
    return delimiter, index


def skip_heredoc_bodies(
    command: str,
    index: int,
    heredocs: list[tuple[str, bool]],
    unsupported: list[str],
) -> int:
    """Consume heredoc bodies verbatim so their lines are never parsed as commands."""
    for delimiter, strip_tabs in heredocs:
        terminated = False
        while index < len(command):
            end = command.find("\n", index)
            line = command[index:] if end == -1 else command[index:end]
            index = len(command) if end == -1 else end + 1
            candidate = line.lstrip("\t") if strip_tabs else line
            if candidate.rstrip("\r") == delimiter:
                terminated = True
                break
        if not terminated:
            add_unsupported(unsupported, "unterminated heredoc")
            break
    return index


def tokenize(command: str) -> TokenizeResult:
    tokens: list[Token] = []
    unsupported: list[str] = []
    token = ""
    token_quoted = False
    has_token = False
    quote = ""
    escaped = False
    index = 0
    pending_heredocs: list[tuple[str, bool]] = []

    def flush() -> None:
        nonlocal token, token_quoted, has_token
        if has_token:
            tokens.append(Token(text=token, quoted=token_quoted))
        token = ""
        token_quoted = False
        has_token = False

    def append(text: str, *, quoted: bool = False) -> None:
        nonlocal token, token_quoted, has_token
        token += text
        has_token = True
        if quoted:
            token_quoted = True

    while index < len(command):
        char = command[index]

        if escaped:
            append(char, quoted=True)
            escaped = False
            index += 1
            continue

        if quote == "'":
            if char == "'":
                quote = ""
                has_token = True
            else:
                append(char, quoted=True)
            index += 1
            continue

        if quote == '"':
            if char == '"':
                quote = ""
                has_token = True
                index += 1
                continue
            if char == "\\":
                index += 1
                if index >= len(command):
                    append("\\", quoted=True)
                    continue
                if command[index] == "\n":
                    index += 1
                    continue
                append(command[index], quoted=True)
                index += 1
                continue
            if char == "$" and index + 1 < len(command) and command[index + 1] == "(":
                add_unsupported(unsupported, "command substitution")
            elif char == "`":
                add_unsupported(unsupported, "backtick command substitution")
            append(char, quoted=True)
            index += 1
            continue

        if char == "\\":
            if index + 1 < len(command) and command[index + 1] == "\n":
                index += 2
                continue
            escaped = True
            index += 1
            continue

        if char in {"'", '"'}:
            quote = char
            has_token = True
            index += 1
            continue

        if char == "$" and index + 1 < len(command) and command[index + 1] == "(":
            add_unsupported(unsupported, "command substitution")
        elif char == "`":
            add_unsupported(unsupported, "backtick command substitution")

        if command.startswith("<<", index) and not command.startswith("<<<", index):
            add_unsupported(unsupported, "heredoc")
            index += 2
            strip_tabs = index < len(command) and command[index] == "-"
            if strip_tabs:
                index += 1
            while index < len(command) and command[index] in {" ", "\t"}:
                index += 1
            delimiter, index = read_heredoc_delimiter(command, index)
            if delimiter:
                pending_heredocs.append((delimiter, strip_tabs))
            continue

        if char in {" ", "\t", "\r"}:
            flush()
            index += 1
            continue

        if char == "\n":
            flush()
            tokens.append(Token(text="\n"))
            index += 1
            if pending_heredocs:
                index = skip_heredoc_bodies(command, index, pending_heredocs, unsupported)
                pending_heredocs = []
            continue

        if command.startswith(";;&", index) or command.startswith(";;", index) or command.startswith(";&", index):
            add_unsupported(unsupported, "unsupported control operator")
            flush()
            tokens.append(Token(text=";"))
            index += 3 if command.startswith(";;&", index) else 2
            continue

        if char == ";":
            flush()
            tokens.append(Token(text=";"))
            index += 1
            continue

        if char == "&" and index + 1 < len(command) and command[index + 1] == "&":
            flush()
            tokens.append(Token(text="&&"))
            index += 2
            continue

        if char == "&":
            flush()
            tokens.append(Token(text="&"))
            index += 1
            continue

        if char == "|" and index + 1 < len(command) and command[index + 1] == "&":
            flush()
            tokens.append(Token(text="|&"))
            index += 2
            continue

        if char == "|" and index + 1 < len(command) and command[index + 1] == "|":
            flush()
            tokens.append(Token(text="||"))
            index += 2
            continue

        if char == "|":
            flush()
            tokens.append(Token(text="|"))
            index += 1
            continue

        if char == "(" and not (index > 0 and command[index - 1] in {"$", "<", ">"}):
            add_unsupported(unsupported, "subshell or grouping")
        if char == ")" and not any(
            construct in unsupported for construct in {"command substitution", "process substitution"}
        ):
            add_unsupported(unsupported, "subshell or grouping")
        if char in {"<", ">"} and index + 1 < len(command) and command[index + 1] == "(":
            add_unsupported(unsupported, "process substitution")

        append(char)
        index += 1

    if escaped:
        add_unsupported(unsupported, "trailing escape")
        append("\\")
    if quote:
        add_unsupported(unsupported, "unterminated quote")
    if pending_heredocs:
        add_unsupported(unsupported, "unterminated heredoc")
    flush()
    return TokenizeResult(tokens=tokens, unsupported=unsupported)


def is_duration(word: str) -> bool:
    value = word[:-1] if word[-1:] in {"s", "m", "h", "d"} else word
    try:
        float(value)
    except ValueError:
        return False
    return True


def base_name(word: str) -> str:
    return PurePosixPath(word.replace("\\", "/")).name or word


def is_shell_c_invocation(words: list[str]) -> bool:
    if len(words) < 2:
        return False

    # `busybox sh -c ...` reaches the same place as `sh -c ...`.
    if base_name(words[0]) == "busybox" and base_name(words[1]) in SHELLS:
        return is_shell_c_invocation(words[1:])
    if base_name(words[0]) not in SHELLS:
        return False

    for word in words[1:]:
        if word == "--":
            return False
        if not word.startswith("-") or word == "-":
            return False
        if word == "-c":
            return True
        if word.startswith("--"):
            continue
        if "c" in word[1:]:
            return True

    return False


def normalize_segment(words: list[str], command_unsupported: list[str]) -> CommandSegment | None:
    if not words:
        return None

    env: dict[str, str] = {}
    wrappers: list[str] = []
    index = 0

    while index < len(words) and is_assignment(words[index]):
        name, value = words[index].split("=", 1)
        env[name] = value
        index += 1

    wrapper_unsupported: list[str] = []
    while index < len(words) and base_name(words[index]) in WRAPPERS:
        wrapper = base_name(words[index])
        wrappers.append(wrapper)
        index += 1

        if wrapper in {"sudo", "doas"}:
            while index < len(words) and words[index].startswith("-"):
                option = words[index]
                index += 1
                if option in SUDO_OPTIONS_WITH_VALUES:
                    index += 1
        elif wrapper in WRAPPER_OPTIONS:
            options_with_values, positionals = WRAPPER_OPTIONS[wrapper]
            while index < len(words) and words[index].startswith("-") and words[index] != "-":
                option = words[index]
                index += 1
                if option in options_with_values:
                    index += 1
            # timeout takes a duration before the command; never swallow the command
            # itself when the duration is missing.
            if positionals and index < len(words) and is_duration(words[index]):
                index += positionals
        elif wrapper == "env":
            while index < len(words) and words[index].startswith("-"):
                option = words[index]
                index += 1
                if option in {"-u", "--unset"}:
                    index += 1
            while index < len(words) and is_assignment(words[index]):
                name, value = words[index].split("=", 1)
                env[name] = value
                index += 1
        elif wrapper == "nohup" and index < len(words) and words[index] == "--":
            index += 1

    normalized = words[index:]
    unsupported = [*command_unsupported, *wrapper_unsupported]
    leading = base_name(normalized[0]) if normalized else ""

    if is_shell_c_invocation(normalized):
        add_unsupported(unsupported, "shell -c")
    if leading in {"python", "python3", "node"} and any(flag in normalized[1:] for flag in ("-c", "-e")):
        add_unsupported(unsupported, "inline interpreter code")
    if leading in {"powershell", "pwsh"}:
        add_unsupported(unsupported, "powershell")
    if normalized and normalized[0] in CONTROL_WORDS:
        add_unsupported(unsupported, "shell control syntax")
    # eval re-parses its arguments and xargs builds a command line from stdin, so
    # neither can be analyzed statically: `eval 'rm -rf /'` must not pass silently.
    if leading == "eval":
        add_unsupported(unsupported, "eval")
    if leading == "xargs":
        add_unsupported(unsupported, "xargs")

    return CommandSegment(words=normalized, env=env, wrappers=wrappers, unsupported=unsupported)


def parse(command: str) -> ShellParseResult:
    tokenized = tokenize(command)
    segments: list[CommandSegment] = []
    separators: list[str] = []
    current: list[str] = []
    pending_separator: str | None = None

    for token in tokenized.tokens:
        # A quoted token is data, never an operator: `rm -rf ';' /` is one command.
        if token.text in SEPARATORS and not token.quoted:
            segment = normalize_segment(current, tokenized.unsupported)
            if segment is not None:
                if segments and pending_separator is not None:
                    separators.append(pending_separator)
                segments.append(segment)
            current = []
            pending_separator = token.text
            continue
        current.append(token.text)

    segment = normalize_segment(current, tokenized.unsupported)
    if segment is not None:
        if segments and pending_separator is not None:
            separators.append(pending_separator)
        segments.append(segment)

    unsupported = sorted({*tokenized.unsupported, *(item for segment in segments for item in segment.unsupported)})
    return ShellParseResult(segments=segments, unsupported=unsupported, separators=separators)
