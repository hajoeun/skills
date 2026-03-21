# 프로젝트 컨텍스트 — project.json / _history.json

## 디렉토리 컨벤션

```
~/.veast/projects/
    _history.json                          # 채널 레벨 히스토리
    2026-03-15-인터뷰-홍길동/
        project.json                       # 프로젝트 상태
        concept.md                         # Phase 1 산출물
        interview_홍길동.srt               # Phase 2 입력
        edit-guide.yaml                    # Phase 2 산출물 (YAML)
        edit-guide.md                      # Phase 2 산출물 (마크다운)
        packaging.md                       # Phase 4 산출물
        upload-kit.md                      # Phase 5 산출물
        review.md                          # Phase 6 산출물
```

---

## project.json 스키마

프로젝트당 하나의 파일. 영상 제작의 모든 단계에서 읽고 쓴다.

```json
{
  "id": "2026-03-15-인터뷰-홍길동",
  "current_phase": 3,
  "type": "인터뷰",
  "meta": {
    "guest": {
      "name": "홍길동",
      "title": "스타트업 CTO",
      "topics": ["해커톤", "제품 개발"]
    },
    "target_audience": "개발자, 스타트업 관계자",
    "target_views": 10000,
    "expected_length": "15 minutes",
    "filming_date": "2026-03-15",
    "youtube_video_id": null
  },
  "phase_results": {
    "1": {
      "status": "done",
      "result_file": "concept.md",
      "started_at": "2026-03-15T09:00:00Z",
      "completed_at": "2026-03-15T10:00:00Z"
    },
    "2": {
      "status": "done",
      "result_file": "edit-guide.yaml",
      "started_at": "2026-03-16T09:00:00Z",
      "completed_at": "2026-03-16T14:00:00Z"
    },
    "3": { "status": "in-progress", "result_file": null, "started_at": "2026-03-17T09:00:00Z", "completed_at": null },
    "4": { "status": "pending", "result_file": null, "started_at": null, "completed_at": null },
    "5": { "status": "pending", "result_file": null, "started_at": null, "completed_at": null },
    "6": { "status": "pending", "result_file": null, "started_at": null, "completed_at": null }
  },
  "insights_from_previous": [
    "숫자형 제목이 평균 대비 CTR +0.5%",
    "인트로 30초 내 핵심 질문 배치 시 리텐션 상승"
  ],
  "created_at": "2026-03-15T09:00:00Z",
  "updated_at": "2026-03-17T09:00:00Z"
}
```

### 필드 설명

| 필드 | 타입 | 설명 |
|------|------|------|
| `id` | string | `YYYY-MM-DD-유형-제목` 형식의 고유 식별자 |
| `current_phase` | int (1–6) | 현재 진행 중인 Phase 번호 |
| `type` | enum | `인터뷰` / `브이로그` / `팟캐스트` / `탐방로그` / `숏폼` |
| `meta` | object | 게스트, 타겟 오디언스, 목표 조회수, 예상 길이, 촬영일, YouTube ID |
| `phase_results.N.status` | enum | `pending` / `in-progress` / `done` / `skipped` |
| `phase_results.N.result_file` | string? | Phase 산출물 파일명 |
| `insights_from_previous` | list[str] | `_history.json`에서 가져온 이전 영상 인사이트 |

### Phase별 읽기/쓰기

| Phase | 읽기 | 쓰기 |
|-------|------|------|
| 1 | `_history.json` | `project.json` 생성, `concept.md` |
| 2 | `project.json`, SRT 파일 | `phase_results.2`, `edit-guide.yaml`, `edit-guide.md` |
| 3 | `edit-guide.md` | (수동 편집, 파일 변경 없음) |
| 4 | `concept.md`, SRT | `phase_results.4`, `packaging.md` |
| 5 | 최종 SRT | `phase_results.5`, `upload-kit.md` |
| 6 | `project.json` 전체, YouTube API | `phase_results.6`, `review.md`, `_history.json` |

---

## _history.json 스키마

채널 전체에서 하나의 파일. Phase 6 완료 시 갱신된다.

```json
{
  "channel": {
    "name": "내 채널",
    "updated_at": "2026-03-15T20:00:00Z"
  },
  "insights": {
    "avg_ctr": 5.8,
    "avg_retention_rate": 42.3,
    "top_performing_topics": ["해커톤", "창업", "AI"],
    "title_patterns": {
      "with_numbers": { "avg_ctr": 7.1, "count": 8 },
      "question_format": { "avg_ctr": 6.2, "count": 5 },
      "how_to": { "avg_ctr": 5.5, "count": 3 }
    },
    "retention_patterns": {
      "hook_in_first_30s": { "avg_retention": 48.2, "count": 6 },
      "slow_intro": { "avg_retention": 35.1, "count": 4 }
    }
  },
  "videos": [
    {
      "project_id": "2026-03-01-인터뷰-김철수",
      "title": "해커톤 1등의 비밀 | 김철수",
      "type": "인터뷰",
      "published_at": "2026-03-01T09:00:00Z",
      "metrics": {
        "views_72h": 1200,
        "views_1w": 3500,
        "views_4w": 8200,
        "ctr": 6.3,
        "retention_rate": 45.2,
        "avg_view_duration": "8:42"
      },
      "learnings": [
        "숫자형 제목이 평균 대비 CTR +0.5%",
        "인트로 30초 내 핵심 질문 배치 시 리텐션 상승"
      ]
    }
  ]
}
```

### 데이터 흐름

```
Phase 6 완료
    ↓
_history.json.videos에 새 영상 추가
    ↓
_history.json.insights 재계산 (평균 CTR, 상위 주제, 패턴 등)
    ↓
다음 프로젝트 Phase 1에서 _history.json 참조
    ↓
인사이트 기반 질문 리스트 생성
```

영상을 만들수록 `insights`가 풍부해지고, AI의 제안이 이 채널에 특화된다.

---

## Pydantic 모델 (`src/veast/project.py`)

모든 스키마는 Pydantic v2 모델로 정의되어 있다.

| 모델 | 용도 |
|------|------|
| `Project` | `project.json` 루트 |
| `ProjectType` | 영상 유형 enum |
| `PhaseStatus` | Phase 상태 enum (`pending`, `in-progress`, `done`, `skipped`) |
| `PhaseResult` | Phase별 상태 + 산출물 |
| `ProjectMeta` | 게스트, 타겟 등 메타 정보 |
| `GuestInfo` | 게스트/인터뷰이 정보 |
| `History` | `_history.json` 루트 |
| `ChannelInfo` | 채널 기본 정보 |
| `ChannelInsights` | 채널 레벨 집계 인사이트 |
| `VideoRecord` | 개별 영상 기록 |
| `VideoMetrics` | 조회수, CTR, 리텐션 등 성과 지표 |

### 유틸리티 함수

| 함수 | 설명 |
|------|------|
| `generate_project_id(type, title, date?)` | `"2026-03-15-인터뷰-홍길동"` 형식 ID 생성 |
| `create_project(type, title, meta?, insights?)` | 프로젝트 생성 + 디렉토리 + JSON 저장 |
| `load_project(dir)` / `save_project(project, dir)` | project.json CRUD |
| `start_phase(project, n)` / `complete_phase(project, n, result_file?)` | Phase 상태 전환 |
| `load_history(path?)` / `save_history(history, path?)` | _history.json CRUD |
| `add_video_to_history(history, record)` | 영상 기록 추가 |
| `recalculate_insights(history)` | 채널 인사이트 재계산 |
| `list_projects(root?)` | 프로젝트 목록 조회 |
