#!/usr/bin/env python3
"""Save review.md and update _history.json after Claude Code analysis.

Replaces the original veast analyzer.py's save_review_and_update_history().
No pydantic dependency — uses plain dicts + json.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Import from sibling module
sys.path.insert(0, str(Path(__file__).resolve().parent))
from manage_project import (  # noqa: E402
    DEFAULT_PROJECTS_ROOT,
    HISTORY_FILENAME,
    add_video_to_history,
    complete_phase,
    load_history,
    load_project,
    recalculate_insights,
    save_history,
    save_project,
    start_phase,
)

# ---------------------------------------------------------------------------
# Security
# ---------------------------------------------------------------------------

_SHELL_META = set('`$();|&><\n\0')


def _validate_path(path_str: str) -> Path:
    if any(c in path_str for c in _SHELL_META):
        print(f"Error: path contains shell metacharacters: {path_str}", file=sys.stderr)
        sys.exit(1)
    return Path(path_str).resolve()


# ---------------------------------------------------------------------------
# Extract learnings
# ---------------------------------------------------------------------------


def extract_learnings(review_md: str) -> list[str]:
    """Extract key learnings from review.md for _history.json.

    Looks for numbered items (1. 2. 3.) under ### headings.
    Returns max 6 learnings.
    """
    learnings: list[str] = []
    lines = review_md.split("\n")
    in_section = False

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("###"):
            in_section = True
            continue
        if in_section and stripped.startswith(("1.", "2.", "3.")):
            learning = stripped.lstrip("0123456789. ").strip()
            if learning:
                learnings.append(learning)

    return learnings[:6]


# ---------------------------------------------------------------------------
# Load metrics from analytics file
# ---------------------------------------------------------------------------


def _load_metrics_from_analytics(project_dir: Path) -> dict:
    """Try to load metrics from analytics_{period}.json files."""
    default_metrics = {
        "views_72h": None, "views_1w": None, "views_4w": None,
        "ctr": None, "retention_rate": None, "avg_view_duration": None,
        "impressions": None, "likes": None, "comment_count": None,
        "subscribers_gained": None, "subscribers_lost": None,
        "traffic_sources": None, "retention_curve": None,
    }

    for period in ["4w", "1w", "72h"]:
        analytics_file = project_dir / f"analytics_{period}.json"
        if not analytics_file.exists():
            continue

        try:
            raw = json.loads(analytics_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue

        analytics = raw.get("analytics", {})
        details = raw.get("video_details", {})
        retention = raw.get("retention_curve", {})
        traffic = raw.get("traffic_sources", {})

        avg_retention = None
        if retention:
            values = list(retention.values())
            avg_retention = round(sum(values) / len(values), 1)

        dur = analytics.get("avg_view_duration", 0)
        duration_str = f"{dur // 60}:{dur % 60:02d}" if isinstance(dur, (int, float)) else str(dur)

        metrics = dict(default_metrics)  # copy defaults
        metrics.update({
            f"views_{period}": analytics.get("views"),
            "ctr": analytics.get("ctr"),
            "retention_rate": avg_retention,
            "avg_view_duration": duration_str,
            "impressions": analytics.get("impressions"),
            "likes": details.get("likes"),
            "comment_count": details.get("comment_count"),
            "subscribers_gained": analytics.get("subscribers_gained"),
            "subscribers_lost": analytics.get("subscribers_lost"),
            "traffic_sources": traffic if traffic else None,
            "retention_curve": retention if retention else None,
        })
        return metrics

    return default_metrics


# ---------------------------------------------------------------------------
# Main function
# ---------------------------------------------------------------------------


def save_review_and_update_history(
    project_dir: Path,
    review_md: str,
    history_path: Path | None = None,
) -> Path:
    """Save review.md and update _history.json.

    1. Load project
    2. Save review.md
    3. Extract learnings
    4. Load metrics from analytics file
    5. Create video record
    6. Update history + recalculate insights
    7. Mark phase 6 as done

    Returns path to saved review.md.
    """
    project = load_project(project_dir)

    # Save review.md
    review_path = project_dir / "review.md"
    review_path.write_text(review_md, encoding="utf-8")

    # Extract learnings
    learnings = extract_learnings(review_md)

    # Load metrics
    metrics = _load_metrics_from_analytics(project_dir)

    # Determine title
    guest = project.get("meta", {}).get("guest")
    title = guest["name"] if guest and isinstance(guest, dict) else project["id"]

    # Create video record
    video_record = {
        "project_id": project["id"],
        "title": title,
        "type": project["type"],
        "published_at": datetime.now(timezone.utc).isoformat(),
        "metrics": metrics,
        "learnings": learnings,
    }

    # Update history
    h_path = history_path or (DEFAULT_PROJECTS_ROOT / HISTORY_FILENAME)
    history = load_history(h_path)
    history = add_video_to_history(history, video_record)
    history = recalculate_insights(history)
    save_history(history, h_path)

    # Mark phase 6 as done
    project = start_phase(project, 6)
    project = complete_phase(project, 6, "review.md")
    save_project(project, project_dir)

    return review_path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Save review.md and update _history.json"
    )
    parser.add_argument("--project-dir", required=True, help="Project directory path")
    parser.add_argument(
        "--review-file", required=True,
        help="Path to review.md file (use '-' for stdin)"
    )
    parser.add_argument("--history-path", help="Path to _history.json (optional)")

    args = parser.parse_args()

    project_dir = _validate_path(args.project_dir)

    # Read review content
    if args.review_file == "-":
        review_md = sys.stdin.read()
    else:
        review_path = _validate_path(args.review_file)
        review_md = review_path.read_text(encoding="utf-8")

    history_path = _validate_path(args.history_path) if args.history_path else None

    result_path = save_review_and_update_history(project_dir, review_md, history_path)
    print(f"Review saved: {result_path}")
    print(f"History updated: {history_path or DEFAULT_PROJECTS_ROOT / HISTORY_FILENAME}")


if __name__ == "__main__":
    main()
