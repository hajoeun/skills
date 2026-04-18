# 위키 Frontmatter 스키마

veast 스킬이 vault(`$VEAST_VAULT_PATH`, 기본 `~/Movies/Youtube/`)에 기록하는 모든 마크다운 파일은 YAML frontmatter를 가진다. 파싱은 `python-frontmatter`로 통일한다.

공통 규칙:
- 링크 필드는 Obsidian `[[wikilink]]` 형식의 문자열 또는 문자열 배열
- 날짜는 ISO 8601 (YYYY-MM-DD 또는 YYYY-MM-DDTHH:MM:SSZ)
- 모든 스키마는 `type` 필드로 구분되므로 검색/필터가 쉬움
- 본문은 자유 노트 영역 — 스크립트는 frontmatter만 읽고 쓰며 본문을 파괴하지 않는다

---

## `project` — 영상 폴더 내 `project.md`

영상 제작 중 프로젝트 상태. 위치: `{VAULT}/{YYMMDD 제목}/project.md`.

```yaml
---
type: project
id: "260416 민상기인터뷰"            # 폴더명과 동일
folder: "260416 민상기인터뷰"
video_type: 인터뷰                   # 인터뷰 / 브이로그 / 팟캐스트 / 탐방로그 / 숏폼
guest: "[[민상기]]"                  # wiki/guests/민상기.md로 연결 (인터뷰/팟캐스트일 때)
filming_date: 2026-04-16
target_audience: 개발자, 스타트업 관계자
target_views: 10000
expected_length: 15 minutes
current_phase: 6                     # 1–6
phase_results:
  1: { status: done, result_file: concept.md, started_at: "...", completed_at: "..." }
  2: { status: done, result_file: edit-guide.yaml, ... }
  3: { status: in-progress, result_file: null, ... }
  4: { status: pending, ... }
  5: { status: pending, ... }
  6: { status: pending, ... }
insights_from_previous:
  - "숫자형 제목이 평균 대비 CTR +0.5%"
youtube_video_id: null               # Phase 5 이후 설정
status: draft                        # draft / ready / published
created_at: "2026-04-16T09:00:00Z"
updated_at: "2026-04-16T09:00:00Z"
---
```

필수: `type`, `id`, `folder`, `video_type`, `current_phase`, `phase_results`, `created_at`, `updated_at`. 나머지는 선택.

---

## `video` — `wiki/videos/{YYMMDD 제목}.md`

퍼블리시된 영상의 추상 지식 카드. Phase 4에서 초안 → Phase 5에서 published 상태 → Phase 6에서 성과 반영.

```yaml
---
type: video
id: "260416 민상기인터뷰"
project: "[[260416 민상기인터뷰/project]]"
title: "해커톤 1등의 비밀 | 민상기"
video_type: 인터뷰
guest: "[[민상기]]"
topics:
  - "[[바이브코딩]]"
  - "[[스타트업]]"
published: 2026-04-30
youtube_video_id: "abc123"
metrics:
  views_72h: 1200
  views_1w: 3500
  views_4w: 8200
  ctr: 6.3
  retention_rate: 45.2
  avg_view_duration: "8:42"
learnings:
  - "[[3컷 훅]]"
  - "숫자형 제목이 CTR +0.5%"
---
```

필수: `type`, `id`, `project`, `video_type`. `metrics` / `learnings` / `published`는 Phase 6 이후 채워짐.

---

## `guest` — `wiki/guests/{name}.md`

게스트(인터뷰이) 인물 카드. Phase 1에서 최초 생성, 이후 영상이 추가될 때마다 `videos` 누적.

```yaml
---
type: guest
name: 민상기
aliases: []
title: 스타트업 CTO
topics:
  - "[[바이브코딩]]"
videos:
  - "[[260416 민상기인터뷰]]"
first_appearance: 2026-04-16
---
```

필수: `type`, `name`, `videos`.

---

## `topic` — `wiki/topics/{topic}.md`

주제 노드. Phase 2(편집 가이드 확정) 시점에 `edit-guide.yaml`의 `sections` 제목에서 추출.

```yaml
---
type: topic
name: 바이브코딩
video_count: 6
videos:
  - "[[260416 민상기인터뷰]]"
  - "[[260325 이승민인터뷰]]"
related:
  - "[[AI 코딩]]"
---
```

필수: `type`, `name`, `videos`. `video_count`는 `len(videos)`와 동기화(멱등성).

---

## `learning` — `wiki/learnings/{name}.md`

검증된 패턴/학습. Phase 6의 성과 분석에서 채널 전반에 반복 검증된 항목을 승격 기록.

```yaml
---
type: learning
name: 3컷 훅
category: 편집                        # 편집 / 기획 / 패키징 / 타임스탬프 / 썸네일 / 제목
verified_count: 2
confidence: medium                    # low / medium / high (verified_count 임계값 기반)
videos:
  - "[[260416 민상기인터뷰]]"
  - "[[260325 이승민인터뷰]]"
first_observed: 2026-03-25
last_verified: 2026-04-16
---
```

필수: `type`, `name`, `category`, `verified_count`, `videos`.

---

## `dashboard` — `wiki/analytics/채널-대시보드.md`

채널 전체 집계. 기존 `_history.json`의 `channel` + `insights` + `videos[].metrics`를 frontmatter로 옮긴다. Phase 6 완료 시마다 재계산.

```yaml
---
type: dashboard
channel:
  name: "하조은"
  updated_at: "2026-04-30T20:00:00Z"
insights:
  avg_ctr: 5.8
  avg_retention_rate: 42.3
  top_performing_topics:
    - 해커톤
    - 창업
    - AI
  title_patterns:
    with_numbers: { avg_ctr: 7.1, count: 8 }
    question_format: { avg_ctr: 6.2, count: 5 }
    how_to: { avg_ctr: 5.5, count: 3 }
  retention_patterns:
    hook_in_first_30s: { avg_retention: 48.2, count: 6 }
    slow_intro: { avg_retention: 35.1, count: 4 }
videos:                               # wiki/videos/*.md 요약 (가장 최신 N개)
  - id: "260416 민상기인터뷰"
    link: "[[260416 민상기인터뷰]]"
    published: 2026-04-30
    metrics: { views_4w: 8200, ctr: 6.3, retention_rate: 45.2 }
---
```

필수: `type`, `channel`, `insights`. `videos` 배열은 프루닝(최근 20~50개)해도 됨 — 원본 지표는 `wiki/videos/*.md`가 보관.

---

## 직렬화 패턴 (스크립트 참고)

```python
import frontmatter
from pathlib import Path

def load_page(path: Path) -> frontmatter.Post:
    if not path.exists():
        return frontmatter.Post(content="", **{})
    return frontmatter.load(path)

def save_page(path: Path, post: frontmatter.Post) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(frontmatter.dumps(post), encoding="utf-8")
```

- Frontmatter `metadata`는 `post.metadata`(dict)로 접근
- 본문 보존이 중요: 기존 페이지를 load → metadata만 merge → save
