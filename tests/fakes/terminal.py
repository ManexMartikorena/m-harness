"""What a person types, for the terminal tests."""


class ScriptedInput:
    """Returns the scripted lines, then raises EOFError (Ctrl+D)."""

    def __init__(self, *lines: str) -> None:
        self._lines = list(lines)

    async def __call__(self) -> str:
        if not self._lines:
            raise EOFError
        return self._lines.pop(0)
