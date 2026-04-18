# Phase 6: 성과 분석 + 피드백 루프

## 개요

YouTube Analytics API에서 데이터를 수집하고, Claude Code가 정성 분석을 수행하여
구체적 개선 액션이 포함된 다음 영상 브리핑을 생성한다.
Anthropic API를 별도로 호출하지 않고, Claude Code 컨텍스트 내에서 분석한다.

## 2단계 플로우

### Step 1: 데이터 수집 + 정량 분석 (CLI)

```bash
veast project collect --dir <project-dir> --period 72h
```

자동으로 수행되는 작업:
1. YouTube Analytics API / Data API에서 데이터 수집
2. 정량 분석 (리텐션 이탈 구간, CTR 비교, 트래픽 분포)
3. `analytics_{period}.json` 저장 (원본 API 응답)
4. `analysis_context.md` 생성 (Claude Code에게 넘길 구조화 컨텍스트)

### Step 2: 정성 분석 + 리뷰 생성 (Claude Code)

사용자가 `/video analyze`를 실행하면:
1. Claude Code가 `analysis_context.md`를 읽는다
2. 댓글 감성 분석을 수행한다 (긍정/부정/질문/요청 분류)
3. 데이터 기반 성과 평가를 수행한다
4. 다음 영상 브리핑을 생성한다
5. `review.md`를 아래 템플릿 형식으로 작성한다
6. `save_review_and_update_history()`로 저장 + `_history.json` 갱신

```python
from pathlib import Path
from veast.analyzer import save_review_and_update_history

review_path = save_review_and_update_history(
    project_dir=Path("<project-dir>"),
    review_md=review_content,  # Claude Code가 생성한 리뷰 마크다운
)
```

## 데이터 수집 시점

| 시점 | 목적 |
|------|------|
| 업로드 후 72시간 | 초기 반응 확인 (CTR, 초기 리텐션) |
| 업로드 후 1주 | 안정화된 지표 확인 (알고리즘 추천 효과) |
| 업로드 후 4주 | 장기 성과 확정 (최종 평가) |

## 수집 데이터 포인트

### YouTube Analytics API
- 조회수 (views)
- 노출수 (impressions)
- CTR (impressions_click_through_rate)
- 평균 시청 시간 (average_view_duration)
- 시청 지속률 곡선 (audience_retention)
- 트래픽 소스 (traffic_source)
- 구독자 변동 (subscribers_gained, subscribers_lost)

### YouTube Data API
- 좋아요/싫어요 수
- 댓글 목록 (감성 분석용)
- 댓글 수

## 분석 방법론

### 1. 리텐션 곡선 분석 (자동 — Step 1)

- 이탈 급감 구간 특정 (5%p 이상 급락)
- 높은 리텐션 구간 특정 (80% 이상)
- 채널 평균 리텐션과 비교
- `analysis_context.md`에 결과 포함

### 2. CTR 분석 (자동 — Step 1)

- 채널 평균 CTR 대비 이 영상의 CTR
- 제목 전략 분류 (숫자형, 질문형, 하우투, 기타)
- `_history.json.insights.title_patterns`와 비교
- `analysis_context.md`에 결과 포함

### 3. 댓글 감성 분석 (Claude Code — Step 2)

- 긍정/부정/질문/요청 분류
- 자주 언급되는 키워드 추출
- 시청자가 가장 반응한 주제 특정
- "다음에 이런 거 해주세요" 유형의 요청 수집

### 4. 다음 영상 브리핑 (Claude Code — Step 2)

분석 결과를 종합하여 구체적 액션을 제시:
- 유지할 것: 이번 영상에서 효과적이었던 요소
- 개선할 것: 이탈 원인 + 구체적 대안
- 시도할 것: 댓글에서 수집한 시청자 요청, 트렌드

## 프롬프트 가이드

### 분석 원칙

```
- "CTR이 낮습니다"에서 끝나지 않고, 원인 + 대안 + 근거까지 제시
- 리텐션 곡선의 이탈 구간을 편집 가이드 타임코드와 매핑하여 "왜" 이탈했는지 분석
- 채널 평균과 비교하여 상대적 성과를 평가
- 다음 영상에 바로 적용할 수 있는 3가지 카테고리(유지/개선/시도)로 브리핑
```

### 입력 변수

| 변수 | 소스 | 설명 |
|------|------|------|
| `analysis_context.md` | Step 1 산출물 | 핵심 지표, 리텐션 커브, CTR 분석, 트래픽, 댓글 원문 |
| `edit-guide.md` | Phase 2 산출물 | 편집 구성 (리텐션-타임코드 매핑용) |
| `packaging.md` | Phase 4 산출물 | 사용된 제목 전략 |
| `_history.json` | 채널 히스토리 | 채널 평균 지표, 패턴 데이터 |

---

## Few-shot 예시

### 예시 1: 인터뷰 영상 성과 분석

**입력 (요약):**
- 조회수: 8,200 (4주), CTR: 6.3%, 리텐션: 45.2%
- 채널 평균: CTR 5.8%, 리텐션 42.3%
- 제목 전략: 숫자형
- 주요 이탈: 3:15 (본론 시작 직후)

**출력:**

```markdown
# 성과 리포트: 홍길동 인터뷰

## 핵심 지표

| 지표 | 이 영상 | 채널 평균 | 비교 |
|------|---------|----------|------|
| 조회수 (4주) | 8,200 | 5,800 | +41.4% |
| CTR | 6.3% | 5.8% | +0.5%p |
| 평균 시청 시간 | 8:42 | 7:15 | +19.8% |
| 시청 지속률 | 45.2% | 42.3% | +2.9%p |

## 리텐션 분석

- 주요 이탈 구간: 3:15 — "해커톤 도전기" 본론 시작 직후
- 이탈 원인 추정: 훅에서 이미 결과(우승)를 알려줬으므로 본론 초반에 긴장감 저하
- 높은 리텐션 구간: 0:00-0:32 (훅, 78%), 8:42-12:05 (교훈+마무리, 52%)

## CTR 분석

- 제목 전략: 숫자형 ("3번 떨어진 해커톤, 4번째에 1등한 비결")
- 같은 전략 과거 평균 CTR: 7.1%
- 평가: 채널 평균 대비 +0.5%p 양호하나, 숫자형 평균(7.1%)에 미달

## 댓글 분석

- 총 댓글: 47개
- 감성: 긍정 72% / 부정 6% / 중립 22%
- 주요 키워드: 해커톤, 도전, 포기하지 않기
- 시청자 요청: "해커톤 준비 과정 디테일", "팀 빌딩 노하우"

## 다음 영상 브리핑

### 유지할 것
- 숫자형 제목 전략, 첫 30초 훅 배치 (리텐션 78%)

### 개선할 것
- 본론 초반 이탈 → 결과를 훅에서 완전히 스포일러하지 않는 구성

### 시도할 것
- 시청자 요청 "해커톤 준비 디테일"을 다음 인터뷰 질문에 포함
```

---

## review.md 출력 템플릿

```markdown
# 성과 리포트: {프로젝트 이름}

## 핵심 지표

| 지표 | 이 영상 | 채널 평균 | 비교 |
|------|---------|----------|------|
| 조회수 | {N} | {N} | {+/-}% |
| CTR | {N}% | {N}% | {+/-}%p |
| 평균 시청 시간 | {MM:SS} | — | — |
| 시청 지속률 | {N}% | {N}% | {+/-}%p |

## 리텐션 분석

- 주요 이탈 구간: {위치}% — {이탈 폭}%p
- 이탈 원인 추정: {분석}
- 높은 리텐션 구간: {위치}% — {리텐션}%
- 반등 구간 분석: {분석}

## CTR 분석

- 제목 전략: {사용한 전략}
- 같은 전략 과거 평균 CTR: {N}%
- 평가: {분석}

## 트래픽 분석

- 1위 트래픽 소스: {소스} ({비율}%)
- 구독자 의존도: {비율}%
- 검색 유입: {비율}%
- 평가: {분석}

## 댓글 분석

- 총 댓글: {N}개
- 감성: 긍정 {N}% / 부정 {N}% / 질문 {N}% / 요청 {N}%
- 주요 키워드: {키워드 목록}
- 시청자 요청: {요청 목록}

## 다음 영상 브리핑

### 유지할 것
1. {구체적 요소} — {근거 데이터}
2. {구체적 요소} — {근거 데이터}
3. {구체적 요소} — {근거 데이터}

### 개선할 것
1. {문제점} → {구체적 대안} — {근거 데이터}
2. {문제점} → {구체적 대안} — {근거 데이터}
3. {문제점} → {구체적 대안} — {근거 데이터}

### 시도할 것
1. {제안} — {근거}
2. {제안} — {근거}
3. {제안} — {근거}
```

## _history.json 갱신

`save_review_and_update_history()` 호출 시 자동 수행:
1. `videos` 배열에 새 영상 데이터 추가 (metrics + learnings)
2. `insights` 재계산:
   - `avg_ctr`: 전체 영상 평균
   - `avg_retention_rate`: 전체 영상 평균
   - `top_performing_topics`: 조회수 상위 주제 갱신
   - `title_patterns`: 제목 전략별 CTR 통계 갱신
   - `retention_patterns`: 구성 패턴별 리텐션 통계 갱신

## 완료 조건

- `analysis_context.md` 파일 생성 (Step 1)
- `review.md` 파일 생성 (Step 2)
- `_history.json` 갱신 (Step 2)
- `project.json`의 Phase 6 상태 `completed`
- `project.json`의 `files.review`에 파일 경로 기록

---

## 성과 추적 재수집

Phase 6 리뷰 이후에도 영상 성과는 계속 변한다. 초기에 구독자 기반으로 시작한 영상이 이후 알고리즘 추천을 타면서 조회수가 급증하는 경우가 흔하다. 이 성장 추이를 다음 영상 기획에 반영하려면, 다음 영상 Phase 2 진입 시 이전 영상의 최신 데이터를 재수집해야 한다.

### 트리거

- `/video edit-guide` 실행 시 자동 (`references/phase-2-edit-guide.md` Step 0a 참조)
- 사용자가 명시적으로 재분석 요청 시

### 절차

1. `collect_analytics.py --period 4w` 재실행
2. 이전 `review.md`의 핵심 지표와 비교 테이블 생성
3. 성장/하락 원인 추정 분석 (알고리즘 추천? 검색 키워드? 외부 유입?)
4. `_history.json`의 해당 영상 metrics + learnings 업데이트
5. 새로운 인사이트를 다음 영상 기획에 반영

### 토큰 만료 대응

YouTube OAuth 토큰(`~/.veast/youtube_token.json`)은 일정 기간 후 만료된다.

- **토큰 파일**: `~/.veast/youtube_token.json`
- **클라이언트 시크릿**: `~/.veast/client_secrets.json`
- **만료 시 재발급**:
  ```python
  from google_auth_oauthlib.flow import InstalledAppFlow
  flow = InstalledAppFlow.from_client_secrets_file(
      '~/.veast/client_secrets.json',
      scopes=[
          'https://www.googleapis.com/auth/yt-analytics.readonly',
          'https://www.googleapis.com/auth/youtube.readonly'
      ]
  )
  creds = flow.run_local_server(port=0)
  from pathlib import Path
  Path('~/.veast/youtube_token.json').expanduser().write_text(creds.to_json())
  ```
- Bash 도구로 직접 실행 가능 (브라우저 인증이 자동으로 열림)
