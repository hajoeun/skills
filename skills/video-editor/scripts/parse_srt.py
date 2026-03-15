#!/usr/bin/env python3
"""Parse an SRT subtitle file into structured JSON.

Usage:
    python3 parse_srt.py <srt_path> [--output <output_path>] [--validate]

Examples:
    python3 parse_srt.py subtitles.srt --output srt_data.json
    python3 parse_srt.py subtitles.srt --validate
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


SRT_BLOCK_RE = re.compile(
    r"(\d+)\s*\n"
    r"(\d{2}:\d{2}:\d{2}[,\.]\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}[,\.]\d{3})\s*\n"
    r"((?:(?!\n\n|\n\d+\s*\n\d{2}:\d{2}:\d{2}).)*)",
    re.DOTALL,
)


def timestamp_to_seconds(ts: str) -> float:
    """Convert SRT timestamp (HH:MM:SS,mmm or HH:MM:SS.mmm) to seconds."""
    ts = ts.replace(",", ".")
    parts = ts.split(":")
    hours = int(parts[0])
    minutes = int(parts[1])
    seconds = float(parts[2])
    return hours * 3600 + minutes * 60 + seconds


def parse_srt(content: str) -> list[dict]:
    """Parse SRT content into a list of subtitle entries."""
    # Remove BOM if present
    if content.startswith("\ufeff"):
        content = content[1:]

    # Normalize line endings
    content = content.replace("\r\n", "\n").replace("\r", "\n")

    # Ensure content ends with double newline for regex matching
    if not content.endswith("\n\n"):
        content += "\n\n"

    subtitles = []
    for match in SRT_BLOCK_RE.finditer(content):
        number = int(match.group(1))
        start = match.group(2).replace(".", ",")
        end = match.group(3).replace(".", ",")
        text = match.group(4).strip()

        subtitles.append(
            {
                "number": number,
                "start": start,
                "end": end,
                "start_seconds": round(timestamp_to_seconds(start), 3),
                "end_seconds": round(timestamp_to_seconds(end), 3),
                "text": text,
            }
        )

    # Sort by number to handle out-of-order entries
    subtitles.sort(key=lambda s: s["number"])

    return subtitles


def validate_srt(filepath: Path) -> tuple[bool, list[str]]:
    """Validate an SRT file and return (is_valid, errors)."""
    errors = []

    try:
        # Try UTF-8 first, then fallback encodings
        content = None
        for encoding in ["utf-8-sig", "utf-8", "cp949", "euc-kr", "latin-1"]:
            try:
                content = filepath.read_text(encoding=encoding)
                break
            except (UnicodeDecodeError, LookupError):
                continue

        if content is None:
            return False, ["Failed to decode file with any supported encoding"]

        subtitles = parse_srt(content)

        if not subtitles:
            errors.append("No valid subtitle blocks found")
            return False, errors

        # Check for gaps or duplicates in numbering
        numbers = [s["number"] for s in subtitles]
        if len(numbers) != len(set(numbers)):
            dupes = [n for n in numbers if numbers.count(n) > 1]
            errors.append(f"Duplicate subtitle numbers: {sorted(set(dupes))}")

        # Check for negative durations
        for s in subtitles:
            if s["end_seconds"] < s["start_seconds"]:
                errors.append(
                    f"Subtitle #{s['number']}: end time ({s['end']}) "
                    f"is before start time ({s['start']})"
                )

        # Check for non-monotonic timestamps
        for i in range(1, len(subtitles)):
            if subtitles[i]["start_seconds"] < subtitles[i - 1]["start_seconds"]:
                errors.append(
                    f"Subtitle #{subtitles[i]['number']}: start time is before "
                    f"previous subtitle #{subtitles[i - 1]['number']}"
                )

        return len(errors) == 0, errors

    except Exception as e:
        return False, [f"Error reading file: {e}"]


def main():
    parser = argparse.ArgumentParser(description="Parse SRT subtitle files to JSON")
    parser.add_argument("srt_path", help="Path to the SRT file")
    parser.add_argument("--output", "-o", help="Output JSON file path (default: stdout)")
    parser.add_argument(
        "--validate", action="store_true", help="Only validate, don't output JSON"
    )
    args = parser.parse_args()

    filepath = Path(args.srt_path)
    if not filepath.exists():
        print(f"Error: File not found: {args.srt_path}", file=sys.stderr)
        sys.exit(2)

    if not filepath.suffix.lower() == ".srt":
        print(f"Error: Expected .srt file, got {filepath.suffix}", file=sys.stderr)
        sys.exit(1)

    if args.validate:
        is_valid, errors = validate_srt(filepath)
        if is_valid:
            print("Valid SRT file", file=sys.stderr)
            sys.exit(0)
        else:
            print("Invalid SRT file:", file=sys.stderr)
            for err in errors:
                print(f"  - {err}", file=sys.stderr)
            sys.exit(1)

    # Parse and output
    content = None
    for encoding in ["utf-8-sig", "utf-8", "cp949", "euc-kr", "latin-1"]:
        try:
            content = filepath.read_text(encoding=encoding)
            break
        except (UnicodeDecodeError, LookupError):
            continue

    if content is None:
        print("Error: Failed to decode file", file=sys.stderr)
        sys.exit(1)

    subtitles = parse_srt(content)

    if not subtitles:
        print("Error: No valid subtitle blocks found", file=sys.stderr)
        sys.exit(1)

    result = {
        "subtitles": subtitles,
        "total_count": len(subtitles),
    }

    output_json = json.dumps(result, ensure_ascii=False, indent=2)

    if args.output:
        Path(args.output).write_text(output_json, encoding="utf-8")
        print(f"Wrote {len(subtitles)} subtitles to {args.output}", file=sys.stderr)
    else:
        print(output_json)


if __name__ == "__main__":
    main()
