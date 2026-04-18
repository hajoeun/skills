# 프로젝트 컨텍스트 — vault 경로 규칙 + `project.md` 스키마

veast는 모든 프로젝트 데이터를 Obsidian vault(`$VEAST_VAULT_PATH`, 기본값 `~/Movies/Youtube/`) 안에 직접 저장한다. 영상 폴더 자체가 프로젝트 디렉토리이며, 추상 지식은 별도 `wiki/` 트리가 담당한다.

## 디렉토리 컨벤션

```
$VEAST_VAULT_PATH/                       # 예: ~/Movies/Youtube/
├── 260416 민상기인터뷰/                  # 영상 폴더 = 프로젝트 디렉토리
│   ├── project.md                       # 프로젝트 상태 (frontmatter)
│   ├── concept.md                       # Phase 1 산출물
│   ├── interview_민상기.srt             # Phase 2 입력
│   ├── edit-guide.yaml                  # Phase 2 산출물
│   ├── edit-guide.md                    # Phase 2 산출물(사람이 읽기용)
│   ├── packaging.md                     # Phase 4 산출물
│   ├── upload-kit.md                    # Phase 5 산출물
│   ├── review.md                        # Phase 6 산출물
│   ├── analytics_{72h|1w|4w}.json       # Phase 6 원본 API 응답
│   ├── analysis_context.md              # Phase 6 구조화 컨텍스트
│   └── *.mov, *.mp4                     # 영상 원본 (gitignored)
├── wiki/
│   ├── videos/                          # 퍼블리시된 영상 카드
│   ├── guests/                          # 게스트 인물 카드
│   ├── topics/                          # 주제 노드
│   ├── learnings/                       # 검증된 패턴
│   ├── strategy/                        # 채널 전략
│   └── analytics/채널-대시보드.md        # 채널 집계 (구 `_history.json` 대체)
├── index.md                             # 자동 갱신 카탈로그
├── log.md                               # 자동 append 이벤트 로그
└── resources/                           # 채널 자산
```

폴더 이름은 `YYMMDD 제목` 형식(예: `260416 민상기인터뷰`). `manage_project.py new`가 이 형식으로 생성한다.

---

## project.md 스키마

프로젝트당 하나. 영상 폴더 루트의 `project.md`가 YAML frontmatter로 상태를 담는다. 본문은 자유 노트 영역 — 스크립트는 frontmatter만 읽고 쓴다.

```yaml
---
type: project
id: "260416 민상기인터뷰"            # 폴더명과 동일
folder: "260416 민상기인터뷰"
video_type: 인터뷰                   # 인터뷰 / 브이로그 / 팟캐스트 / 탐방로그 / 숏폼
title: "민상기 인터뷰"                # 내부 작업 제목 (최종 제목은 Phase 4에서 별도 결정)
guest: "[[민상기]]"                  # wiki/guests/*.md로 연결 (인터뷰/팟캐스트일 때)
target_audience: "개발자, 스타트업 관계자"
target_views: 10000
expected_length: "15 minutes"
filming_date: 2026-04-16
current_phase: 3                     # 1–6
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
metrics: null                        # Phase 6 이후 { views_4w, ctr, retention_rate, ... }
learnings: null                      # Phase 6 이후
created_at: "2026-04-16T09:00:00Z"
updated_at: "2026-04-16T09:00:00Z"
---

<!-- 본문은 자유 노트 영역. 기획 중 떠오른 생각, 참고 링크 등. -->
```

### 필드 설명

| 필드 | 타입 | 설명 |
|------|------|------|
| `type` | literal `project` | 위키 내 문서 구분자 |
| `id` | string | 폴더명과 동일 (`YYMMDD 제목`) |
| `folder` | string | 폴더명 — 위키링크 타겟 |
| `video_type` | enum | `인터뷰` / `브이로그` / `팟캐스트` / `탐방로그` / `숏폼` |
| `guest` | `[[wikilink]]` \| `null` | 인터뷰/팟캐스트일 때 게스트 페이지로 연결 |
| `phase_results.N.status` | enum | `pending` / `in-progress` / `done` / `skipped` |
| `phase_results.N.result_file` | string? | Phase 산출물 파일명 |
| `current_phase` | int (1–6) | 가장 진행된 Phase |
| `insights_from_previous` | list[str] | `wiki/analytics/채널-대시보드.md`에서 주입된 이전 학습 |
| `status` | enum | `draft` / `ready` / `published` |

### Phase별 읽기/쓰기

| Phase | 읽기 | 쓰기 |
|-------|------|------|
| 1 | `wiki/analytics/채널-대시보드.md`(insights), `wiki/guests/*`, `wiki/topics/*` | `project.md` 생성, `concept.md`, `wiki/guests/{name}.md` |
| 2 | `project.md`, SRT | `phase_results.2`, `edit-guide.yaml`, `edit-guide.md`, `wiki/topics/*.md` |
| 3 | `edit-guide.yaml` | (수동 편집, 파일 변경 없음) |
| 4 | `concept.md`, SRT | `phase_results.4`, `packaging.md`, `wiki/videos/{folder}.md` 초안 |
| 5 | 최종 SRT | `phase_results.5`, `upload-kit.md`, `wiki/videos/{folder}.md` published |
| 6 | `project.md` 전체, YouTube API | `phase_results.6`, `review.md`, `metrics`, `learnings`, `wiki/videos/{folder}.md`, `wiki/learnings/*.md`, `wiki/strategy/채널-전략.md`, `wiki/analytics/채널-대시보드.md` |

---

## 채널 대시보드 — `wiki/analytics/채널-대시보드.md`

기존 `_history.json`의 `channel` + `insights` + `videos[].metrics`를 frontmatter로 이전했다. Phase 6 완료 시 `wiki_updater.update_dashboard()`가 자동 재계산한다.

```yaml
---
type: dashboard
channel:
  name: "하조은"
  updated_at: "2026-04-30T20:00:00Z"
insights:
  avg_ctr: 5.8
  avg_retention_rate: 42.3
  top_performing_topics: [해커톤, 창업, AI]
  title_patterns:
    with_numbers: { avg_ctr: 7.1, count: 8 }
    question_format: { avg_ctr: 6.2, count: 5 }
    how_to: { avg_ctr: 5.5, count: 3 }
  retention_patterns:
    hook_in_first_30s: { avg_retention: 48.2, count: 6 }
    slow_intro: { avg_retention: 35.1, count: 4 }
videos:                               # 최근 N개 영상 요약 (프루닝됨)
  - id: "260416 민상기인터뷰"
    link: "[[260416 민상기인터뷰]]"
    published: 2026-04-30
    metrics: { views_4w: 8200, ctr: 6.3, retention_rate: 45.2 }
---
```

### 데이터 흐름

```
Phase 6 완료
    ↓
wiki_updater.update_for_phase(6, project, project_dir)
    ├─ update_video_page       → wiki/videos/{folder}.md (metrics 반영)
    ├─ update_learnings        → wiki/learnings/{name}.md (verified_count++, confidence 재계산)
    ├─ update_strategy         → wiki/strategy/채널-전략.md (관찰 기록 append)
    └─ update_dashboard        → wiki/analytics/채널-대시보드.md (insights 재계산)
    ↓
다음 프로젝트 Phase 1
    ↓
insights_from_previous = 대시보드 insights에서 주입
```

영상을 만들수록 insights가 풍부해지고, AI의 제안이 이 채널에 특화된다. 게스트·주제 페이지는 Obsidian 그래프뷰에서 연결을 시각화한다.

→ 위키 페이지별 상세 frontmatter 스키마: `references/wiki-frontmatter.md`
