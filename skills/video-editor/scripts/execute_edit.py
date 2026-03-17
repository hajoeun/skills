#!/usr/bin/env python3
"""Execute video edits from an edit plan JSON using FFmpeg.

Extracts segments from a source video and concatenates them into a new video.

Usage:
    python3 execute_edit.py \
        --edit-plan edit_plan.json \
        --video source.mp4 \
        --output output.mp4 \
        --work-dir /tmp/video-editor.XXXXXX
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


def run_ffmpeg(args: list[str], description: str) -> subprocess.CompletedProcess:
    """Run an FFmpeg command safely using list arguments (no shell)."""
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "warning"] + args
    print(f"  {description}...", file=sys.stderr, flush=True)
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  FFmpeg error: {result.stderr}", file=sys.stderr)
    return result


def get_duration(filepath: str) -> Optional[float]:
    """Get video duration in seconds using ffprobe."""
    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        filepath,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return None
    try:
        data = json.loads(result.stdout)
        return float(data["format"]["duration"])
    except (json.JSONDecodeError, KeyError, ValueError):
        return None


def extract_segment(
    video_path: str,
    start: float,
    end: float,
    output_path: str,
    segment_name: str,
    reencode: bool = False,
) -> bool:
    """Extract a segment from the video. Returns True on success."""
    duration = end - start
    if duration <= 0:
        print(
            f"  Warning: Segment '{segment_name}' has non-positive duration ({duration:.2f}s), skipping",
            file=sys.stderr,
        )
        return False

    if reencode:
        args = [
            "-ss", str(start),
            "-i", video_path,
            "-t", str(duration),
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "18",
            "-c:a", "aac",
            "-b:a", "192k",
            output_path,
        ]
    else:
        args = [
            "-ss", str(start),
            "-i", video_path,
            "-t", str(duration),
            "-c", "copy",
            "-avoid_negative_ts", "make_zero",
            output_path,
        ]

    result = run_ffmpeg(args, f"Extracting '{segment_name}' ({start:.1f}s - {end:.1f}s)")
    if result.returncode != 0:
        return False

    # Verify the extracted segment
    actual_duration = get_duration(output_path)
    if actual_duration is None:
        print(f"  Warning: Could not verify segment '{segment_name}'", file=sys.stderr)
        return True

    # If stream copy produced a significantly different duration, re-encode
    if not reencode and abs(actual_duration - duration) > 1.0:
        print(
            f"  Stream copy inaccurate for '{segment_name}' "
            f"(expected {duration:.1f}s, got {actual_duration:.1f}s). Re-encoding...",
            file=sys.stderr,
        )
        os.remove(output_path)
        return extract_segment(
            video_path, start, end, output_path, segment_name, reencode=True
        )

    return True


def main():
    parser = argparse.ArgumentParser(description="Execute video edit from plan")
    parser.add_argument("--edit-plan", required=True, help="Path to edit plan JSON")
    parser.add_argument("--video", required=True, help="Path to source video")
    parser.add_argument("--output", required=True, help="Path for output video")
    parser.add_argument("--work-dir", required=True, help="Working directory for temp files")
    args = parser.parse_args()

    # Validate inputs
    edit_plan_path = Path(args.edit_plan)
    if not edit_plan_path.exists():
        print(f"Error: Edit plan not found: {args.edit_plan}", file=sys.stderr)
        sys.exit(2)

    video_path = Path(args.video)
    if not video_path.exists():
        print(f"Error: Video not found: {args.video}", file=sys.stderr)
        sys.exit(2)

    work_dir = Path(args.work_dir)
    segments_dir = work_dir / "segments"
    segments_dir.mkdir(parents=True, exist_ok=True)

    # Load edit plan
    try:
        plan = json.loads(edit_plan_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        print(f"Error reading edit plan: {e}", file=sys.stderr)
        sys.exit(1)

    segments = plan if isinstance(plan, list) else plan.get("segments", [])
    if not segments:
        print("Error: No segments found in edit plan", file=sys.stderr)
        sys.exit(1)

    print(f"Processing {len(segments)} segments...", file=sys.stderr, flush=True)

    # Extract each segment
    segment_files = []
    for i, seg in enumerate(segments):
        name = seg.get("name", f"segment_{i + 1}")
        start = float(seg["start"])
        end = float(seg["end"])
        seg_path = str(segments_dir / f"seg_{i + 1:03d}.mp4")

        success = extract_segment(str(video_path), start, end, seg_path, name)
        if success and Path(seg_path).exists():
            segment_files.append(seg_path)
        else:
            print(f"  Error: Failed to extract segment '{name}'", file=sys.stderr)
            sys.exit(1)

    # Create concat list
    concat_list_path = work_dir / "concat_list.txt"
    with open(concat_list_path, "w") as f:
        for seg_file in segment_files:
            # Use absolute paths and escape single quotes in filenames
            abs_path = str(Path(seg_file).resolve())
            escaped = abs_path.replace("'", "'\\''")
            f.write(f"file '{escaped}'\n")

    # Concatenate all segments
    print(f"\nConcatenating {len(segment_files)} segments...", file=sys.stderr, flush=True)
    concat_result = run_ffmpeg(
        [
            "-f", "concat",
            "-safe", "0",
            "-i", str(concat_list_path),
            "-c", "copy",
            args.output,
        ],
        "Merging into final video",
    )

    if concat_result.returncode != 0:
        # If concat with copy fails, try re-encoding
        print("  Stream copy concat failed, trying with re-encoding...", file=sys.stderr)
        concat_result = run_ffmpeg(
            [
                "-f", "concat",
                "-safe", "0",
                "-i", str(concat_list_path),
                "-c:v", "libx264",
                "-preset", "fast",
                "-crf", "18",
                "-c:a", "aac",
                "-b:a", "192k",
                args.output,
            ],
            "Merging with re-encoding",
        )
        if concat_result.returncode != 0:
            print("Error: Failed to concatenate segments", file=sys.stderr)
            sys.exit(1)

    # Report result
    output_path = Path(args.output)
    if not output_path.exists():
        print("Error: Output file was not created", file=sys.stderr)
        sys.exit(1)

    output_duration = get_duration(args.output)
    output_size_mb = output_path.stat().st_size / (1024 * 1024)

    print(f"\nDone!", file=sys.stderr)
    print(f"  Output: {args.output}", file=sys.stderr)
    if output_duration:
        minutes = int(output_duration // 60)
        seconds = output_duration % 60
        print(f"  Duration: {minutes}m {seconds:.1f}s ({output_duration:.1f}s)", file=sys.stderr)
    print(f"  Size: {output_size_mb:.1f} MB", file=sys.stderr)

    # Output JSON summary to stdout for Claude to read
    summary = {
        "output_path": args.output,
        "duration_seconds": output_duration,
        "size_mb": round(output_size_mb, 1),
        "segments_count": len(segment_files),
    }
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
