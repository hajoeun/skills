#!/usr/bin/env python3
"""SRT subtitle file parser — no external dependencies.

Replaces the original veast srt_parser.py (which used pysrt).
Uses regex-based parsing with Python standard library only.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Security
# ---------------------------------------------------------------------------

_SHELL_META = set('`$();|&><\n\0')


def _validate_path(path_str: str, expected_ext: str | None = None) -> Path:
    """Resolve to absolute path and validate."""
    if any(c in path_str for c in _SHELL_META):
        print(f"Error: path contains shell metacharacters: {path_str}", file=sys.stderr)
        sys.exit(1)
    p = Path(path_str).resolve()
    if not p.exists():
        print(f"Error: file not found: {p}", file=sys.stderr)
        sys.exit(1)
    if expected_ext and p.suffix.lower() != expected_ext:
        print(f"Error: expected {expected_ext} file, got: {p.suffix}", file=sys.stderr)
        sys.exit(1)
    return p


# ---------------------------------------------------------------------------
# Timecode helpers
# ---------------------------------------------------------------------------

_TC_RE = re.compile(
    r"(\d{2}):(\d{2}):(\d{2})[,.](\d{3})"
)


def parse_timecode(tc: str) -> int:
    """Parse 'HH:MM:SS,mmm' or 'HH:MM:SS.mmm' to total milliseconds."""
    m = _TC_RE.match(tc.strip())
    if not m:
        raise ValueError(f"Invalid timecode: {tc}")
    h, mi, s, ms = int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4))
    return h * 3600000 + mi * 60000 + s * 1000 + ms


def format_timecode(ms: int) -> str:
    """Format milliseconds as 'HH:MM:SS,mmm' (SRT format)."""
    if ms < 0:
        ms = 0
    h = ms // 3600000
    ms %= 3600000
    mi = ms // 60000
    ms %= 60000
    s = ms // 1000
    millis = ms % 1000
    return f"{h:02d}:{mi:02d}:{s:02d},{millis:03d}"


def ms_to_ffmpeg_tc(ms: int) -> str:
    """Format milliseconds as 'HH:MM:SS.mmm' (FFmpeg format — dot, not comma)."""
    if ms < 0:
        ms = 0
    h = ms // 3600000
    ms %= 3600000
    mi = ms // 60000
    ms %= 60000
    s = ms // 1000
    millis = ms % 1000
    return f"{h:02d}:{mi:02d}:{s:02d}.{millis:03d}"


# ---------------------------------------------------------------------------
# HTML stripping
# ---------------------------------------------------------------------------

_HTML_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(text: str) -> str:
    """Remove HTML tags from subtitle text."""
    return _HTML_TAG_RE.sub("", text)


# ---------------------------------------------------------------------------
# SRT parsing
# ---------------------------------------------------------------------------

_TIMECODE_LINE_RE = re.compile(
    r"(\d{2}:\d{2}:\d{2}[,.]\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}[,.]\d{3})"
)


def parse_srt(path: str | Path) -> list[dict]:
    """Parse an SRT file and return a list of entry dicts.

    Each entry:
        {"index": int, "start_ms": int, "end_ms": int,
         "start_tc": str, "end_tc": str, "text": str}
    """
    path = Path(path)
    content = path.read_text(encoding="utf-8-sig")  # handle BOM

    entries: list[dict] = []
    blocks = re.split(r"\n\s*\n", content.strip())

    for block in blocks:
        lines = block.strip().split("\n")
        if len(lines) < 2:
            continue

        # First line: index
        idx_line = lines[0].strip()
        if not idx_line.isdigit():
            continue
        index = int(idx_line)

        # Second line: timecodes
        tc_match = _TIMECODE_LINE_RE.match(lines[1].strip())
        if not tc_match:
            continue

        start_tc = tc_match.group(1)
        end_tc = tc_match.group(2)
        start_ms = parse_timecode(start_tc)
        end_ms = parse_timecode(end_tc)

        # Remaining lines: text
        text = _strip_html("\n".join(lines[2:]).strip())

        entries.append({
            "index": index,
            "start_ms": start_ms,
            "end_ms": end_ms,
            "start_tc": start_tc.replace(".", ","),  # normalize to SRT comma format
            "end_tc": end_tc.replace(".", ","),
            "text": text,
        })

    return entries


# ---------------------------------------------------------------------------
# Time range
# ---------------------------------------------------------------------------


def get_time_range(entries: list[dict], start_idx: int, end_idx: int) -> dict:
    """Get time range spanning from start_idx to end_idx (1-based subtitle indices).

    Returns:
        {"start_ms": int, "end_ms": int, "start_tc": str, "end_tc": str,
         "start_ffmpeg": str, "end_ffmpeg": str, "duration_ms": int}
    """
    index_map = {e["index"]: e for e in entries}

    if start_idx not in index_map:
        raise ValueError(f"Subtitle index {start_idx} not found in SRT")
    if end_idx not in index_map:
        raise ValueError(f"Subtitle index {end_idx} not found in SRT")
    if start_idx > end_idx:
        raise ValueError(f"start_idx ({start_idx}) must be <= end_idx ({end_idx})")

    start_ms = index_map[start_idx]["start_ms"]
    end_ms = index_map[end_idx]["end_ms"]

    return {
        "start_ms": start_ms,
        "end_ms": end_ms,
        "start_tc": format_timecode(start_ms),
        "end_tc": format_timecode(end_ms),
        "start_ffmpeg": ms_to_ffmpeg_tc(start_ms),
        "end_ffmpeg": ms_to_ffmpeg_tc(end_ms),
        "duration_ms": end_ms - start_ms,
    }


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_srt(entries: list[dict]) -> list[str]:
    """Check for common SRT issues. Returns list of warning strings."""
    warnings: list[str] = []

    for i, entry in enumerate(entries):
        # Empty text
        if not entry["text"].strip():
            warnings.append(f"Entry {entry['index']}: empty text")

        # Start after end
        if entry["start_ms"] >= entry["end_ms"]:
            warnings.append(
                f"Entry {entry['index']}: start ({entry['start_tc']}) >= end ({entry['end_tc']})"
            )

        # Overlap with next entry
        if i + 1 < len(entries):
            next_entry = entries[i + 1]
            if entry["end_ms"] > next_entry["start_ms"]:
                warnings.append(
                    f"Entry {entry['index']}-{next_entry['index']}: "
                    f"overlap ({entry['end_tc']} > {next_entry['start_tc']})"
                )

    return warnings


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Parse SRT subtitle files (no external dependencies)"
    )
    parser.add_argument("srt_path", help="Path to SRT file")
    parser.add_argument("--validate", action="store_true", help="Run validation checks")
    parser.add_argument("--json", action="store_true", dest="output_json", help="Output as JSON")
    parser.add_argument(
        "--range", nargs=2, type=int, metavar=("START", "END"),
        help="Print time range for subtitle index range"
    )

    args = parser.parse_args()

    path = _validate_path(args.srt_path, expected_ext=".srt")
    entries = parse_srt(path)

    if args.validate:
        warnings = validate_srt(entries)
        if warnings:
            for w in warnings:
                print(f"WARNING: {w}")
            print(f"\n{len(warnings)} warning(s) found in {len(entries)} entries.")
        else:
            print(f"OK: {len(entries)} entries, no issues found.")
        return

    if args.range:
        start_idx, end_idx = args.range
        try:
            tr = get_time_range(entries, start_idx, end_idx)
            print(json.dumps(tr, indent=2, ensure_ascii=False))
        except ValueError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
        return

    if args.output_json:
        print(json.dumps(entries, indent=2, ensure_ascii=False))
        return

    # Default: summary
    print(f"Parsed {len(entries)} subtitle entries from {path.name}")
    if entries:
        first = entries[0]
        last = entries[-1]
        duration_ms = last["end_ms"] - first["start_ms"]
        print(f"  Range: {first['start_tc']} → {last['end_tc']}")
        print(f"  Duration: {ms_to_ffmpeg_tc(duration_ms)}")


if __name__ == "__main__":
    main()
