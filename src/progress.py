from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Progress:
    current: int
    total: int

    @property
    def percent(self) -> int:
        if self.total <= 0:
            return 0
        return max(0, min(100, round(self.current * 100 / self.total)))


_PROGRESS_PATTERNS = (
    re.compile(r"(?P<current>\d+)\s*/\s*(?P<total>\d+)"),
    re.compile(r"(?P<percent>\d{1,3})%"),
)


def parse_progress(line: str) -> Progress | None:
    """Parse common count/percentage progress forms from gallery-dl output.

    This intentionally stays conservative. Unknown output is left untouched in
    the log instead of being guessed as progress.
    """
    match = _PROGRESS_PATTERNS[0].search(line)
    if match:
        current = int(match.group("current"))
        total = int(match.group("total"))
        if total > 0 and current <= total:
            return Progress(current, total)

    match = _PROGRESS_PATTERNS[1].search(line)
    if match:
        percent = int(match.group("percent"))
        if 0 <= percent <= 100:
            return Progress(percent, 100)

    return None
