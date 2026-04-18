#!/usr/bin/env python3
"""Wiki page updater — keeps the Obsidian vault in sync with project progress.

Called by manage_project.py and save_review.py when a phase completes.
Safe to import and call even when the vault is absent or python-frontmatter
is not installed — in those cases, calls are no-ops.
"""

from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

try:
    import frontmatter  # type: ignore
except ImportError:
    frontmatter = None  # type: ignore

try:
    import yaml  # type: ignore
except ImportError:
    yaml = None  # type: ignore


# ---------------------------------------------------------------------------
# Vault resolution
# ---------------------------------------------------------------------------


def get_vault_root() -> Path:
    return Path(
        os.environ.get(
            "VEAST_VAULT_PATH", str(Path.home() / "Movies" / "Youtube")
        )
    ).expanduser()


def _wiki_enabled() -> bool:
    """Returns True when frontmatter is importable and the vault exists."""
    return frontmatter is not None and get_vault_root().is_dir()


# ---------------------------------------------------------------------------
# Frontmatter I/O
# ---------------------------------------------------------------------------


def load_page(path: Path):
    if path.exists():
        return frontmatter.load(path)
    return frontmatter.Post(content="")


def save_page(path: Path, post) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(frontmatter.dumps(post), encoding="utf-8")


def _merge_link(links: list, new_link: str) -> list:
    if new_link not in links:
        links.append(new_link)
    return links


def _strip_wikilink(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    m = re.match(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]", value.strip())
    return m.group(1) if m else value.strip()


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Phase dispatcher
# ---------------------------------------------------------------------------


def update_for_phase(phase: int, project: dict, project_dir: Path) -> None:
    """Run the wiki updates attached to a phase completion.

    No-op if the vault is not available. Never raises — failures are swallowed
    to avoid breaking the pipeline script that called us.
    """
    if not _wiki_enabled():
        return
    try:
        vault = get_vault_root()
        wiki = vault / "wiki"

        if phase == 1:
            update_guest_page(project, wiki)
        if phase == 2:
            update_topic_pages(project, project_dir, wiki)
        if phase in (4, 5, 6):
            update_video_page(project, phase, wiki)
        if phase == 6:
            update_strategy(project, project_dir, wiki)
            update_learnings(project, project_dir, wiki)
            update_dashboard(project, wiki)

        append_log(vault, project, phase)

        if phase in (1, 4, 6):
            refresh_index(vault)
    except Exception as exc:  # noqa: BLE001
        # Never break the caller
        print(f"[wiki_updater] warning: {exc}")


# ---------------------------------------------------------------------------
# Guest page (Phase 1)
# ---------------------------------------------------------------------------


def update_guest_page(project: dict, wiki_dir: Path) -> None:
    guest_name = _resolve_guest_name(project)
    if not guest_name:
        return

    page = wiki_dir / "guests" / f"{guest_name}.md"
    post = load_page(page)
    meta = dict(post.metadata)
    meta.setdefault("type", "guest")
    meta.setdefault("name", guest_name)
    meta.setdefault("first_appearance", project.get("filming_date") or _today())
    videos = list(meta.get("videos") or [])
    _merge_link(videos, f"[[{project['folder']}]]")
    meta["videos"] = videos
    post.metadata = meta
    save_page(page, post)


def _resolve_guest_name(project: dict) -> str:
    guest = project.get("guest")
    if isinstance(guest, str):
        return _strip_wikilink(guest)
    if isinstance(guest, dict):
        return str(guest.get("name") or "").strip()
    return ""


# ---------------------------------------------------------------------------
# Topic pages (Phase 2)
# ---------------------------------------------------------------------------


def update_topic_pages(project: dict, project_dir: Path, wiki_dir: Path) -> None:
    if yaml is None:
        return
    guide_path = project_dir / "edit-guide.yaml"
    if not guide_path.exists():
        return
    try:
        guide = yaml.safe_load(guide_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        return
    sections = guide.get("sections") or []
    topics = {
        s["title"].strip()
        for s in sections
        if isinstance(s, dict) and isinstance(s.get("title"), str)
    }
    for topic in topics:
        _upsert_topic_page(topic, project, wiki_dir)


def _upsert_topic_page(topic: str, project: dict, wiki_dir: Path) -> None:
    page = wiki_dir / "topics" / f"{topic}.md"
    post = load_page(page)
    meta = dict(post.metadata)
    meta.setdefault("type", "topic")
    meta.setdefault("name", topic)
    videos = list(meta.get("videos") or [])
    _merge_link(videos, f"[[{project['folder']}]]")
    meta["videos"] = videos
    meta["video_count"] = len(videos)
    post.metadata = meta
    save_page(page, post)


# ---------------------------------------------------------------------------
# Video page (Phase 4/5/6)
# ---------------------------------------------------------------------------


def update_video_page(project: dict, phase: int, wiki_dir: Path) -> None:
    folder = project["folder"]
    page = wiki_dir / "videos" / f"{folder}.md"
    post = load_page(page)
    meta = dict(post.metadata)

    meta["type"] = "video"
    meta["id"] = folder
    meta.setdefault("project", f"[[{folder}/project]]")
    if project.get("video_type"):
        meta["video_type"] = project["video_type"]
    if project.get("guest"):
        meta["guest"] = project["guest"]

    if phase == 4 and project.get("title"):
        meta["title"] = project["title"]
    if phase == 5:
        meta["status"] = "published"
        if project.get("youtube_video_id"):
            meta["youtube_video_id"] = project["youtube_video_id"]
        if project.get("published_at"):
            meta["published"] = project["published_at"]
    if phase == 6 and project.get("metrics"):
        meta["metrics"] = project["metrics"]

    post.metadata = meta
    save_page(page, post)


# ---------------------------------------------------------------------------
# Strategy (Phase 6)
# ---------------------------------------------------------------------------


def update_strategy(project: dict, project_dir: Path, wiki_dir: Path) -> None:
    """Append a dated observation to wiki/strategy/채널-전략.md.

    Initial implementation is intentionally minimal — we log a pointer back to
    the review and let the user promote patterns manually. Future iterations
    can parse review.md for structured insights.
    """
    review_path = project_dir / "review.md"
    if not review_path.exists():
        return
    page = wiki_dir / "strategy" / "채널-전략.md"
    post = load_page(page)
    meta = dict(post.metadata)
    meta.setdefault("type", "strategy")
    meta.setdefault("name", "채널 전략")
    observations = list(meta.get("observations") or [])
    entry = f"[[{project['folder']}]] — review recorded {_today()}"
    _merge_link(observations, entry)
    meta["observations"] = observations
    post.metadata = meta
    save_page(page, post)


# ---------------------------------------------------------------------------
# Learnings (Phase 6)
# ---------------------------------------------------------------------------


def update_learnings(project: dict, project_dir: Path, wiki_dir: Path) -> None:
    learnings = _extract_learnings(project)
    if not learnings:
        return
    for item in learnings:
        name, category = _parse_learning(item)
        if not name:
            continue
        _upsert_learning(name, category, project, wiki_dir)


def _extract_learnings(project: dict) -> list:
    return list(project.get("learnings") or [])


def _parse_learning(item: Any) -> tuple[str, str]:
    if isinstance(item, dict):
        return str(item.get("name") or "").strip(), str(item.get("category") or "편집")
    return _strip_wikilink(str(item)), "편집"


def _upsert_learning(
    name: str, category: str, project: dict, wiki_dir: Path
) -> None:
    page = wiki_dir / "learnings" / f"{name}.md"
    post = load_page(page)
    meta = dict(post.metadata)
    meta.setdefault("type", "learning")
    meta.setdefault("name", name)
    meta.setdefault("category", category)
    meta.setdefault("first_observed", _today())
    meta["last_verified"] = _today()
    videos = list(meta.get("videos") or [])
    _merge_link(videos, f"[[{project['folder']}]]")
    meta["videos"] = videos
    meta["verified_count"] = len(videos)
    meta["confidence"] = _confidence(len(videos))
    post.metadata = meta
    save_page(page, post)


def _confidence(count: int) -> str:
    if count >= 3:
        return "high"
    if count >= 2:
        return "medium"
    return "low"


# ---------------------------------------------------------------------------
# Dashboard (Phase 6)
# ---------------------------------------------------------------------------


def update_dashboard(project: dict, wiki_dir: Path) -> None:
    page = wiki_dir / "analytics" / "채널-대시보드.md"
    post = load_page(page)
    meta = dict(post.metadata)
    meta.setdefault("type", "dashboard")
    channel = dict(meta.get("channel") or {"name": "내 채널"})
    channel["updated_at"] = _utcnow()
    meta["channel"] = channel

    videos = list(meta.get("videos") or [])
    metrics = project.get("metrics") or {}
    entry = {
        "id": project["folder"],
        "link": f"[[{project['folder']}]]",
        "published": project.get("published_at") or project.get("filming_date"),
        "metrics": {
            k: metrics.get(k)
            for k in ("views_4w", "ctr", "retention_rate")
            if metrics.get(k) is not None
        },
    }
    videos = [v for v in videos if v.get("id") != project["folder"]]
    videos.append(entry)
    videos = videos[-50:]
    meta["videos"] = videos

    meta["insights"] = _recalculate_insights(videos)
    post.metadata = meta
    save_page(page, post)


def _recalculate_insights(videos: Iterable[dict]) -> dict:
    videos = list(videos)
    ctrs = [v["metrics"].get("ctr") for v in videos if isinstance(v.get("metrics"), dict)]
    ctrs = [c for c in ctrs if c is not None]
    retentions = [
        v["metrics"].get("retention_rate")
        for v in videos
        if isinstance(v.get("metrics"), dict)
    ]
    retentions = [r for r in retentions if r is not None]
    return {
        "avg_ctr": round(sum(ctrs) / len(ctrs), 1) if ctrs else None,
        "avg_retention_rate": (
            round(sum(retentions) / len(retentions), 1) if retentions else None
        ),
    }


# ---------------------------------------------------------------------------
# Log + index
# ---------------------------------------------------------------------------


def append_log(vault: Path, project: dict, phase: int) -> None:
    log_path = vault / "log.md"
    line = (
        f"- {_utcnow()} — Phase {phase} done — "
        f"[[{project['folder']}]]\n"
    )
    log_path.parent.mkdir(parents=True, exist_ok=True)
    if not log_path.exists():
        log_path.write_text("# Log\n\n", encoding="utf-8")
    with log_path.open("a", encoding="utf-8") as fh:
        fh.write(line)


def refresh_index(vault: Path) -> None:
    folders = []
    for entry in sorted(vault.iterdir()):
        if not entry.is_dir():
            continue
        if entry.name in {"wiki", "resources"} or entry.name.startswith("."):
            continue
        if (entry / "project.md").exists():
            folders.append(entry.name)
    lines = ["# Vault Index", ""]
    lines.append(f"Last refreshed: {_utcnow()}")
    lines.append("")
    lines.append("## Videos")
    lines.append("")
    for name in folders:
        lines.append(f"- [[{name}]]")
    (vault / "index.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


# ---------------------------------------------------------------------------
# Read helpers (consumers that only need history-like data)
# ---------------------------------------------------------------------------


def load_dashboard() -> dict:
    """Return the dashboard frontmatter as a plain dict.

    Returns an empty default if the vault/dashboard is absent or unreadable,
    so callers can keep running without special-casing.
    """
    default = {
        "channel": {"name": "Unknown"},
        "insights": {
            "avg_ctr": None,
            "avg_retention_rate": None,
            "top_performing_topics": [],
            "title_patterns": {},
            "retention_patterns": {},
        },
        "videos": [],
    }
    if frontmatter is None:
        return default
    vault = get_vault_root()
    page = vault / "wiki" / "analytics" / "채널-대시보드.md"
    if not page.exists():
        return default
    try:
        post = frontmatter.load(page)
    except Exception:  # noqa: BLE001
        return default
    data = dict(post.metadata)
    data.setdefault("channel", default["channel"])
    data.setdefault("insights", default["insights"])
    data.setdefault("videos", [])
    return data
