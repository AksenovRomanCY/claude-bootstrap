"""Small shell tokenizer for command guard rule inputs."""

from __future__ import annotations

from dataclasses import dataclass, field


SEPARATORS = {"&&", "||", ";", "&", "|", "|&", "\n"}
WRAPPERS = {"sudo", "env", "command", "nohup"}
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


def is_shell_c_invocation(words: list[str]) -> bool:
    if len(words) < 2 or words[0] not in {"bash", "sh"}:
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

    while index < len(words) and words[index] in WRAPPERS:
        wrapper = words[index]
        wrappers.append(wrapper)
        index += 1

        if wrapper == "sudo":
            while index < len(words) and words[index].startswith("-"):
                option = words[index]
                index += 1
                if option in {"-A", "-a", "-b", "-C", "-c", "-D", "-g", "-h", "-p", "-R", "-r", "-T", "-t", "-U", "-u"}:
                    index += 1
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
    unsupported = list(command_unsupported)

    if is_shell_c_invocation(normalized):
        unsupported.append("shell -c")
    if normalized and normalized[0] in {"python", "python3", "node"} and any(
        flag in normalized[1:] for flag in ("-c", "-e")
    ):
        unsupported.append("inline interpreter code")
    if normalized and normalized[0] in {"powershell", "pwsh"}:
        unsupported.append("powershell")
    if normalized and normalized[0] in CONTROL_WORDS:
        add_unsupported(unsupported, "shell control syntax")

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
