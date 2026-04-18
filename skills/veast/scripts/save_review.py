#!/usr/bin/env python3
"""Save review.md and propagate Phase 6 results to the wiki.

After Claude Code writes review.md, this script:
1. Loads the project (`project.md`)
2. Persists review.md to the project folder
3. Extracts learnings from review.md
4. Reads metrics from `analytics_{period}.json`
5. Attaches title, metrics, and learnings to the project dict
6. Marks Phase 6 done and saves
7. Calls `wiki_updater.update_for_phase(6, project, project_dir)` to update
   `wiki/videos/`, `wiki/learnings/`, `wiki/strategy/`, and `wiki/analytics/`.
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
    complete_phase,
    load_project,
    save_project,
    start_phase,
)
import wiki_updater  # noqa: E402

# ---------------------------------------------------------------------------
# Security
# ---------------------------------------------------------------------------

_SHELL_META = set('`$();|&><\n\0')


def _validate_path(path_str: str) -> Path:
    if any(c in path_str for c in _SHELL_META):
        print(
            f"Error: path contains shell metacharacters: {path_str}",
            file=sys.stderr,
        )
        sys.exit(1)
    return Path(path_str).expanduser().resolve()


# ---------------------------------------------------------------------------
# Extract learnings
# ---------------------------------------------------------------------------


def extract_learnings(review_md: str) -> list[str]:
    """Pull up to 6 numbered items sitting under ### headings."""
    learnings: list[str] = []
    in_section = False
    for line in review_md.split("\n"):
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
# Metrics loader
# ---------------------------------------------------------------------------


_DEFAULT_METRICS = {
    "views_72h": None, "views_1w": None, "views_4w": None,
    "ctr": None, "retention_rate": None, "avg_view_duration": None,
    "impressions": None, "likes": None, "comment_count": None,
    "subscribers_gained": None, "subscribers_lost": None,
    "traffic_sources": None, "retention_curve": None,
}


def _load_metrics_from_analytics(project_dir: Path) -> dict:
    for period in ("4w", "1w", "72h"):
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
        duration_str = (
            f"{dur // 60}:{dur % 60:02d}"
            if isinstance(dur, (int, float))
            else str(dur)
        )

        metrics = dict(_DEFAULT_METRICS)
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
            "traffic_sources": traffic or None,
            "retention_curve": retention or None,
        })
        return metrics
    return dict(_DEFAULT_METRICS)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def save_review_and_update_wiki(project_dir: Path, review_md: str) -> Path:
    project = load_project(project_dir)

    review_path = project_dir / "review.md"
    review_path.write_text(review_md, encoding="utf-8")

    learnings = extract_learnings(review_md)
    metrics = _load_metrics_from_analytics(project_dir)

    project["metrics"] = metrics
    project["learnings"] = learnings
    project.setdefault(
        "published_at", datetime.now(timezone.utc).isoformat()
    )

    project = start_phase(project, 6)
    project = complete_phase(project, 6, "review.md")
    save_project(project, project_dir)

    wiki_updater.update_for_phase(6, project, project_dir)

    return review_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Save review.md and propagate Phase 6 results to the wiki"
    )
    parser.add_argument(
        "--project-dir", required=True, help="Project directory path"
    )
    parser.add_argument(
        "--review-file",
        required=True,
        help="Path to review.md file (use '-' for stdin)",
    )
    args = parser.parse_args()

    project_dir = _validate_path(args.project_dir)
    if args.review_file == "-":
        review_md = sys.stdin.read()
    else:
        review_md = _validate_path(args.review_file).read_text(encoding="utf-8")

    result_path = save_review_and_update_wiki(project_dir, review_md)
    print(f"Review saved: {result_path}")
    print("Wiki updated: guests/, topics/, videos/, learnings/, strategy/, analytics/")


if __name__ == "__main__":
    main()
