#!/usr/bin/env python3
"""FCPXML round-trip reordering — Phase 3C of the veast pipeline.

Reorders a DaVinci Resolve FCPXML timeline based on an edit guide,
producing a reordered .fcpxml and reordered .srt file.

Usage:
    python3 resolve_xml.py validate --fcpxml <f> --srt <s> --guide <g>
    python3 resolve_xml.py preview  --fcpxml <f> --srt <s> --guide <g>
    python3 resolve_xml.py reorder  --fcpxml <f> --srt <s> --guide <g> \
        --output-fcpxml <out.fcpxml> --output-srt <out.srt>

External dependency: pyyaml (pip install pyyaml)
"""

from __future__ import annotations

import argparse
import copy
import sys
import xml.etree.ElementTree as ET
from fractions import Fraction
from pathlib import Path

# Import from sibling modules
sys.path.insert(0, str(Path(__file__).resolve().parent))
from parse_srt import format_timecode, get_time_range, parse_srt  # noqa: E402
from execute_edit import parse_guide, validate_guide  # noqa: E402

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


def _validate_output_path(path_str: str, expected_ext: str) -> Path:
    """Validate output path (parent must exist, correct extension)."""
    if any(c in path_str for c in _SHELL_META):
        print(f"Error: path contains shell metacharacters: {path_str}", file=sys.stderr)
        sys.exit(1)
    p = Path(path_str).resolve()
    if not p.parent.exists():
        print(f"Error: output directory does not exist: {p.parent}", file=sys.stderr)
        sys.exit(1)
    if p.suffix.lower() != expected_ext:
        print(f"Error: expected {expected_ext} extension, got: {p.suffix}", file=sys.stderr)
        sys.exit(1)
    return p


# ---------------------------------------------------------------------------
# FCPXML Rational Timecode Helpers
# ---------------------------------------------------------------------------

def parse_rational(s: str) -> Fraction:
    """Parse FCPXML rational timecode like '59850791/24000s' or '0/1s'."""
    s = s.rstrip("s")
    if "/" in s:
        num, den = s.split("/")
        return Fraction(int(num), int(den))
    return Fraction(int(s))


def rational_to_str(f: Fraction) -> str:
    """Convert Fraction to FCPXML timecode string."""
    return f"{f.numerator}/{f.denominator}s"


def ms_to_fraction(ms: int) -> Fraction:
    """Convert milliseconds to Fraction seconds."""
    return Fraction(ms, 1000)


def snap_to_frame(t: Fraction, frame_dur: Fraction) -> Fraction:
    """Snap a time value to the nearest frame boundary."""
    frames = round(t / frame_dur)
    return frames * frame_dur


# ---------------------------------------------------------------------------
# FCPXML Validation
# ---------------------------------------------------------------------------

_SUPPORTED_VERSIONS = {"1.8", "1.9", "1.10", "1.11", "1.12", "1.13"}


def validate_fcpxml(root: ET.Element) -> list[str]:
    """Validate FCPXML structure. Returns list of error messages (empty = valid)."""
    errors: list[str] = []

    # Check version
    version = root.get("version", "")
    if version not in _SUPPORTED_VERSIONS:
        errors.append(f"Unsupported FCPXML version: '{version}' (supported: {', '.join(sorted(_SUPPORTED_VERSIONS))})")

    # Check spine
    spine = root.find(".//spine")
    if spine is None:
        errors.append("No <spine> element found in FCPXML")
        return errors  # can't continue without spine

    # Check clips in spine
    clip_count = sum(1 for c in spine if c.tag in ("clip", "asset-clip", "gap"))
    if clip_count == 0:
        errors.append("No clips found in <spine>")

    # Check format with frameDuration
    fmt = root.find(".//format")
    if fmt is None:
        errors.append("No <format> element found — cannot determine frame duration")
    elif not fmt.get("frameDuration"):
        errors.append("<format> element missing frameDuration attribute")

    return errors


# ---------------------------------------------------------------------------
# Spine Analysis
# ---------------------------------------------------------------------------

def analyze_spine(spine_elem: ET.Element) -> list[dict]:
    """Extract spine clips with their timeline and source ranges."""
    clips = []
    for clip_elem in spine_elem:
        if clip_elem.tag not in ("clip", "asset-clip", "gap"):
            continue
        offset = parse_rational(clip_elem.get("offset", "0/1s"))
        duration = parse_rational(clip_elem.get("duration", "0/1s"))
        start = parse_rational(clip_elem.get("start", "0/1s"))
        clips.append({
            "element": clip_elem,
            "offset": offset,
            "duration": duration,
            "start": start,
            "end": start + duration,
            "timeline_start": offset,
            "timeline_end": offset + duration,
        })
    return clips


# ---------------------------------------------------------------------------
# Core: Split and Reorder
# ---------------------------------------------------------------------------

def find_clip_for_time(spine_clips: list[dict], timeline_time: Fraction) -> dict | None:
    """Find which spine clip contains a given timeline time."""
    for clip in spine_clips:
        if clip["timeline_start"] <= timeline_time < clip["timeline_end"]:
            return clip
    # Edge case: exact end of last clip
    if spine_clips and timeline_time == spine_clips[-1]["timeline_end"]:
        return spine_clips[-1]
    return None


def create_sub_clip(
    original_clip: dict,
    seg_timeline_start: Fraction,
    seg_timeline_end: Fraction,
    new_offset: Fraction,
    frame_dur: Fraction,
) -> ET.Element:
    """Create a new clip element that is a sub-range of an original spine clip.

    Adjusts the source in-point (start) based on where in the original clip
    the segment begins, and updates all child elements accordingly.
    """
    orig_elem = original_clip["element"]
    orig_start = original_clip["start"]
    orig_timeline_start = original_clip["timeline_start"]

    # How far into the original clip does our segment start/end?
    delta_start = seg_timeline_start - orig_timeline_start
    delta_end = seg_timeline_end - orig_timeline_start

    # New source in-point and duration
    new_source_start = snap_to_frame(orig_start + delta_start, frame_dur)
    new_duration = snap_to_frame(delta_end - delta_start, frame_dur)

    # Deep copy the original clip element
    new_elem = copy.deepcopy(orig_elem)

    # Update main clip attributes
    new_elem.set("offset", rational_to_str(snap_to_frame(new_offset, frame_dur)))
    new_elem.set("start", rational_to_str(new_source_start))
    new_elem.set("duration", rational_to_str(new_duration))

    # Update all child elements (connected clips, audio, etc.)
    _update_children(new_elem, orig_elem, new_source_start, new_duration, new_offset, frame_dur)

    return new_elem


def _update_children(
    new_parent: ET.Element,
    orig_parent: ET.Element,
    new_source_start: Fraction,
    new_duration: Fraction,
    new_offset: Fraction,
    frame_dur: Fraction,
) -> None:
    """Update child elements' offset/start/duration to match the new clip range."""
    for child in new_parent:
        tag = child.tag

        if tag in ("adjust-transform", "adjust-volume"):
            continue

        if tag in ("clip", "asset-clip", "video", "audio"):
            lane = child.get("lane")
            if lane is not None:
                # Connected clip or separate track
                child.set("offset", rational_to_str(new_source_start))
                child.set("duration", rational_to_str(new_duration))

                # For connected clips with their own start, adjust relative to original
                if child.get("start") is not None and tag in ("clip", "asset-clip"):
                    orig_child = None
                    for oc in orig_parent:
                        if oc.get("lane") == lane and oc.tag == tag:
                            orig_child = oc
                            break
                    if orig_child is not None:
                        orig_child_start = parse_rational(orig_child.get("start", "0/1s"))
                        orig_parent_start = parse_rational(orig_parent.get("start", "0/1s"))
                        parent_delta = new_source_start - orig_parent_start
                        new_child_start = snap_to_frame(orig_child_start + parent_delta, frame_dur)
                        child.set("start", rational_to_str(new_child_start))

            # Recurse into children
            orig_child_elem = None
            for oc in orig_parent:
                if oc.get("lane") == child.get("lane") and oc.tag == child.tag:
                    orig_child_elem = oc
                    break
            if orig_child_elem is not None:
                _update_children(child, orig_child_elem, new_source_start, new_duration, new_offset, frame_dur)


# ---------------------------------------------------------------------------
# Segment Resolution
# ---------------------------------------------------------------------------

def resolve_segments(guide: dict, subtitles: list[dict]) -> list[dict]:
    """Convert guide sequence into timeline ranges using SRT timecodes.

    Returns list of:
        {"label": str, "section": str, "sub_range": str,
         "timeline_start": Fraction, "timeline_end": Fraction, "duration": Fraction}
    """
    sub_map = {s["index"]: s for s in subtitles}
    resolved = []

    for seq_entry in guide["sequence"]:
        for seg in seq_entry["segments"]:
            start_sub = sub_map.get(seg["subtitle_start"])
            end_sub = sub_map.get(seg["subtitle_end"])

            if not start_sub or not end_sub:
                print(f"  WARNING: Subtitle {seg['subtitle_start']}-{seg['subtitle_end']} not found, skipping",
                      file=sys.stderr)
                continue

            tl_start = ms_to_fraction(start_sub["start_ms"])
            tl_end = ms_to_fraction(end_sub["end_ms"])

            resolved.append({
                "label": seq_entry["label"],
                "section": seg["section"],
                "sub_range": f"{seg['subtitle_start']}-{seg['subtitle_end']}",
                "subtitle_start": seg["subtitle_start"],
                "subtitle_end": seg["subtitle_end"],
                "timeline_start": tl_start,
                "timeline_end": tl_end,
                "duration": tl_end - tl_start,
            })

    return resolved


# ---------------------------------------------------------------------------
# SRT Reordering
# ---------------------------------------------------------------------------

def generate_reordered_srt(
    guide: dict,
    subtitles: list[dict],
    output_path: Path,
) -> dict:
    """Reorder SRT subtitles according to edit guide sequence.

    Returns summary: {"total_subtitles": int, "total_duration_ms": int}
    """
    sub_map = {s["index"]: s for s in subtitles}
    reordered: list[dict] = []
    cumulative_ms = 0

    for seq_entry in guide["sequence"]:
        for seg in seq_entry["segments"]:
            sub_start = seg["subtitle_start"]
            sub_end = seg["subtitle_end"]

            # Get the time range for this segment from the original SRT
            try:
                time_range = get_time_range(subtitles, sub_start, sub_end)
            except ValueError as e:
                print(f"  WARNING (SRT): {e}", file=sys.stderr)
                continue

            segment_origin_ms = time_range["start_ms"]

            # Extract and re-time subtitles in this range
            for idx in range(sub_start, sub_end + 1):
                sub = sub_map.get(idx)
                if not sub:
                    continue

                new_start_ms = cumulative_ms + (sub["start_ms"] - segment_origin_ms)
                new_end_ms = cumulative_ms + (sub["end_ms"] - segment_origin_ms)

                reordered.append({
                    "index": len(reordered) + 1,
                    "start_tc": format_timecode(new_start_ms),
                    "end_tc": format_timecode(new_end_ms),
                    "text": sub["text"],
                })

            cumulative_ms += time_range["duration_ms"]

    # Write SRT file
    lines: list[str] = []
    for entry in reordered:
        lines.append(str(entry["index"]))
        lines.append(f"{entry['start_tc']} --> {entry['end_tc']}")
        lines.append(entry["text"])
        lines.append("")

    output_path.write_text("\n".join(lines), encoding="utf-8")

    return {"total_subtitles": len(reordered), "total_duration_ms": cumulative_ms}


# ---------------------------------------------------------------------------
# FCPXML Reordering Pipeline
# ---------------------------------------------------------------------------

def build_reordered_spine(
    resolved_segments: list[dict],
    spine_clips: list[dict],
    frame_dur: Fraction,
) -> tuple[ET.Element, Fraction, int]:
    """Build a new spine with reordered clips.

    Returns (new_spine_element, total_duration, skipped_count).
    """
    new_spine = ET.Element("spine")
    current_offset = Fraction(0)
    total_duration = Fraction(0)
    skipped = 0

    for seg in resolved_segments:
        clip = find_clip_for_time(spine_clips, seg["timeline_start"])
        if not clip:
            print(f"  WARNING: No clip found for timeline {float(seg['timeline_start']):.1f}s "
                  f"({seg['label']}), skipping", file=sys.stderr)
            skipped += 1
            continue

        # Check if segment spans multiple clips — handle N-clip spanning
        seg_start = seg["timeline_start"]
        seg_end = seg["timeline_end"]
        part_num = 0

        while seg_start < seg_end:
            clip = find_clip_for_time(spine_clips, seg_start)
            if not clip:
                print(f"  WARNING: No clip for {float(seg_start):.1f}s in {seg['label']}, skipping remainder",
                      file=sys.stderr)
                skipped += 1
                break

            # This part ends at the earlier of: segment end or clip end
            part_end = min(seg_end, clip["timeline_end"])
            part_duration = snap_to_frame(part_end - seg_start, frame_dur)

            new_elem = create_sub_clip(clip, seg_start, part_end, current_offset, frame_dur)

            # Set clip name
            if part_end < seg_end:
                part_num += 1
                new_elem.set("name", f"{seg['label']} ({part_num})")
            elif part_num > 0:
                part_num += 1
                new_elem.set("name", f"{seg['label']} ({part_num})")
            else:
                new_elem.set("name", seg["label"])

            new_spine.append(new_elem)
            current_offset += part_duration
            total_duration += part_duration

            seg_start = part_end

    return new_spine, total_duration, skipped


def generate_reordered_fcpxml(
    fcpxml_path: Path,
    srt_path: Path,
    guide_path: Path,
    output_fcpxml: Path,
    output_srt: Path | None = None,
) -> dict:
    """Execute the full FCPXML reordering pipeline.

    Returns summary dict with segment count, duration, skipped count.
    """
    # 1. Parse inputs
    print("Parsing SRT...")
    subtitles = parse_srt(str(srt_path))
    print(f"  {len(subtitles)} subtitle entries")

    print("Parsing edit guide...")
    guide = parse_guide(str(guide_path))
    print(f"  Title: {guide['title']}")
    print(f"  Sequence: {len(guide['sequence'])} entries")

    # 2. Validate guide against SRT
    print("Validating guide...")
    errors = validate_guide(guide, subtitles)
    if errors:
        for err in errors:
            print(f"  ERROR: {err}", file=sys.stderr)
        print(f"\n{len(errors)} validation error(s). Fix the guide and retry.", file=sys.stderr)
        sys.exit(1)
    print("  Guide validation passed")

    # 3. Parse FCPXML
    print("Parsing FCPXML...")
    tree = ET.parse(str(fcpxml_path))
    root = tree.getroot()

    fcpxml_errors = validate_fcpxml(root)
    if fcpxml_errors:
        for err in fcpxml_errors:
            print(f"  ERROR: {err}", file=sys.stderr)
        sys.exit(1)
    print(f"  FCPXML version: {root.get('version', '?')}")

    # 4. Analyze spine
    spine = root.find(".//spine")
    spine_clips = analyze_spine(spine)
    print(f"  {len(spine_clips)} spine clips")
    for i, sc in enumerate(spine_clips):
        dur_s = float(sc["duration"])
        print(f"    Clip {i+1}: offset={float(sc['offset']):.1f}s, duration={dur_s:.1f}s ({dur_s/60:.1f}min)")

    # 5. Get frame duration
    fmt = root.find(".//format")
    frame_dur = parse_rational(fmt.get("frameDuration", "1001/24000s"))
    print(f"  Frame duration: {frame_dur} ({float(1/frame_dur):.3f} fps)")

    # 6. Resolve segments
    print("\nResolving segments...")
    resolved = resolve_segments(guide, subtitles)
    print(f"  {len(resolved)} segments resolved")
    for seg in resolved:
        dur = float(seg["duration"])
        print(f"    {seg['label']} [{seg['section']}] #{seg['sub_range']}: "
              f"{float(seg['timeline_start']):.1f}s - {float(seg['timeline_end']):.1f}s ({dur:.1f}s)")

    # 7. Build new spine
    print(f"\nBuilding new timeline...")
    new_spine, total_duration, skipped = build_reordered_spine(resolved, spine_clips, frame_dur)

    # 8. Replace spine in tree
    sequence = root.find(".//sequence")
    sequence.remove(spine)
    sequence.append(new_spine)
    sequence.set("duration", rational_to_str(snap_to_frame(total_duration, frame_dur)))

    # 9. Write FCPXML
    ET.indent(tree, space="    ")
    tree.write(str(output_fcpxml), encoding="UTF-8", xml_declaration=True)

    # Add DOCTYPE (ElementTree doesn't preserve it)
    content = output_fcpxml.read_text(encoding="utf-8")
    content = content.replace(
        "<?xml version='1.0' encoding='UTF-8'?>",
        '<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE fcpxml>',
    )
    output_fcpxml.write_text(content, encoding="utf-8")

    total_s = float(total_duration)
    print(f"\nFCPXML output: {output_fcpxml}")
    print(f"  Segments: {len(new_spine)}")
    print(f"  Duration: {total_s:.1f}s ({total_s/60:.1f} min)")
    if skipped:
        print(f"  Skipped: {skipped}")

    # 10. Generate reordered SRT if requested
    srt_summary = None
    if output_srt:
        print(f"\nGenerating reordered SRT...")
        srt_summary = generate_reordered_srt(guide, subtitles, output_srt)
        print(f"  SRT output: {output_srt}")
        print(f"  Subtitles: {srt_summary['total_subtitles']}")
        dur_ms = srt_summary["total_duration_ms"]
        print(f"  Duration: {dur_ms/1000:.1f}s ({dur_ms/60000:.1f} min)")

    return {
        "segments": len(new_spine),
        "duration_s": total_s,
        "skipped": skipped,
        "srt": srt_summary,
    }


# ---------------------------------------------------------------------------
# CLI: validate
# ---------------------------------------------------------------------------

def cmd_validate(args: argparse.Namespace) -> None:
    """Validate guide + SRT + FCPXML without generating output."""
    fcpxml_path = _validate_path(args.fcpxml, [".fcpxml"])
    srt_path = _validate_path(args.srt, [".srt"])
    guide_path = _validate_path(args.guide, [".yaml", ".yml"])

    subtitles = parse_srt(str(srt_path))
    print(f"SRT: {len(subtitles)} entries")

    guide = parse_guide(str(guide_path))
    print(f"Guide: {guide['title']} ({len(guide['sequence'])} sequence entries)")

    guide_errors = validate_guide(guide, subtitles)
    if guide_errors:
        print(f"\nGuide validation errors ({len(guide_errors)}):")
        for err in guide_errors:
            print(f"  - {err}")
    else:
        print("Guide validation: OK")

    tree = ET.parse(str(fcpxml_path))
    root = tree.getroot()
    fcpxml_errors = validate_fcpxml(root)
    if fcpxml_errors:
        print(f"\nFCPXML validation errors ({len(fcpxml_errors)}):")
        for err in fcpxml_errors:
            print(f"  - {err}")
    else:
        spine = root.find(".//spine")
        clips = analyze_spine(spine)
        print(f"FCPXML validation: OK (version {root.get('version', '?')}, {len(clips)} clips)")

    all_errors = guide_errors + fcpxml_errors
    if all_errors:
        sys.exit(1)
    print("\nAll validations passed.")


# ---------------------------------------------------------------------------
# CLI: preview
# ---------------------------------------------------------------------------

def cmd_preview(args: argparse.Namespace) -> None:
    """Show segment mapping without generating files."""
    fcpxml_path = _validate_path(args.fcpxml, [".fcpxml"])
    srt_path = _validate_path(args.srt, [".srt"])
    guide_path = _validate_path(args.guide, [".yaml", ".yml"])

    subtitles = parse_srt(str(srt_path))
    guide = parse_guide(str(guide_path))

    # Validate
    errors = validate_guide(guide, subtitles)
    if errors:
        for err in errors:
            print(f"ERROR: {err}", file=sys.stderr)
        sys.exit(1)

    tree = ET.parse(str(fcpxml_path))
    root = tree.getroot()
    fcpxml_errors = validate_fcpxml(root)
    if fcpxml_errors:
        for err in fcpxml_errors:
            print(f"ERROR: {err}", file=sys.stderr)
        sys.exit(1)

    spine = root.find(".//spine")
    spine_clips = analyze_spine(spine)
    fmt = root.find(".//format")
    frame_dur = parse_rational(fmt.get("frameDuration", "1001/24000s"))

    # Resolve segments
    resolved = resolve_segments(guide, subtitles)

    # Print preview
    print(f"Edit Guide: {guide['title']}")
    print(f"FCPXML: {fcpxml_path.name} (v{root.get('version', '?')}, {len(spine_clips)} clips)")
    print(f"Frame rate: {float(1/frame_dur):.3f} fps")
    print(f"\n{'#':>3}  {'Label':<20} {'Section':>7}  {'Subtitles':>12}  {'Source Range':>25}  {'Duration':>10}")
    print("-" * 85)

    total_dur = Fraction(0)
    for i, seg in enumerate(resolved, 1):
        dur_s = float(seg["duration"])
        src_start = float(seg["timeline_start"])
        src_end = float(seg["timeline_end"])

        # Check if it spans multiple clips
        clip = find_clip_for_time(spine_clips, seg["timeline_start"])
        end_clip = find_clip_for_time(spine_clips, seg["timeline_end"] - Fraction(1, 1000))
        span_marker = " *" if (end_clip and clip and end_clip is not clip) else ""

        print(f"{i:>3}  {seg['label']:<20} {seg['section']:>7}  #{seg['sub_range']:>11}  "
              f"{src_start:>10.1f}s - {src_end:>8.1f}s  {dur_s:>8.1f}s{span_marker}")
        total_dur += seg["duration"]

    total_s = float(total_dur)
    print("-" * 85)
    print(f"{'':>3}  {'TOTAL':<20} {'':>7}  {len(resolved):>9} seg  {'':>25}  {total_s:>8.1f}s ({total_s/60:.1f} min)")
    print(f"\n* = segment spans multiple spine clips (will be split)")


# ---------------------------------------------------------------------------
# CLI: reorder
# ---------------------------------------------------------------------------

def cmd_reorder(args: argparse.Namespace) -> None:
    """Execute the full reordering pipeline."""
    fcpxml_path = _validate_path(args.fcpxml, [".fcpxml"])
    srt_path = _validate_path(args.srt, [".srt"])
    guide_path = _validate_path(args.guide, [".yaml", ".yml"])
    output_fcpxml = _validate_output_path(args.output_fcpxml, ".fcpxml")
    output_srt = _validate_output_path(args.output_srt, ".srt") if args.output_srt else None

    result = generate_reordered_fcpxml(fcpxml_path, srt_path, guide_path, output_fcpxml, output_srt)

    if result["skipped"]:
        print(f"\nWARNING: {result['skipped']} segment(s) skipped due to errors.", file=sys.stderr)
        sys.exit(1)

    print("\nDone!")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="FCPXML round-trip reordering for DaVinci Resolve (Phase 3C)",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Common arguments
    def add_common_args(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("--fcpxml", required=True, help="Original FCPXML file")
        sp.add_argument("--srt", required=True, help="SRT subtitle file")
        sp.add_argument("--guide", required=True, help="YAML edit guide file")

    # validate
    sp_validate = subparsers.add_parser("validate", help="Validate inputs without generating output")
    add_common_args(sp_validate)
    sp_validate.set_defaults(func=cmd_validate)

    # preview
    sp_preview = subparsers.add_parser("preview", help="Show segment mapping without generating files")
    add_common_args(sp_preview)
    sp_preview.set_defaults(func=cmd_preview)

    # reorder
    sp_reorder = subparsers.add_parser("reorder", help="Generate reordered FCPXML and SRT")
    add_common_args(sp_reorder)
    sp_reorder.add_argument("--output-fcpxml", required=True, help="Output FCPXML file path")
    sp_reorder.add_argument("--output-srt", help="Output SRT file path (optional)")
    sp_reorder.set_defaults(func=cmd_reorder)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
