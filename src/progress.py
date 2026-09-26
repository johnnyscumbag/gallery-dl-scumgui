from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Progress:
    percent: int | None
    downloaded: str
    speed: str


_PROGRESS_RE = re.compile(
    r"\s*(?P<percent>\d{1,3})%\s+"
    r"(?P<downloaded>\S+)\s+"
    r"(?P<speed>\S+)\s*$"
)


def parse_progress(line: str) -> Progress | None:
    """Parse gallery-dl terminal progress output.

    Typical output looks like:
        16%   1.01MB 337.19kB/s

    Progress is written to stderr and refreshed with carriage returns.
    """
    match = _PROGRESS_RE.fullmatch(line.strip())
    if not match:
        return None

    percent = int(match.group("percent"))
    if not 0 <= percent <= 100:
        return None

    return Progress(
        percent=percent,
        downloaded=match.group("downloaded"),
        speed=match.group("speed"),
    )
