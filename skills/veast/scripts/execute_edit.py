#!/usr/bin/env python3
"""Video editing pipeline — guide parsing, validation, FFmpeg execution.

Merges guide_parser.py, video_processor.py, orchestrator.py, and utils.py
from the original veast project. No pydantic, no rich.

External dependency: pyyaml (pip install pyyaml)
System dependency: ffmpeg
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# Import parse_srt from sibling module
sys.path.insert(0, str(Path(__file__).resolve().parent))
from parse_srt import get_time_range, ms_to_ffmpeg_tc, parse_srt  # noqa: E402

# ---------------------------------------------------------------------------
# Security
# ---------------------------------------------------------------------------

_SHELL_META = set('`$();|&><\n\0')


def _validate_path(path_str: str, expected_exts: list[str] | None = None) -> Path:
    """Resolve to absolute path and validate."""
    if any(c in path_str for c in _SHELL_META):
        print(f"Error: path contains shell metacharacters: {path_str}", file=sys.stderr)
        sys.exit(1)
    p = Path(path_str).resolve()
    if not p.exists():
        print(f"Error: file not found: {p}", file=sys.stderr)
        sys.exit(1)
    if expected_exts and p.suffix.lower() not in expected_exts:
        print(f"Error: expected {expected_exts} file, got: {p.suffix}", file=sys.stderr)
        sys.exit(1)
    return p


# ---------------------------------------------------------------------------
# Timecode utils (inlined from utils.py)
# ---------------------------------------------------------------------------


def timecode_to_ms(tc: str) -> int:
    """Convert 'HH:MM:SS.mmm' or 'HH:MM:SS,mmm' to milliseconds."""
    tc = tc.strip().replace(",", ".")
    parts = tc.split(":")
    if len(parts) != 3:
        raise ValueError(f"Invalid timecode format: {tc}")
    h = int(parts[0])
    m = int(parts[1])
    sec_parts = parts[2].split(".")
    s = int(sec_parts[0])
    ms = int(sec_parts[1]) if len(sec_parts) > 1 else 0
    return h * 3600000 + m * 60000 + s * 1000 + ms


def ms_to_tc(ms: int) -> str:
    """Convert milliseconds to 'HH:MM:SS.mmm' (FFmpeg format)."""
    return ms_to_ffmpeg_tc(ms)


def format_duration_str(ms: int) -> str:
    """Format milliseconds to human-readable duration."""
    total_s = ms // 1000
    h = total_s // 3600
    m = (total_s % 3600) // 60
    s = total_s % 60
    if h > 0:
        return f"{h}h {m}m {s}s"
    if m > 0:
        return f"{m}m {s}s"
    return f"{s}s"


# ---------------------------------------------------------------------------
# TempDir (inlined from utils.py)
# ---------------------------------------------------------------------------


class TempDir:
    """Context manager for a temporary directory that cleans up on exit."""

    def __init__(self, prefix: str = "veast_") -> None:
        self._prefix = prefix
        self._path: Path | None = None

    def __enter__(self) -> Path:
        self._path = Path(tempfile.mkdtemp(prefix=self._prefix))
        return self._path

    def __exit__(self, *exc: object) -> None:
        if self._path and self._path.exists():
            # Safety: verify it's in a temp location
            path_str = str(self._path)
            tmpdir = tempfile.gettempdir()
            if path_str.startswith(tmpdir) or path_str.startswith("/tmp/"):
                shutil.rmtree(self._path, ignore_errors=True)


# ---------------------------------------------------------------------------
# Guide parser (from guide_parser.py)
# ---------------------------------------------------------------------------


def parse_guide(path: str | Path) -> dict:
    """Parse a YAML editing guide file.

    Returns:
        {"title": str, "sections": {label: {...}}, "sequence": [...], "excluded": [...]}
    """
    try:
        import yaml
    except ImportError:
        print("Error: PyYAML required. Install with: pip install pyyaml", file=sys.stderr)
        sys.exit(1)

    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Guide file not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not isinstance(data, dict):
        raise ValueError("Guide file must contain a YAML mapping at the top level")

    # Parse sections
    sections: dict[str, dict] = {}
    for label, sec_data in data.get("sections", {}).items():
        sub_range = sec_data.get("subtitles", [])
        time_range = sec_data.get("time", [])
        sections[label] = {
            "label": label,
            "subtitle_start": sub_range[0] if len(sub_range) > 0 else 0,
            "subtitle_end": sub_range[1] if len(sub_range) > 1 else 0,
            "time_start": time_range[0] if len(time_range) > 0 else "00:00:00",
            "time_end": time_range[1] if len(time_range) > 1 else "00:00:00",
            "description": sec_data.get("description", ""),
        }

    # Parse sequence
    sequence: list[dict] = []
    for seq_data in data.get("sequence", []):
        segments: list[dict] = []
        for seg_data in seq_data.get("segments", []):
            sub_range = seg_data.get("subtitles", [])
            segments.append({
                "section": seg_data["section"],
                "subtitle_start": sub_range[0] if len(sub_range) > 0 else 0,
                "subtitle_end": sub_range[1] if len(sub_range) > 1 else 0,
            })
        sequence.append({"label": seq_data.get("label", ""), "segments": segments})

    # Parse excluded
    excluded: list[dict] = []
    for exc_data in data.get("excluded", []):
        sub_range = exc_data.get("subtitles", [])
        excluded.append({
            "section": exc_data["section"],
            "subtitle_start": sub_range[0] if len(sub_range) > 0 else 0,
            "subtitle_end": sub_range[1] if len(sub_range) > 1 else 0,
            "reason": exc_data.get("reason", ""),
        })

    return {
        "title": data.get("title", "Untitled"),
        "sections": sections,
        "sequence": sequence,
        "excluded": excluded,
    }


def validate_guide(guide: dict, subtitles: list[dict]) -> list[str]:
    """Validate guide against subtitle entries. Returns list of error messages."""
    errors: list[str] = []
    index_set = {e["index"] for e in subtitles}

    # Validate sections
    for label, section in guide["sections"].items():
        if section["subtitle_start"] not in index_set:
            errors.append(f"Section '{label}': subtitle_start {section['subtitle_start']} not found in SRT")
        if section["subtitle_end"] not in index_set:
            errors.append(f"Section '{label}': subtitle_end {section['subtitle_end']} not found in SRT")
        if section["subtitle_start"] > section["subtitle_end"]:
            errors.append(f"Section '{label}': subtitle_start > subtitle_end")

    # Validate sequence segments
    for seq_entry in guide["sequence"]:
        for seg in seq_entry["segments"]:
            if seg["section"] not in guide["sections"]:
                errors.append(f"Sequence '{seq_entry['label']}': unknown section '{seg['section']}'")
            if seg["subtitle_start"] not in index_set:
                errors.append(f"Sequence '{seq_entry['label']}': subtitle {seg['subtitle_start']} not found")
            if seg["subtitle_end"] not in index_set:
                errors.append(f"Sequence '{seq_entry['label']}': subtitle {seg['subtitle_end']} not found")
            if seg["subtitle_start"] > seg["subtitle_end"]:
                errors.append(f"Sequence '{seq_entry['label']}': subtitle_start > subtitle_end")
            # Check within section bounds
            if seg["section"] in guide["sections"]:
                sec = guide["sections"][seg["section"]]
                if seg["subtitle_start"] < sec["subtitle_start"] or seg["subtitle_end"] > sec["subtitle_end"]:
                    errors.append(
                        f"Sequence '{seq_entry['label']}': subtitles [{seg['subtitle_start']}, {seg['subtitle_end']}] "
                        f"outside section '{seg['section']}' range [{sec['subtitle_start']}, {sec['subtitle_end']}]"
                    )

    return errors


# ---------------------------------------------------------------------------
# Video processor (from video_processor.py)
# ---------------------------------------------------------------------------


class VideoProcessingError(Exception):
    """Raised when an FFmpeg operation fails."""


def _run_ffmpeg(args: list[str]) -> subprocess.CompletedProcess:
    """Run an FFmpeg command and raise on failure."""
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error"] + args
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise VideoProcessingError(f"FFmpeg failed (exit {result.returncode}): {result.stderr.strip()}")
    return result


def check_ffmpeg() -> bool:
    """Check if FFmpeg is available on the system."""
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def get_video_duration(path: str | Path) -> float:
    """Get video duration in seconds using ffprobe."""
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise VideoProcessingError(f"ffprobe failed: {result.stderr.strip()}")
    return float(result.stdout.strip())


def cut_segment(
    source: str | Path, start_tc: str, duration_tc: str,
    output: str | Path, precise: bool = True,
) -> Path:
    """Cut a segment from the source video."""
    output = Path(output)
    if precise:
        args = [
            "-ss", start_tc, "-i", str(source), "-t", duration_tc,
            "-c:v", "libx264", "-crf", "18",
            "-c:a", "aac", "-b:a", "192k",
            "-avoid_negative_ts", "make_zero",
            str(output),
        ]
    else:
        args = [
            "-ss", start_tc, "-i", str(source), "-t", duration_tc,
            "-c", "copy", "-avoid_negative_ts", "make_zero",
            str(output),
        ]
    _run_ffmpeg(args)
    return output


def concat_segments(segment_files: list[Path], output: str | Path) -> Path:
    """Concatenate video segments using FFmpeg concat demuxer."""
    output = Path(output)
    if not segment_files:
        raise VideoProcessingError("No segments to concatenate")

    list_file = output.parent / f"{output.stem}_concat_list.txt"
    try:
        with open(list_file, "w", encoding="utf-8") as f:
            for seg_file in segment_files:
                escaped = str(seg_file.resolve()).replace("'", "'\\''")
                f.write(f"file '{escaped}'\n")

        args = ["-f", "concat", "-safe", "0", "-i", str(list_file), "-c", "copy", str(output)]
        _run_ffmpeg(args)
    finally:
        if list_file.exists():
            list_file.unlink()

    return output


# ---------------------------------------------------------------------------
# Orchestrator (from orchestrator.py)
# ---------------------------------------------------------------------------


def resolve_plan(guide: dict, subtitles: list[dict], source_video: str, output_path: str) -> dict:
    """Convert guide into an execution plan with resolved time ranges."""
    segments: list[dict] = []

    for seq_entry in guide["sequence"]:
        for seg in seq_entry["segments"]:
            tr = get_time_range(subtitles, seg["subtitle_start"], seg["subtitle_end"])
            segments.append({
                "label": seq_entry["label"],
                "section": seg["section"],
                "start_tc": tr["start_ffmpeg"],
                "end_tc": tr["end_ffmpeg"],
                "duration_ms": tr["duration_ms"],
                "duration_tc": ms_to_tc(tr["duration_ms"]),
            })

    return {
        "segments": segments,
        "source_video": str(source_video),
        "output_path": str(output_path),
    }


def print_plan(plan: dict) -> None:
    """Print the edit plan as a formatted table."""
    segments = plan["segments"]
    print(f"\n{'#':>3}  {'Label':<20} {'Section':<15} {'Start':<14} {'End':<14} {'Duration':<10}")
    print("-" * 80)

    total_ms = 0
    for i, seg in enumerate(segments, 1):
        print(
            f"{i:>3}  {seg['label']:<20} {seg['section']:<15} "
            f"{seg['start_tc']:<14} {seg['end_tc']:<14} "
            f"{format_duration_str(seg['duration_ms']):<10}"
        )
        total_ms += seg["duration_ms"]

    print("-" * 80)
    print(f"Total segments: {len(segments)} | Estimated output: {format_duration_str(total_ms)}")


def execute_plan(plan: dict, precise: bool = True) -> str:
    """Execute the edit plan: cut segments and concatenate."""
    if not check_ffmpeg():
        raise VideoProcessingError("FFmpeg not found. Please install FFmpeg.")

    source = plan["source_video"]
    output = plan["output_path"]
    segments = plan["segments"]

    source_dur = get_video_duration(source)
    print(f"Source: {Path(source).name} ({format_duration_str(int(source_dur * 1000))})")
    print(f"Segments: {len(segments)}")
    print(f"Mode: {'precise (re-encode)' if precise else 'fast (stream copy)'}\n")

    with TempDir() as tmp_dir:
        segment_files: list[Path] = []

        for i, seg in enumerate(segments):
            out_file = tmp_dir / f"seg_{i:04d}.mp4"
            print(f"  [{i+1}/{len(segments)}] Cutting: {seg['label']} [{seg['section']}]")
            cut_segment(
                source=source,
                start_tc=seg["start_tc"],
                duration_tc=seg["duration_tc"],
                output=out_file,
                precise=precise,
            )
            segment_files.append(out_file)

        print("\nConcatenating segments...")
        concat_segments(segment_files, output)

    output_dur = get_video_duration(output)
    print(f"\nDone!")
    print(f"  Output: {output}")
    print(f"  Source duration: {format_duration_str(int(source_dur * 1000))}")
    print(f"  Output duration: {format_duration_str(int(output_dur * 1000))}")

    return output


def run_pipeline(
    video_path: str, srt_path: str, guide_path: str,
    output_path: str, preview: bool = False, precise: bool = True,
) -> str | None:
    """Run the full editing pipeline."""
    # Parse SRT
    print(f"Parsing SRT: {Path(srt_path).name}")
    subtitles = parse_srt(srt_path)
    print(f"  Found {len(subtitles)} subtitle entries\n")

    # Parse guide
    guide = parse_guide(guide_path)

    # Validate
    print("Validating guide...")
    errors = validate_guide(guide, subtitles)
    if errors:
        print("Validation errors:")
        for err in errors:
            print(f"  - {err}")
        raise ValueError(f"Guide validation failed with {len(errors)} error(s)")
    print("  Guide is valid\n")

    # Resolve plan
    plan = resolve_plan(guide, subtitles, video_path, output_path)
    print_plan(plan)

    if preview:
        print("\nPreview mode — no video processing performed.")
        return None

    print()
    return execute_plan(plan, precise)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _cmd_validate(args: argparse.Namespace) -> None:
    srt_path = _validate_path(args.srt, expected_exts=[".srt"])
    guide_path = _validate_path(args.guide, expected_exts=[".yaml", ".yml"])

    subtitles = parse_srt(str(srt_path))
    guide = parse_guide(str(guide_path))
    errors = validate_guide(guide, subtitles)

    if errors:
        print(f"FAIL: {len(errors)} error(s)")
        for err in errors:
            print(f"  - {err}")
        sys.exit(1)
    else:
        print(f"OK: guide is valid ({len(subtitles)} subtitles, {len(guide['sequence'])} sequence entries)")


def _cmd_preview(args: argparse.Namespace) -> None:
    video_path = _validate_path(args.video, expected_exts=[".mp4", ".mov", ".mkv"])
    srt_path = _validate_path(args.srt, expected_exts=[".srt"])
    guide_path = _validate_path(args.guide, expected_exts=[".yaml", ".yml"])

    run_pipeline(str(video_path), str(srt_path), str(guide_path), "preview.mp4", preview=True)


def _cmd_execute(args: argparse.Namespace) -> None:
    video_path = _validate_path(args.video, expected_exts=[".mp4", ".mov", ".mkv"])
    srt_path = _validate_path(args.srt, expected_exts=[".srt"])
    guide_path = _validate_path(args.guide, expected_exts=[".yaml", ".yml"])

    output_str = args.output
    if any(c in output_str for c in _SHELL_META):
        print(f"Error: output path contains shell metacharacters", file=sys.stderr)
        sys.exit(1)

    precise = not args.fast
    run_pipeline(str(video_path), str(srt_path), str(guide_path), output_str, precise=precise)


def main() -> None:
    parser = argparse.ArgumentParser(description="Video editing pipeline")
    sub = parser.add_subparsers(dest="command", required=True)

    # validate
    p_val = sub.add_parser("validate", help="Validate guide against SRT")
    p_val.add_argument("--guide", required=True, help="YAML editing guide")
    p_val.add_argument("--srt", required=True, help="SRT subtitle file")
    p_val.set_defaults(func=_cmd_validate)

    # preview
    p_pre = sub.add_parser("preview", help="Preview edit plan without executing")
    p_pre.add_argument("--video", required=True, help="Source video file")
    p_pre.add_argument("--srt", required=True, help="SRT subtitle file")
    p_pre.add_argument("--guide", required=True, help="YAML editing guide")
    p_pre.set_defaults(func=_cmd_preview)

    # execute
    p_exec = sub.add_parser("execute", help="Execute editing pipeline")
    p_exec.add_argument("--video", required=True, help="Source video file")
    p_exec.add_argument("--srt", required=True, help="SRT subtitle file")
    p_exec.add_argument("--guide", required=True, help="YAML editing guide")
    p_exec.add_argument("--output", required=True, help="Output video file path")
    p_exec.add_argument("--fast", action="store_true", help="Stream copy mode (faster but keyframe-aligned)")
    p_exec.set_defaults(func=_cmd_execute)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
