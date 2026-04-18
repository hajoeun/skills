#!/usr/bin/env python3
"""Vault initialization — scaffold the Obsidian vault for veast.

Run once after installing the skill in a fresh vault (typically
`~/Movies/Youtube/`). Creates the wiki/ layout, seeds AGENT.md / index.md /
log.md, merges a .gitignore, and (optionally) drives the Obsidian CLI to
install plugins and merge "Excluded files" patterns.

Idempotent: re-running only adds what's missing and never overwrites user
edits (use --force to replace AGENT.md).
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Templates (inline constants)
# ---------------------------------------------------------------------------

WIKI_SUBFOLDERS = (
    "videos",
    "guests",
    "topics",
    "strategy",
    "learnings",
    "analytics",
)

AGENT_MD = """# AGENT.md — vault 유지보수 규칙

이 vault는 [veast 스킬](https://github.com/hajoeun/skills)의 Obsidian vault로,
유튜브 영상 제작 파이프라인의 **영상 폴더 + 추상 지식 위키**를 함께 보관한다.

## 2레이어 구조

1. **영상 폴더** — vault 루트 하위 `projects/` 폴더 내에 `YYMMDD 제목` 형식으로
   배치 (예: `projects/260101 홍길동인터뷰/`). 프로젝트 단위 작업 파일을 모두 담는다:
   `project.md`(frontmatter 상태), `concept.md`, `edit-guide.yaml`, `packaging.md`,
   `upload-kit.md`, `review.md`, SRT·영상 원본.

2. **추상 지식 위키 (`wiki/`)** — 영상을 가로지르는 지식을 축적한다.
   - `wiki/videos/` — 퍼블리시된 영상 카드
   - `wiki/guests/` — 게스트 인물 카드
   - `wiki/topics/` — 주제 노드
   - `wiki/learnings/` — 검증된 패턴
   - `wiki/strategy/` — 채널 전략
   - `wiki/analytics/채널-대시보드.md` — 채널 집계

## Frontmatter 스키마

각 페이지 타입의 필수/선택 필드는 스킬 설치 위치의
`skills/veast/references/wiki-frontmatter.md`를 참조한다.

## 페이지 upsert 원칙

veast 스크립트(`wiki_updater.py`)가 위키 페이지를 쓸 때 따르는 규칙:

- **멱등**: 같은 Phase를 두 번 완료해도 중복 엔트리가 생기지 않는다.
- **Frontmatter-only 쓰기**: 기존 페이지를 load → metadata만 merge → save.
  본문(body)은 건드리지 않으므로 사용자 수동 노트가 보존된다.
- **링크 형식**: 모든 영상·게스트·주제 참조는 `[[wikilink]]` 사용.

## 자동 갱신 파일 (수동 편집 시 덮어쓰기 주의)

다음 파일은 Phase 완료 훅이 갱신하거나 재생성한다:

- `log.md` — 이벤트 로그. veast가 append-only로 추가하므로 수동 추가도 안전
- `index.md` — **완전 재생성**된다. 수동 편집 금지 (Dataview 쿼리 블록을 원하면
  별도 `wiki/*.md`에 두는 것을 권장)
- `wiki/videos/*.md`, `wiki/guests/*.md`, `wiki/topics/*.md`,
  `wiki/learnings/*.md`, `wiki/analytics/채널-대시보드.md` —
  frontmatter가 자동 갱신된다. 본문은 보존되지만, frontmatter 수동 편집은
  다음 Phase 완료 시 덮어쓰일 수 있다.

## 스킬 비활성 상태에서 수동 편집

veast 스크립트를 거치지 않고 직접 편집할 때:
- 프로젝트 폴더는 `projects/` 하위에 `YYMMDD 제목` 명명 규칙으로 유지
- `project.md`의 `phase_results`를 직접 수정할 때는 `updated_at` 필드도 갱신
- 새로 만든 게스트/주제 노드도 frontmatter `type` 필드 필수

## 권장 Obsidian 플러그인

`/video init`이 자동 설치·활성화한다:
- **Dataview** — 위키 페이지 집계 쿼리
- **Templater** — 노트 템플릿
- **Graph Analysis** — 그래프뷰 고급 분석
"""

INDEX_MD_SEED = """# Vault Index

자동 갱신됩니다. 영상 폴더를 추가하거나 Phase를 완료하면 veast가 이 파일을 재생성합니다.

## Videos

_(아직 영상이 없습니다. `/video new`로 첫 프로젝트를 시작하세요.)_
"""

LOG_MD_SEED = """# Log

veast Phase 훅이 append-only로 이벤트를 기록합니다.

"""

GITIGNORE_PATTERNS = (
    "# Video sources (영상 원본은 vault에 두되 git에는 제외)",
    "*.mp4",
    "*.MP4",
    "*.mov",
    "*.MOV",
    "*.mkv",
    "*.vrew",
    "*.psd",
    "*.fcpxml",
    "",
    "# System",
    ".DS_Store",
    "",
    "# Obsidian (config은 유지, cache·workspace만 제외)",
    ".obsidian/workspace*",
    ".obsidian/cache",
)


def _ignore_filters_js() -> str:
    """JS snippet for `obsidian eval` — merges Excluded files patterns."""
    return (
        "const cur = app.vault.config.userIgnoreFilters || [];"
        "const add = ['\\\\.mp4$','\\\\.MP4$','\\\\.mov$','\\\\.MOV$',"
        "'\\\\.mkv$','\\\\.vrew$','\\\\.psd$','\\\\.fcpxml$'];"
        "app.vault.config.userIgnoreFilters = [...new Set([...cur, ...add])];"
        "app.vault.saveConfig();"
    )


OBSIDIAN_PLUGINS = ("dataview", "templater-obsidian", "graph-analysis")


# ---------------------------------------------------------------------------
# Reporter — uniform stdout handling + --dry-run support
# ---------------------------------------------------------------------------


class Reporter:
    def __init__(self, dry_run: bool) -> None:
        self.dry_run = dry_run
        self.actions: list[str] = []

    def created(self, path: Path, kind: str = "file") -> None:
        prefix = "would create" if self.dry_run else "created"
        msg = f"  [{prefix}] {kind}: {path}"
        self.actions.append(msg)
        print(msg)

    def skipped(self, path: Path, reason: str) -> None:
        print(f"  [skip] {path} — {reason}")

    def updated(self, path: Path, note: str) -> None:
        prefix = "would update" if self.dry_run else "updated"
        msg = f"  [{prefix}] {path} — {note}"
        self.actions.append(msg)
        print(msg)

    def info(self, msg: str) -> None:
        print(msg)

    def warn(self, msg: str) -> None:
        print(f"  [warn] {msg}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Filesystem steps
# ---------------------------------------------------------------------------


def _write(path: Path, content: str, reporter: Reporter) -> None:
    if reporter.dry_run:
        reporter.created(path)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    reporter.created(path)


def ensure_wiki_tree(vault: Path, reporter: Reporter) -> None:
    for name in WIKI_SUBFOLDERS:
        folder = vault / "wiki" / name
        gitkeep = folder / ".gitkeep"
        if folder.is_dir() and gitkeep.exists():
            reporter.skipped(folder, "already exists")
            continue
        if reporter.dry_run:
            reporter.created(folder, kind="dir")
            reporter.created(gitkeep)
            continue
        folder.mkdir(parents=True, exist_ok=True)
        if not gitkeep.exists():
            gitkeep.write_text("", encoding="utf-8")
        reporter.created(folder, kind="dir")


def ensure_projects_tree(vault: Path, reporter: Reporter) -> None:
    folder = vault / "projects"
    gitkeep = folder / ".gitkeep"
    if folder.is_dir() and gitkeep.exists():
        reporter.skipped(folder, "already exists")
        return
    if reporter.dry_run:
        reporter.created(folder, kind="dir")
        reporter.created(gitkeep)
        return
    folder.mkdir(parents=True, exist_ok=True)
    if not gitkeep.exists():
        gitkeep.write_text("", encoding="utf-8")
    reporter.created(folder, kind="dir")


def ensure_agent_md(vault: Path, reporter: Reporter, force: bool) -> None:
    path = vault / "AGENT.md"
    if path.exists() and not force:
        reporter.skipped(path, "already exists (use --force to overwrite)")
        return
    _write(path, AGENT_MD, reporter)


def ensure_index_md(vault: Path, reporter: Reporter) -> None:
    path = vault / "index.md"
    if path.exists():
        reporter.skipped(path, "already exists")
        return
    _write(path, INDEX_MD_SEED, reporter)


def ensure_log_md(vault: Path, reporter: Reporter) -> None:
    path = vault / "log.md"
    if path.exists():
        reporter.skipped(path, "already exists")
        return
    ts = datetime.now(timezone.utc).isoformat()
    content = LOG_MD_SEED + f"- {ts} — Vault initialized\n"
    _write(path, content, reporter)


def merge_gitignore(vault: Path, reporter: Reporter) -> None:
    path = vault / ".gitignore"
    existing_lines: list[str] = []
    if path.exists():
        existing_lines = path.read_text(encoding="utf-8").splitlines()

    existing_set = {line.strip() for line in existing_lines if line.strip()}
    missing_non_comment = [
        line for line in GITIGNORE_PATTERNS
        if line.strip()
        and not line.lstrip().startswith("#")
        and line.strip() not in existing_set
    ]

    if not missing_non_comment and path.exists():
        reporter.skipped(path, "all patterns already present")
        return

    if not path.exists():
        _write(path, "\n".join(GITIGNORE_PATTERNS) + "\n", reporter)
        return

    # Append only the missing actual patterns (no orphan comment headers)
    appended = (
        "\n# --- added by veast init ---\n"
        + "\n".join(missing_non_comment)
        + "\n"
    )
    if reporter.dry_run:
        reporter.updated(path, f"would append {len(missing_non_comment)} patterns")
        return
    with path.open("a", encoding="utf-8") as fh:
        fh.write(appended)
    reporter.updated(path, f"appended {len(missing_non_comment)} patterns")


def maybe_git_init(vault: Path, reporter: Reporter, do_git: bool) -> None:
    if not do_git:
        return
    if (vault / ".git").exists():
        reporter.skipped(vault / ".git", "git repo already initialized")
        return
    if reporter.dry_run:
        reporter.created(vault / ".git", kind="dir")
        return
    try:
        subprocess.run(
            ["git", "init", "--quiet"],
            cwd=vault,
            check=True,
            timeout=15,
        )
        reporter.created(vault / ".git", kind="dir")
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError) as exc:
        reporter.warn(f"git init failed: {exc}")


# ---------------------------------------------------------------------------
# Obsidian CLI integration
# ---------------------------------------------------------------------------


CLI_ACTIVATION_MSG = """
[obsidian] Obsidian CLI가 감지되지 않았습니다.

CLI 없이도 veast는 동작하지만, 플러그인 자동 설치와 Excluded files 자동
설정이 생략됩니다. 활성화 방법:

  1. Obsidian 1.12.7+ installer로 업데이트
     (https://obsidian.md/download)
  2. Obsidian 실행 → Settings → General →
     "Command line interface" 활성화
     (macOS: sudo 심볼릭링크 프롬프트 수락)
  3. 터미널 재시작 후 이 스크립트를 다시 실행

수동 대안:
  - 플러그인: Obsidian에서 Dataview, Templater, Graph Analysis를
    Community plugins에서 직접 설치·활성화
  - Excluded files (Settings → Files & Links): *.mp4, *.mov, *.vrew,
    *.psd, *.fcpxml 패턴 추가
"""


def configure_obsidian(vault: Path, mode: str, reporter: Reporter) -> None:
    if mode == "off":
        reporter.info("\n[obsidian] --obsidian=off: skipped.")
        return

    cli = shutil.which("obsidian")
    if not cli:
        if mode == "strict":
            raise RuntimeError(
                "obsidian CLI not found — --obsidian=strict requires it on PATH"
            )
        reporter.info(CLI_ACTIVATION_MSG)
        return

    reporter.info("\n[obsidian] CLI detected — configuring vault...")

    steps: list[tuple[str, list[str]]] = [
        ("allow community plugins", ["plugins:restrict", "off"]),
        *[
            (f"install plugin {pid}", ["plugin:install", f"id={pid}", "enable"])
            for pid in OBSIDIAN_PLUGINS
        ],
        (
            "merge Excluded files patterns",
            ["eval", f"code={_ignore_filters_js()}"],
        ),
    ]

    for label, args in steps:
        if reporter.dry_run:
            reporter.info(f"  [would run] obsidian {' '.join(args)}")
            continue
        try:
            subprocess.run(
                [cli, *args],
                cwd=vault,
                check=True,
                timeout=60,
                capture_output=True,
            )
            reporter.info(f"  [ok] {label}")
        except subprocess.CalledProcessError as exc:
            stderr = (exc.stderr or b"").decode("utf-8", errors="replace").strip()
            msg = f"obsidian {args[0]} 실패 ({label}): {stderr or exc}"
            if mode == "strict":
                raise RuntimeError(msg) from exc
            reporter.warn(msg + f"\n          수동 실행: obsidian {' '.join(args)}")
        except subprocess.TimeoutExpired:
            msg = f"obsidian {args[0]} 타임아웃 ({label})"
            if mode == "strict":
                raise RuntimeError(msg)
            reporter.warn(msg)


# ---------------------------------------------------------------------------
# Vault path resolution
# ---------------------------------------------------------------------------


def resolve_vault(arg: str | None) -> Path:
    if arg:
        return Path(arg).expanduser().resolve()
    env = os.environ.get("VEAST_VAULT_PATH")
    if env:
        return Path(env).expanduser().resolve()
    return Path.cwd().resolve()


# ---------------------------------------------------------------------------
# Next-steps summary
# ---------------------------------------------------------------------------


NEXT_STEPS = """
[done] Vault 초기화 완료.

다음 단계:
  - 첫 프로젝트 시작:
      python3 scripts/manage_project.py new --type 인터뷰 --title "<제목>"
    또는 Claude Code에서 /video new

  - 기존 `~/.veast/projects/` 데이터가 있으면 향후 `/video migrate` 커맨드로
    영상 폴더로 이전하세요 (현재 미구현).

  - Obsidian에서 이 vault가 처음이라면 "Open folder as vault"로 한 번
    열어주세요. 이후 /video init을 다시 실행하면 플러그인 자동 설치가
    동작합니다.
"""


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def run_init(
    vault: Path,
    *,
    force: bool,
    do_git: bool,
    obsidian_mode: str,
    dry_run: bool,
) -> int:
    reporter = Reporter(dry_run=dry_run)

    if not vault.is_dir():
        reporter.warn(
            f"vault 경로가 존재하지 않습니다: {vault}\n"
            f"  디렉토리를 먼저 생성하거나 --vault로 올바른 경로를 지정하세요."
        )
        return 1

    if not os.environ.get("VEAST_VAULT_PATH"):
        reporter.info(
            f"[hint] VEAST_VAULT_PATH 환경변수가 미설정입니다. "
            f"다음 줄을 ~/.zshrc 또는 ~/.bashrc에 추가하세요:\n"
            f"    export VEAST_VAULT_PATH=\"{vault}\"\n"
        )

    reporter.info(f"[init] vault: {vault}")
    if dry_run:
        reporter.info("[init] --dry-run: 실제 변경 없음\n")

    reporter.info("\n[files] scaffolding...")
    ensure_wiki_tree(vault, reporter)
    ensure_projects_tree(vault, reporter)
    ensure_agent_md(vault, reporter, force=force)
    ensure_index_md(vault, reporter)
    ensure_log_md(vault, reporter)
    merge_gitignore(vault, reporter)
    maybe_git_init(vault, reporter, do_git=do_git)

    configure_obsidian(vault, obsidian_mode, reporter)

    if not dry_run:
        reporter.info(NEXT_STEPS)
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Initialize an Obsidian vault for the veast skill"
    )
    parser.add_argument(
        "--vault",
        help="Vault path (default: $VEAST_VAULT_PATH or current directory)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite AGENT.md even if it exists",
    )
    parser.add_argument(
        "--git",
        action="store_true",
        help="Run `git init` if no .git/ is present",
    )
    parser.add_argument(
        "--obsidian",
        choices=("auto", "off", "strict"),
        default="auto",
        help=(
            "How to treat the Obsidian CLI: "
            "auto (best-effort, default), off (skip), strict (fail if unavailable)"
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be done, make no changes",
    )

    args = parser.parse_args()

    vault = resolve_vault(args.vault)
    try:
        code = run_init(
            vault,
            force=args.force,
            do_git=args.git,
            obsidian_mode=args.obsidian,
            dry_run=args.dry_run,
        )
    except RuntimeError as exc:
        print(f"[error] {exc}", file=sys.stderr)
        sys.exit(1)
    sys.exit(code)


if __name__ == "__main__":
    main()
