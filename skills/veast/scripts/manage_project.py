#!/usr/bin/env python3
"""Project management — vault-based with frontmatter project.md.

Projects live inside the Obsidian vault at `$VEAST_VAULT_PATH` (default
`~/Movies/Youtube/`). Each project is a folder named `YYMMDD 제목` containing
a `project.md` with YAML frontmatter (schema: see references/wiki-frontmatter.md).

Channel-level aggregation (previously `_history.json`) now lives in
`wiki/analytics/채널-대시보드.md` and is maintained by `wiki_updater`.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path

try:
    import frontmatter  # type: ignore
except ImportError:
    print(
        "Error: python-frontmatter is required. "
        "Install with: pip install -r skills/veast/requirements.txt",
        file=sys.stderr,
    )
    sys.exit(1)

import wiki_updater

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PROJECT_FILENAME = "project.md"

VALID_TYPES = ["인터뷰", "브이로그", "팟캐스트", "탐방로그", "숏폼"]

# Phase → 결과 파일 매핑 (Phase 3은 수동 편집이므로 제외)
PHASE_RESULT_FILES = {
    1: "concept.md",
    2: "edit-guide.yaml",
    4: "packaging.md",
    5: "upload-kit.md",
    6: "review.md",
}


def get_vault_root() -> Path:
    return Path(
        os.environ.get(
            "VEAST_VAULT_PATH", str(Path.home() / "Movies" / "Youtube")
        )
    ).expanduser()


# ---------------------------------------------------------------------------
# Security
# ---------------------------------------------------------------------------

_SHELL_META = set('`$();|&><\n\0')


def _validate_path(path_str: str) -> Path:
    """Resolve to absolute path and reject shell metacharacters."""
    if any(c in path_str for c in _SHELL_META):
        print(
            f"Error: path contains shell metacharacters: {path_str}",
            file=sys.stderr,
        )
        sys.exit(1)
    return Path(path_str).expanduser().resolve()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sanitize_title(title: str) -> str:
    """Collapse whitespace and strip path-unsafe characters (keep Korean)."""
    cleaned = re.sub(r"\s+", " ", title.strip())
    cleaned = re.sub(r"[\\/:*?\"<>|]", "", cleaned)
    return cleaned


def generate_folder_name(title: str, d: date | None = None) -> str:
    """Generate a folder name like '260101 홍길동인터뷰'."""
    d = d or date.today()
    stamp = d.strftime("%y%m%d")
    return f"{stamp} {_sanitize_title(title)}"


# ---------------------------------------------------------------------------
# Directory helpers
# ---------------------------------------------------------------------------


def get_project_dir(folder: str, root: Path | None = None) -> Path:
    return (root or get_vault_root()) / folder


def ensure_project_dir(folder: str, root: Path | None = None) -> Path:
    d = get_project_dir(folder, root)
    d.mkdir(parents=True, exist_ok=True)
    return d


# ---------------------------------------------------------------------------
# Default project skeleton
# ---------------------------------------------------------------------------


def _default_phase_results() -> dict:
    return {
        i: {
            "status": "pending",
            "result_file": None,
            "started_at": None,
            "completed_at": None,
        }
        for i in range(1, 7)
    }


# ---------------------------------------------------------------------------
# Project CRUD — project.md frontmatter
# ---------------------------------------------------------------------------


def create_project(
    project_type: str,
    title: str,
    meta: dict | None = None,
    insights: list | None = None,
    d: date | None = None,
    root: Path | None = None,
) -> dict:
    if project_type not in VALID_TYPES:
        raise ValueError(
            f"Invalid type '{project_type}'. Must be one of: {VALID_TYPES}"
        )

    folder = generate_folder_name(title, d)
    now = _now()
    project: dict = {
        "type": "project",
        "id": folder,
        "folder": folder,
        "video_type": project_type,
        "title": title,
        "current_phase": 1,
        "phase_results": _default_phase_results(),
        "insights_from_previous": insights or [],
        "status": "draft",
        "created_at": now,
        "updated_at": now,
    }
    if meta:
        project.update(meta)

    project_dir = ensure_project_dir(folder, root)
    save_project(project, project_dir)
    return project


def load_project(project_dir: Path) -> dict:
    path = project_dir / PROJECT_FILENAME
    if not path.exists():
        raise FileNotFoundError(f"project.md not found in {project_dir}")
    post = frontmatter.load(path)
    data = dict(post.metadata)
    data.setdefault("folder", project_dir.name)
    data.setdefault("id", project_dir.name)
    data.setdefault("_body", post.content)
    return data


def save_project(project: dict, project_dir: Path) -> Path:
    project["updated_at"] = _now()
    body = project.pop("_body", "")
    path = project_dir / PROJECT_FILENAME
    post = frontmatter.Post(content=body, **project)
    path.write_text(frontmatter.dumps(post), encoding="utf-8")
    project["_body"] = body
    return path


# ---------------------------------------------------------------------------
# Phase management
# ---------------------------------------------------------------------------


def _phase_key(project: dict, phase: int):
    """phase_results may be keyed by int or str depending on YAML load."""
    results = project.setdefault("phase_results", _default_phase_results())
    if phase in results:
        return phase
    str_key = str(phase)
    if str_key in results:
        return str_key
    results[phase] = {
        "status": "pending",
        "result_file": None,
        "started_at": None,
        "completed_at": None,
    }
    return phase


def start_phase(project: dict, phase: int) -> dict:
    key = _phase_key(project, phase)
    project["phase_results"][key]["status"] = "in-progress"
    project["phase_results"][key]["started_at"] = _now()
    project["current_phase"] = phase
    project["updated_at"] = _now()
    return project


def complete_phase(
    project: dict, phase: int, result_file: str | None = None
) -> dict:
    key = _phase_key(project, phase)
    project["phase_results"][key]["status"] = "done"
    project["phase_results"][key]["completed_at"] = _now()
    if result_file:
        project["phase_results"][key]["result_file"] = result_file
    project["updated_at"] = _now()
    return project


def sync_phases(project: dict, project_dir: Path) -> tuple[dict, list[int]]:
    """결과 파일 존재 여부로 phase_results를 동기화. 변경된 Phase 목록 반환."""
    synced: list[int] = []
    for phase, filename in PHASE_RESULT_FILES.items():
        key = _phase_key(project, phase)
        result = project["phase_results"][key]
        file_path = project_dir / filename
        if file_path.exists() and result["status"] != "done":
            result["status"] = "done"
            result["result_file"] = filename
            result["completed_at"] = _now()
            synced.append(phase)
    if synced:
        done_phases = [
            int(k if not isinstance(k, str) else k)
            for k, v in project["phase_results"].items()
            if v["status"] == "done"
        ]
        project["current_phase"] = max(done_phases)
        project["updated_at"] = _now()
    return project, synced


# ---------------------------------------------------------------------------
# List projects
# ---------------------------------------------------------------------------


_FOLDER_PATTERN = re.compile(r"^\d{6} .+")


def list_projects(root: Path | None = None) -> list[Path]:
    root = root or get_vault_root()
    if not root.is_dir():
        return []
    return sorted(
        d
        for d in root.iterdir()
        if d.is_dir()
        and _FOLDER_PATTERN.match(d.name)
        and (d / PROJECT_FILENAME).exists()
    )


# ---------------------------------------------------------------------------
# CLI commands
# ---------------------------------------------------------------------------


def _cmd_new(args: argparse.Namespace) -> None:
    root = Path(args.root).expanduser().resolve() if args.root else None
    project = create_project(args.type, args.title, root=root)
    print(project["folder"])


def _cmd_status(args: argparse.Namespace) -> None:
    project_dir = _validate_path(args.dir)
    project = load_project(project_dir)
    print(f"Project: {project.get('folder', project_dir.name)}")
    print(f"Type:    {project.get('video_type', '?')}")
    print(f"Phase:   {project.get('current_phase', '?')}")
    print()
    results = project.get("phase_results", {})
    for phase_num in range(1, 7):
        pr = results.get(phase_num) or results.get(str(phase_num)) or {}
        status = pr.get("status", "pending")
        result = pr.get("result_file") or ""
        marker = (
            "✅" if status == "done" else ("🔄" if status == "in-progress" else "⬜")
        )
        print(f"  {marker} Phase {phase_num}: {status} {result}")


def _cmd_list(args: argparse.Namespace) -> None:
    root = Path(args.root).expanduser().resolve() if args.root else None
    projects = list_projects(root)
    if not projects:
        print("No projects found.")
        return
    for p in projects:
        try:
            proj = load_project(p)
            phase = proj.get("current_phase", "?")
            key = proj["phase_results"].get(phase) or proj["phase_results"].get(
                str(phase), {}
            )
            status = key.get("status", "?")
            print(f"  {proj['folder']}  (Phase {phase}: {status})")
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
    wiki_updater.update_for_phase(args.phase, project, project_dir)
    print(f"Phase {args.phase} completed.")


def _cmd_sync(args: argparse.Namespace) -> None:
    project_dir = _validate_path(args.dir)
    project = load_project(project_dir)
    project, synced = sync_phases(project, project_dir)
    if synced:
        save_project(project, project_dir)
        for phase in synced:
            wiki_updater.update_for_phase(phase, project, project_dir)
        print(f"Synced phases: {', '.join(str(p) for p in synced)}")
    else:
        print("Already in sync.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Veast project management")
    sub = parser.add_subparsers(dest="command", required=True)

    p_new = sub.add_parser("new", help="Create a new project")
    p_new.add_argument(
        "--type", required=True, choices=VALID_TYPES, help="Project type"
    )
    p_new.add_argument("--title", required=True, help="Project title")
    p_new.add_argument("--root", help="Vault root override")
    p_new.set_defaults(func=_cmd_new)

    p_status = sub.add_parser("status", help="Show project status")
    p_status.add_argument("--dir", required=True, help="Project directory")
    p_status.set_defaults(func=_cmd_status)

    p_list = sub.add_parser("list", help="List all projects")
    p_list.add_argument("--root", help="Vault root override")
    p_list.set_defaults(func=_cmd_list)

    p_start = sub.add_parser("start-phase", help="Start a phase")
    p_start.add_argument("--dir", required=True, help="Project directory")
    p_start.add_argument(
        "--phase", required=True, type=int, choices=range(1, 7), help="Phase number"
    )
    p_start.set_defaults(func=_cmd_start_phase)

    p_complete = sub.add_parser("complete-phase", help="Complete a phase")
    p_complete.add_argument("--dir", required=True, help="Project directory")
    p_complete.add_argument(
        "--phase", required=True, type=int, choices=range(1, 7), help="Phase number"
    )
    p_complete.add_argument("--result-file", help="Result file name")
    p_complete.set_defaults(func=_cmd_complete_phase)

    p_sync = sub.add_parser("sync", help="Sync phase status from result files")
    p_sync.add_argument("--dir", required=True, help="Project directory")
    p_sync.set_defaults(func=_cmd_sync)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
