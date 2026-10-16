"""Read the pipe tables of a delivered Markdown report by section heading."""

from __future__ import annotations


def sections(text: str) -> dict[str, list[str]]:
    """Heading text (without the #s) -> the lines under it, up to the next heading."""
    out: dict[str, list[str]] = {}
    current = ""
    for line in text.splitlines():
        if line.startswith("#"):
            current = line.lstrip("#").strip()
            out[current] = []
        else:
            out.setdefault(current, []).append(line)
    return out


def _cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def table(text: str, heading: str) -> list[dict[str, str]]:
    """The first pipe table under a heading, as one dict per body row."""
    lines = [line for line in sections(text)[heading] if line.startswith("|")]
    if not lines:
        return []
    header = _cells(lines[0])
    return [dict(zip(header, _cells(line))) for line in lines[2:]]


def prose(text: str, heading: str) -> str:
    """The non-table lines under a heading, joined."""
    return "\n".join(line for line in sections(text)[heading] if not line.startswith("|")).strip()
