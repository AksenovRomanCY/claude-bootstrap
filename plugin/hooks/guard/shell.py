"""Small shell tokenizer for command guard rule inputs."""

from __future__ import annotations

from dataclasses import dataclass, field


SEPARATORS = {"&&", "||", ";", "|", "\n"}
WRAPPERS = {"sudo", "env", "command", "nohup"}


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
class TokenizeResult:
    tokens: list[str]
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


def tokenize(command: str) -> TokenizeResult:
    tokens: list[str] = []
    unsupported: list[str] = []
    token = ""
    quote = ""
    escaped = False
    index = 0

    while index < len(command):
        char = command[index]

        if escaped:
            token += char
            escaped = False
            index += 1
            continue

        if quote == "'":
            if char == "'":
                quote = ""
            else:
                token += char
            index += 1
            continue

        if quote == '"':
            if char == '"':
                quote = ""
            elif char == "\\":
                index += 1
                if index < len(command):
                    token += command[index]
                else:
                    token += "\\"
            elif char == "$" and index + 1 < len(command) and command[index + 1] == "(":
                add_unsupported(unsupported, "command substitution")
                token += char
            elif char == "`":
                add_unsupported(unsupported, "backtick command substitution")
                token += char
            else:
                token += char
            index += 1
            continue

        if char == "\\":
            escaped = True
            index += 1
            continue

        if char in {"'", '"'}:
            quote = char
            index += 1
            continue

        if char == "$" and index + 1 < len(command) and command[index + 1] == "(":
            add_unsupported(unsupported, "command substitution")
        elif char == "`":
            add_unsupported(unsupported, "backtick command substitution")
        elif char == "<" and index + 1 < len(command) and command[index + 1] == "<":
            add_unsupported(unsupported, "heredoc")

        if char in {" ", "\t", "\r"}:
            if token:
                tokens.append(token)
                token = ""
            index += 1
            continue

        if char == "\n":
            if token:
                tokens.append(token)
                token = ""
            tokens.append("\n")
            index += 1
            continue

        if char == ";":
            if token:
                tokens.append(token)
                token = ""
            tokens.append(";")
            index += 1
            continue

        if char == "&" and index + 1 < len(command) and command[index + 1] == "&":
            if token:
                tokens.append(token)
                token = ""
            tokens.append("&&")
            index += 2
            continue

        if char == "|" and index + 1 < len(command) and command[index + 1] == "|":
            if token:
                tokens.append(token)
                token = ""
            tokens.append("||")
            index += 2
            continue

        if char == "|":
            if token:
                tokens.append(token)
                token = ""
            tokens.append("|")
            index += 1
            continue

        token += char
        index += 1

    if escaped:
        token += "\\"
    if token:
        tokens.append(token)
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

    return CommandSegment(words=normalized, env=env, wrappers=wrappers, unsupported=unsupported)


def parse(command: str) -> ShellParseResult:
    tokenized = tokenize(command)
    segments: list[CommandSegment] = []
    separators: list[str] = []
    current: list[str] = []
    pending_separator: str | None = None

    for token in tokenized.tokens:
        if token in SEPARATORS:
            segment = normalize_segment(current, tokenized.unsupported)
            if segment is not None:
                if segments and pending_separator is not None:
                    separators.append(pending_separator)
                segments.append(segment)
            current = []
            pending_separator = token
            continue
        current.append(token)

    segment = normalize_segment(current, tokenized.unsupported)
    if segment is not None:
        if segments and pending_separator is not None:
            separators.append(pending_separator)
        segments.append(segment)

    unsupported = sorted({item for segment in segments for item in segment.unsupported})
    return ShellParseResult(segments=segments, unsupported=unsupported, separators=separators)
