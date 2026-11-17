"""How big the context is, and how much of it `maha` sends (spec hito 11).

Pure: no I/O. The exact count of each call comes from the provider; what
was added after it is estimated here (§1.2). The policy says how much is
sent at most in one call (§1.3), and `fit()` caps one tool result (§1.6).
"""

import json
from collections.abc import Sequence

from pydantic import BaseModel, Field

from mharness.domain.messages import (
    Message,
    ReasoningBlock,
    TextBlock,
    ToolCallBlock,
    ToolResultBlock,
)
from mharness.domain.model import ToolSpec
from mharness.domain.todo import TODO_TOOL, TodoList, todo_list

# Characters per token, rounded down: English text has about 4 (§1.2).
CHARS_PER_TOKEN = 4

# Tokens sent to the model in one call at most, with any model (§1.3,
# decision 3 of the maintainer).
DEFAULT_BUDGET = 100_000
# Less would archive at every step: the fixed part alone has some 3,500
# tokens, and the project's instructions up to 16,000 (spec hito 10).
MIN_BUDGET = 10_000

# What is kept free for the answer and for an estimate that falls short:
# 15 % of the window, and never less than 16,000 tokens (as OpenCode V2).
RESERVE_SHARE = 0.15
RESERVE_MIN = 16_000

# After archiving, the last whole steps that fit in this share of the
# ceiling are sent as they are (§1.3).
TAIL_SHARE = 0.30

# Characters one tool result puts in the context at once, about 10,000
# tokens (§1.6, decision 6).
OUTPUT_LIMIT = 40_000

# Room kept for the line that says what was cut.
_MARK_ROOM = 300

# What the model sees in place of the archived steps (§1.8).
ARCHIVE_TAG = "context-archive"
# The user's own words kept in the index, the most recent first (as Codex).
USER_WORDS = 20_000
# The archivist's part of the index: about 2,000 tokens (§1.7).
NOTES_CHARS = 8_000
# The tools whose successful calls change a file, by their `path`.
EDIT_TOOLS = ("write_file", "edit_file")

_TODO_MARKS = {"completed": "[x]", "in_progress": "[~]", "pending": "[ ]"}


def estimate(text: str) -> int:
    """Tokens of a text, estimated: characters / 4, rounded up."""
    return -(-len(text) // CHARS_PER_TOKEN)


def message_text(message: Message) -> str:
    """Everything of a message that the model reads, as text."""
    parts: list[str] = []
    for block in message.blocks:
        match block:
            case TextBlock():
                parts.append(block.text)
            case ReasoningBlock():
                parts.append(block.text)
            case ToolCallBlock():
                parts.append(block.name)
                parts.append(block.arguments)
            case ToolResultBlock():
                parts.append(block.content)
    return "\n".join(parts)


def estimate_messages(messages: list[Message]) -> int:
    """Tokens of some messages, estimated."""
    return sum(estimate(message_text(message)) for message in messages)


def tools_text(tools: list[ToolSpec]) -> str:
    """The tools as the model reads them: name, description and schema."""
    return "\n".join(
        f"{tool.name}\n{tool.description}\n{json.dumps(tool.input_schema)}"
        for tool in tools
    )


def estimate_tools(tools: list[ToolSpec]) -> int:
    """Tokens of the tools, estimated."""
    return estimate(tools_text(tools))


class ContextPolicy(BaseModel, frozen=True):
    """How much `maha` sends to the model in one call (§1.3)."""

    # Tokens per call at most, the same with every model.
    budget: int = Field(default=DEFAULT_BUDGET, ge=MIN_BUDGET)
    # The model's context window, from the catalog; None: unknown, and the
    # budget stands for it.
    window: int | None = Field(default=None, gt=0)

    @property
    def effective_window(self) -> int:
        return self.window if self.window is not None else self.budget

    @property
    def reserve(self) -> int:
        """Tokens kept free: 15 % of the window, at least 16,000, and never
        more than half of it (a small local model of 8,192 still works)."""
        window = self.effective_window
        wanted = max(int(window * RESERVE_SHARE), RESERVE_MIN)
        return min(wanted, window // 2)

    @property
    def ceiling(self) -> int:
        """The most tokens a call may send: past it, the oldest steps are
        archived."""
        return min(self.budget, self.effective_window - self.reserve)

    @property
    def tail(self) -> int:
        """Tokens of the last steps kept as they are after archiving."""
        return int(self.ceiling * TAIL_SHARE)

    def answer_room(self, prompt: int, max_output: int | None) -> int | None:
        """The `max_tokens` of a call whose prompt has `prompt` tokens: what
        the model may write without passing its window (§1.4).

        None when nothing is known (the adapter's choice), or when the
        prompt alone fills the window: then the call fails anyway, and the
        provider says why.
        """
        if self.window is None:
            return max_output
        room = self.window - prompt
        if room <= 0:
            return None
        return room if max_output is None else min(max_output, room)


class ContextUsage(BaseModel, frozen=True):
    """What the working window holds, by parts, for `/context` (§1.11).
    Tokens; the parts are estimated, the total uses the exact count of the
    last call when it can."""

    budget: int
    # None: not in the catalog.
    window: int | None
    # Past it, the oldest steps are archived.
    ceiling: int
    system: int
    tools: int
    tool_count: int
    messages: int
    # Of `messages`, the tool results.
    tool_results: int
    # The prompt of the next call, as `maha` counts it (§1.2).
    total: int
    # Whether `total` starts from the provider's exact count.
    exact: bool
    # The prompt of the last call that answered, and the part of it read
    # from the cache, as the provider said; None before the first one.
    last_prompt: int | None = None
    last_cached: int | None = None


def fit(text: str, limit: int = OUTPUT_LIMIT, *, archived_as: str | None = None) -> str:
    """A tool result of at most `limit` characters: as it is if it fits;
    if not, its beginning and its end, and a line that says what was cut
    in the middle (§1.6). The end of a command says what failed."""
    if len(text) <= limit:
        return text
    room = max(limit - _MARK_ROOM, 0)
    head = _head(text, room // 2)
    tail = _tail(text, room - len(head))
    cut = len(text) - len(head) - len(tail)
    mark = f"… [output cut: {cut:,} of {len(text):,} characters left out"
    if archived_as is not None:
        mark += (
            f"; the whole output is archived as {archived_as};"
            f' read it with recall(id="{archived_as}", offset=…)'
        )
    mark += "]"
    return f"{head}\n{mark}\n{tail}"


def _head(text: str, size: int) -> str:
    """The first `size` characters, ending at a line break if one is in
    their second half."""
    head = text[:size]
    newline = head.rfind("\n")
    return head[:newline] if newline >= size // 2 else head


def _tail(text: str, size: int) -> str:
    """The last `size` characters, starting after a line break if one is
    in their first half."""
    if size <= 0:
        return ""
    tail = text[-size:]
    newline = tail.find("\n")
    return tail[newline + 1 :] if 0 <= newline < size // 2 else tail


def step_starts(messages: Sequence[Message]) -> list[int]:
    """Where each step begins: a message of the person, or an answer of the
    model, which its tool results follow. A step is archived whole: a call
    never goes without its result (§1.10)."""
    return [index for index, message in enumerate(messages) if message.role != "tool"]


def archive_cut(messages: Sequence[Message], tail: int, *, start: int = 0) -> int:
    """How many messages, from the start, leave the working window: all but
    the last whole steps that fit in `tail` tokens, and never the last
    step. `start` were archived already; the result is `start` when there
    is nothing more to archive."""
    starts = [index for index in step_starts(messages) if index >= start]
    if not starts or starts[-1] <= start:
        return start
    cut = starts[-1]
    used = estimate_messages(list(messages[cut:]))
    for begin in reversed(starts[:-1]):
        size = estimate_messages(list(messages[begin:cut]))
        if used + size > tail:
            break
        used += size
        cut = begin
    return cut


def archive_index(archived: Sequence[Message], notes: str | None) -> Message:
    """The message that stands for the archived steps, first in the
    conversation (§1.8). The code writes what it knows exactly: what the
    person asked, in their words, the last task list and the files
    changed; `notes` is the archivist's index, None if it failed."""
    parts = [
        "Earlier steps of this conversation are archived. Search or read "
        "them with the recall tool."
    ]
    words = _user_words(archived)
    if words:
        parts.append("What the user asked, in their words:\n" + "\n".join(words))
    todos = _last_todos(archived)
    if todos is not None:
        tasks = " · ".join(
            f"{_TODO_MARKS.get(todo.status, '[-]')} {todo.content}"
            for todo in todos.todos
        )
        parts.append(f"Task list: {tasks}")
    files = _changed_files(archived)
    if files:
        parts.append("Files changed: " + ", ".join(files))
    if notes is not None and notes.strip():
        parts.append("Index (archivist):\n" + fit(notes.strip(), NOTES_CHARS))
    else:
        parts.append("Index: none was written; search the archive for details.")
    body = _unclosed("\n\n".join(parts))
    text = f"<{ARCHIVE_TAG}>\n{body}\n</{ARCHIVE_TAG}>"
    return Message(role="user", blocks=[TextBlock(text=text)])


def _user_words(messages: Sequence[Message]) -> list[str]:
    """The person's messages, quoted, the most recent that fit in
    `USER_WORDS` characters, oldest first."""
    quoted: list[str] = []
    left = USER_WORDS
    for message in reversed(messages):
        if message.role != "user" or not message.text.strip():
            continue
        text = message.text.strip()
        if len(text) > left:
            if quoted:
                break
            text = fit(text, left)
        left -= len(text)
        quoted.append('- "' + text.replace("\n", "\n  ") + '"')
    return quoted[::-1]


def _last_todos(messages: Sequence[Message]) -> TodoList | None:
    """The last valid task list the model wrote."""
    for message in reversed(messages):
        for block in reversed(message.blocks):
            if isinstance(block, ToolCallBlock) and block.name == TODO_TOOL:
                found = todo_list(block.arguments)
                if found is not None:
                    return found
    return None


def _changed_files(messages: Sequence[Message]) -> list[str]:
    """The paths that `write_file` and `edit_file` changed, in order, once."""
    succeeded = {
        block.call_id
        for message in messages
        for block in message.blocks
        if isinstance(block, ToolResultBlock) and not block.is_error
    }
    paths: list[str] = []
    for message in messages:
        for block in message.blocks:
            if (
                isinstance(block, ToolCallBlock)
                and block.name in EDIT_TOOLS
                and block.id in succeeded
            ):
                path = _path_of(block.arguments)
                if path is not None and path not in paths:
                    paths.append(path)
    return paths


def _path_of(arguments: str) -> str | None:
    try:
        value = json.loads(arguments or "{}")
    except ValueError, RecursionError:
        return None
    path = value.get("path") if isinstance(value, dict) else None
    return path if isinstance(path, str) and path else None


def _unclosed(text: str) -> str:
    """Text in the index cannot close it early."""
    return text.replace(f"</{ARCHIVE_TAG}>", f"<\\/{ARCHIVE_TAG}>")
