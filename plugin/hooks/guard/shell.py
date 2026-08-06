"""Small shell tokenizer for command guard rule inputs."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import PurePosixPath


SEPARATORS = {"&&", "||", ";", "&", "|", "|&", "\n"}
# Longest first, so `;;&` wins over `;;` and `&&` over `&`. A newline is also a
# separator but is matched separately: it terminates a heredoc redirection.
OPERATORS = (";;&", ";;", ";&", "&&", "||", "|&", ";", "&", "|")
# `case` arm terminators. They only appear inside a case statement, which the
# guard does not model, so they are reported and treated as a plain separator.
CASE_OPERATORS = {";;&": ";", ";;": ";", ";&": ";"}
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


def match_operator(command: str, index: int) -> str | None:
    return next((operator for operator in OPERATORS if command.startswith(operator, index)), None)


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


class Tokenizer:
    """Character-level lexer for the subset of shell the guard models.

    Each method consumes one construct and leaves the cursor on the character
    after it, so quoting and escaping are local to the method that handles them
    rather than flags carried across the whole scan. Anything the guard cannot
    model faithfully is recorded in `unsupported`, which turns into a permission
    prompt instead of a silent mis-parse.
    """

    BLANKS = {" ", "\t", "\r"}

    def __init__(self, command: str) -> None:
        self.command = command
        self.index = 0
        self.tokens: list[Token] = []
        self.unsupported: list[str] = []
        self.pending_heredocs: list[tuple[str, bool]] = []
        self._text = ""
        self._quoted = False
        self._started = False

    # -- cursor ----------------------------------------------------------

    @property
    def at_end(self) -> bool:
        return self.index >= len(self.command)

    def peek(self, offset: int = 0) -> str:
        position = self.index + offset
        return self.command[position] if position < len(self.command) else ""

    def take(self) -> str:
        char = self.command[self.index]
        self.index += 1
        return char

    def looking_at(self, text: str) -> bool:
        return self.command.startswith(text, self.index)

    # -- token accumulation ----------------------------------------------

    def start_token(self) -> None:
        """Mark a token as begun, so `''` produces an empty word rather than nothing."""
        self._started = True

    def add(self, text: str, *, quoted: bool = False) -> None:
        self._text += text
        self._started = True
        if quoted:
            self._quoted = True

    def flush(self) -> None:
        if self._started:
            self.tokens.append(Token(text=self._text, quoted=self._quoted))
        self._text = ""
        self._quoted = False
        self._started = False

    def emit(self, text: str) -> None:
        self.flush()
        self.tokens.append(Token(text=text))

    def mark(self, construct: str) -> None:
        add_unsupported(self.unsupported, construct)

    # -- constructs ------------------------------------------------------

    def run(self) -> TokenizeResult:
        while not self.at_end:
            char = self.peek()
            if char == "\\":
                self.read_escape()
            elif char == "'":
                self.read_single_quoted()
            elif char == '"':
                self.read_double_quoted()
            elif self.looking_at("<<<"):
                self.read_herestring_redirection()
            elif self.looking_at("<<"):
                self.read_heredoc_redirection()
            elif char in self.BLANKS:
                self.flush()
                self.index += 1
            elif char == "\n":
                self.read_newline()
            elif (operator := match_operator(self.command, self.index)) is not None:
                self.read_operator(operator)
            else:
                self.read_word_character()

        if self.pending_heredocs:
            self.mark("unterminated heredoc")
        self.flush()
        return TokenizeResult(tokens=self.tokens, unsupported=self.unsupported)

    def read_escape(self) -> None:
        self.index += 1
        if self.at_end:
            self.mark("trailing escape")
            self.add("\\")
            return
        char = self.take()
        if char == "\n":
            return  # line continuation: the newline is not a separator
        self.add(char, quoted=True)

    def read_single_quoted(self) -> None:
        self.index += 1
        self.start_token()
        while not self.at_end:
            char = self.take()
            if char == "'":
                return
            self.add(char, quoted=True)
        self.mark("unterminated quote")

    def read_double_quoted(self) -> None:
        self.index += 1
        self.start_token()
        while not self.at_end:
            char = self.peek()
            if char == '"':
                self.index += 1
                return
            if char == "\\":
                self.index += 1
                if self.at_end:
                    self.add("\\", quoted=True)
                    break
                escaped = self.take()
                if escaped != "\n":  # line continuation inside quotes
                    self.add(escaped, quoted=True)
                continue
            if char == "$" and self.peek(1) == "(":
                self.mark("command substitution")
            elif char == "`":
                self.mark("backtick command substitution")
            self.add(self.take(), quoted=True)
        self.mark("unterminated quote")

    def read_herestring_redirection(self) -> None:
        """`<<<` feeds a word to stdin. Consuming it keeps the word from being read
        as a heredoc delimiter, which left the command looking unterminated."""
        self.mark("herestring")
        self.index += 3

    def read_heredoc_redirection(self) -> None:
        self.mark("heredoc")
        self.index += 2
        strip_tabs = self.peek() == "-"
        if strip_tabs:
            self.index += 1
        while self.peek() in {" ", "\t"} and not self.at_end:
            self.index += 1
        delimiter, self.index = read_heredoc_delimiter(self.command, self.index)
        if delimiter:
            self.pending_heredocs.append((delimiter, strip_tabs))

    def read_newline(self) -> None:
        self.emit("\n")
        self.index += 1
        if self.pending_heredocs:
            # The body is data, not commands: documenting `rm -rf /` must not deny.
            self.index = skip_heredoc_bodies(self.command, self.index, self.pending_heredocs, self.unsupported)
            self.pending_heredocs = []

    def read_operator(self, operator: str) -> None:
        if operator in CASE_OPERATORS:
            self.mark("unsupported control operator")
        self.emit(CASE_OPERATORS.get(operator, operator))
        self.index += len(operator)

    def read_word_character(self) -> None:
        """Consume one ordinary character, noting constructs the guard cannot model."""
        char = self.peek()
        if char == "$" and self.peek(1) == "(":
            self.mark("command substitution")
        elif char == "`":
            self.mark("backtick command substitution")

        if char == "(" and self.command[self.index - 1 : self.index] not in {"$", "<", ">"}:
            self.mark("subshell or grouping")
        if char == ")" and not {"command substitution", "process substitution"}.intersection(self.unsupported):
            self.mark("subshell or grouping")
        if char in {"<", ">"} and self.peek(1) == "(":
            self.mark("process substitution")

        self.add(self.take())


def tokenize(command: str) -> TokenizeResult:
    return Tokenizer(command).run()


def is_duration(word: str) -> bool:
    value = word[:-1] if word[-1:] in {"s", "m", "h", "d"} else word
    try:
        float(value)
    except ValueError:
        return False
    return True


def base_name(word: str) -> str:
    return PurePosixPath(word.replace("\\", "/")).name or word


def normalized_command(segment: CommandSegment) -> str | None:
    """Command name without its path, so /usr/bin/git is judged as git."""
    if segment.command is None:
        return None
    return base_name(segment.command)


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
