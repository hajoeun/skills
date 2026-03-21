#!/usr/bin/env python3
"""Project and channel history management — no pydantic dependency.

Replaces the original veast project.py. Uses plain dicts + json module.
Data is stored at ~/.veast/projects/ for backward compatibility.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_PROJECTS_ROOT = Path.home() / ".veast/projects"
HISTORY_FILENAME = "_history.json"
PROJECT_FILENAME = "project.json"

VALID_TYPES = ["인터뷰", "브이로그", "팟캐스트", "탐방로그", "숏폼"]

# ---------------------------------------------------------------------------
# Security
# ---------------------------------------------------------------------------

_SHELL_META = set('`$();|&><\n\0')


def _validate_path(path_str: str) -> Path:
    """Resolve to absolute path and reject shell metacharacters."""
    if any(c in path_str for c in _SHELL_META):
        print(f"Error: path contains shell metacharacters: {path_str}", file=sys.stderr)
        sys.exit(1)
    return Path(path_str).resolve()


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------


def _now() -> str:
    """Return current UTC time as ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


def _slugify(text: str) -> str:
    """Replace whitespace with hyphens and strip unsafe chars (keep Korean)."""
    text = re.sub(r"\s+", "-", text.strip())
    text = re.sub(r"[^\w가-힣-]", "", text)
    return text


def generate_project_id(
    project_type: str, title: str, d: date | None = None
) -> str:
    """Generate a project id like '2026-03-15-인터뷰-홍길동'."""
    d = d or date.today()
    return f"{d.isoformat()}-{project_type}-{_slugify(title)}"


# ---------------------------------------------------------------------------
# Directory helpers
# ---------------------------------------------------------------------------


def get_project_dir(project_id: str, root: Path = DEFAULT_PROJECTS_ROOT) -> Path:
    return root / project_id


def ensure_project_dir(project_id: str, root: Path = DEFAULT_PROJECTS_ROOT) -> Path:
    d = get_project_dir(project_id, root)
    d.mkdir(parents=True, exist_ok=True)
    return d


# ---------------------------------------------------------------------------
# Default structures
# ---------------------------------------------------------------------------


def _default_phase_results() -> dict:
    return {
        str(i): {
            "status": "pending",
            "result_file": None,
            "started_at": None,
            "completed_at": None,
        }
        for i in range(1, 7)
    }


def _default_meta() -> dict:
    return {
        "guest": None,
        "target_audience": "",
        "target_views": None,
        "expected_length": "",
        "filming_date": None,
        "youtube_video_id": None,
    }


def _default_history() -> dict:
    return {
        "channel": {"name": "Unknown", "updated_at": _now()},
        "insights": {
            "avg_ctr": None,
            "avg_retention_rate": None,
            "top_performing_topics": [],
            "title_patterns": {},
            "retention_patterns": {},
        },
        "videos": [],
    }


# ---------------------------------------------------------------------------
# Project CRUD
# ---------------------------------------------------------------------------


def create_project(
    project_type: str,
    title: str,
    meta: dict | None = None,
    insights: list[str] | None = None,
    d: date | None = None,
    root: Path = DEFAULT_PROJECTS_ROOT,
) -> dict:
    """Create a new project, its directory, and persist project.json."""
    if project_type not in VALID_TYPES:
        raise ValueError(f"Invalid type '{project_type}'. Must be one of: {VALID_TYPES}")

    now = _now()
    project_id = generate_project_id(project_type, title, d)
    project = {
        "id": project_id,
        "current_phase": 1,
        "type": project_type,
        "meta": meta or _default_meta(),
        "phase_results": _default_phase_results(),
        "insights_from_previous": insights or [],
        "created_at": now,
        "updated_at": now,
    }
    project_dir = ensure_project_dir(project_id, root)
    save_project(project, project_dir)
    return project


def load_project(project_dir: Path) -> dict:
    """Load project.json from project_dir."""
    path = project_dir / PROJECT_FILENAME
    if not path.exists():
        raise FileNotFoundError(f"project.json not found in {project_dir}")
    return json.loads(path.read_text(encoding="utf-8"))


def save_project(project: dict, project_dir: Path) -> Path:
    """Write project.json into project_dir."""
    project["updated_at"] = _now()
    path = project_dir / PROJECT_FILENAME
    path.write_text(
        json.dumps(project, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return path


# ---------------------------------------------------------------------------
# Phase management
# ---------------------------------------------------------------------------


def start_phase(project: dict, phase: int) -> dict:
    """Mark phase as in-progress and update current_phase."""
    key = str(phase)
    project["phase_results"][key]["status"] = "in-progress"
    project["phase_results"][key]["started_at"] = _now()
    project["current_phase"] = phase
    project["updated_at"] = _now()
    return project


def complete_phase(project: dict, phase: int, result_file: str | None = None) -> dict:
    """Mark phase as done."""
    key = str(phase)
    project["phase_results"][key]["status"] = "done"
    project["phase_results"][key]["completed_at"] = _now()
    if result_file:
        project["phase_results"][key]["result_file"] = result_file
    project["updated_at"] = _now()
    return project


# ---------------------------------------------------------------------------
# History CRUD
# ---------------------------------------------------------------------------


def load_history(path: Path | None = None) -> dict:
    """Load _history.json. Returns default if not found."""
    path = path or (DEFAULT_PROJECTS_ROOT / HISTORY_FILENAME)
    if not path.exists():
        return _default_history()
    return json.loads(path.read_text(encoding="utf-8"))


def save_history(history: dict, path: Path | None = None) -> Path:
    """Write _history.json."""
    path = path or (DEFAULT_PROJECTS_ROOT / HISTORY_FILENAME)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(history, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return path


def add_video_to_history(history: dict, record: dict) -> dict:
    """Append a video record to the history."""
    history["videos"].append(record)
    history["channel"]["updated_at"] = _now()
    return history


def recalculate_insights(history: dict) -> dict:
    """Recompute channel-level insights from all video records."""
    videos = history.get("videos", [])
    if not videos:
        return history

    ctrs = [
        v["metrics"]["ctr"]
        for v in videos
        if v.get("metrics", {}).get("ctr") is not None
    ]
    retentions = [
        v["metrics"]["retention_rate"]
        for v in videos
        if v.get("metrics", {}).get("retention_rate") is not None
    ]

    insights = history.setdefault("insights", {})
    insights["avg_ctr"] = round(sum(ctrs) / len(ctrs), 1) if ctrs else None
    insights["avg_retention_rate"] = (
        round(sum(retentions) / len(retentions), 1) if retentions else None
    )

    return history


# ---------------------------------------------------------------------------
# List projects
# ---------------------------------------------------------------------------


def list_projects(root: Path = DEFAULT_PROJECTS_ROOT) -> list[Path]:
    """Return paths of directories containing project.json."""
    if not root.exists():
        return []
    return sorted(
        d for d in root.iterdir() if d.is_dir() and (d / PROJECT_FILENAME).exists()
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _cmd_new(args: argparse.Namespace) -> None:
    root = Path(args.root).resolve() if args.root else DEFAULT_PROJECTS_ROOT
    project = create_project(args.type, args.title, root=root)
    print(project["id"])


def _cmd_status(args: argparse.Namespace) -> None:
    project_dir = _validate_path(args.dir)
    project = load_project(project_dir)
    print(f"Project: {project['id']}")
    print(f"Type:    {project['type']}")
    print(f"Phase:   {project['current_phase']}")
    print()
    for phase_num in range(1, 7):
        pr = project["phase_results"][str(phase_num)]
        status = pr["status"]
        result = pr.get("result_file") or ""
        marker = "✅" if status == "done" else ("🔄" if status == "in-progress" else "⬜")
        print(f"  {marker} Phase {phase_num}: {status} {result}")


def _cmd_list(args: argparse.Namespace) -> None:
    root = Path(args.root).resolve() if args.root else DEFAULT_PROJECTS_ROOT
    projects = list_projects(root)
    if not projects:
        print("No projects found.")
        return
    for p in projects:
        try:
            proj = load_project(p)
            status = proj["phase_results"][str(proj["current_phase"])]["status"]
            print(f"  {proj['id']}  (Phase {proj['current_phase']}: {status})")
        except Exception:
            print(f"  {p.name}  (error loading)")


def _cmd_start_phase(args: argparse.Namespace) -> None:
    project_dir = _validate_path(args.dir)
    project = load_project(project_dir)
    project = start_phase(project, args.phase)
    save_project(project, project_dir)
    print(f"Phase {args.phase} started.")


def _cmd_complete_phase(args: argparse.Namespace) -> None:
    project_dir = _validate_path(args.dir)
    project = load_project(project_dir)
    project = complete_phase(project, args.phase, args.result_file)
    save_project(project, project_dir)
    print(f"Phase {args.phase} completed.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Veast project management")
    sub = parser.add_subparsers(dest="command", required=True)

    # new
    p_new = sub.add_parser("new", help="Create a new project")
    p_new.add_argument("--type", required=True, choices=VALID_TYPES, help="Project type")
    p_new.add_argument("--title", required=True, help="Project title")
    p_new.add_argument("--root", help="Projects root directory")
    p_new.set_defaults(func=_cmd_new)

    # status
    p_status = sub.add_parser("status", help="Show project status")
    p_status.add_argument("--dir", required=True, help="Project directory")
    p_status.set_defaults(func=_cmd_status)

    # list
    p_list = sub.add_parser("list", help="List all projects")
    p_list.add_argument("--root", help="Projects root directory")
    p_list.set_defaults(func=_cmd_list)

    # start-phase
    p_start = sub.add_parser("start-phase", help="Start a phase")
    p_start.add_argument("--dir", required=True, help="Project directory")
    p_start.add_argument("--phase", required=True, type=int, choices=range(1, 7), help="Phase number")
    p_start.set_defaults(func=_cmd_start_phase)

    # complete-phase
    p_complete = sub.add_parser("complete-phase", help="Complete a phase")
    p_complete.add_argument("--dir", required=True, help="Project directory")
    p_complete.add_argument("--phase", required=True, type=int, choices=range(1, 7), help="Phase number")
    p_complete.add_argument("--result-file", help="Result file name")
    p_complete.set_defaults(func=_cmd_complete_phase)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
