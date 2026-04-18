# Phase 2: 자막 → 편집 가이드 (킬러 피처)

## 개요

촬영 후 SRT 자막을 업로드하면, AI가 주제별로 세그멘테이션하고 조회수 극대화를 위한 편집 가이드를 생성한다. DaVinci Resolve에서 바로 참조할 수 있는 타임코드 테이블이 최종 산출물이다.

## 워크플로우

### Step 0: 데이터 재수집 + PD 분석

편집 가이드 생성 전 반드시 수행하는 사전 분석. 기계적 세그멘테이션만으로는 "정보 나열형" 편집밖에 나오지 않는다. PD 분석을 통해 "감정 아크형" 편집을 설계한다.

#### 0a. 이전 영상 최신 데이터 재수집

`/video edit-guide` 실행 시 첫 단계로:

1. `_history.json`에서 가장 최근 영상의 게시일 확인
2. `collect_analytics.py --period 4w`로 최신 데이터 재수집
   - 토큰 만료 시: `references/phase-6-review.md`의 "토큰 만료 대응" 참조
3. 이전 `review.md`의 핵심 지표와 비교 → 성장/하락 추이 분석
4. `_history.json`의 해당 영상 metrics + learnings 업데이트
5. 새로운 인사이트 도출: "이전 영상에서 검증된 패턴은? 미해결 과제는?"

#### 0b. PD 분석 — 자막에서 "보물" 찾기

교정 완료된 SRT 자막 전문을 통독하며 아래 체크리스트로 "보물"을 추출한다. 보물 = 시청자의 스크롤을 멈추거나, 영상을 끝까지 보게 만드는 순간.

**보물 찾기 체크리스트:**

1. **예상을 깨는 순간** — "이 인터뷰에서 이런 말이 나올 줄 몰랐다"
   - 주제와 어울리지 않는 깊은 발언 (예: 개발자 인터뷰에서 "죽음")
   - 게스트의 이미지와 다른 과거 경험 (예: 개발자가 헌팅 술집에서 영업)
   - 통념을 뒤집는 주장 (예: "기술이 아니라 영업이 해자다")

2. **그림이 그려지는 장면** — "시청자가 머릿속에 영상을 그릴 수 있다"
   - 구체적 장소 + 행동 (예: "건대 왕대박에 가서 사장님을 뵀다")
   - 시간+숫자 디테일 (예: "2016년부터 매년 일본에 갔다")
   - 감각적 묘사가 포함된 에피소드

3. **클립 가능한 한 마디** — "이 문장만 잘라도 숏폼이 된다"
   - 10초 이내로 전달되는 강력한 메시지
   - 예: "해서 잘하는 거지, 잘해서 하는 게 아니다"
   - 예: "매일매일 불안해요"

4. **스케일 서사** — "시간 축이 넓어서 무게감이 있다"
   - 수년~수십년의 시간이 압축된 서사 (예: "10년 기다린 꿈")
   - 과거→현재→미래를 관통하는 일관된 테마

#### 0c. concept.md 재검토

촬영 전 기획(concept.md)과 실제 인터뷰 결과를 비교:
- 기획했던 핵심 메시지가 실제로 나왔는가?
- 기획에 없던 더 강력한 메시지가 나왔는가?
- 기획 의도를 수정할 필요가 있는가?
- 영상의 진짜 힘이 어디에 있는가? (도구 비교? 인간 이야기? 비즈니스 인사이트?)

#### 0d. 제목/썸네일 방향 잠정 확정

이전 영상 학습 + 보물 분석을 종합하여 편집 구조를 결정할 방향을 잡는다.
- 이전 영상에서 검증된 패턴 유지 (예: 트렌딩 키워드, 구체적 숫자)
- 미해결 과제 해결 (예: 훅 강화, 감정 요소 추가)
- 제목 후보 2~3개를 제시하고 사용자와 잠정 확정
- Phase 4에서 최종 제목 후보 + 썸네일 상세 디렉션 확정

---

### Step 1: 자막 업로드 (`/video transcript`)

1. 사용자가 Whisper로 생성한 SRT 파일을 제공
2. `srt_parser.parse_srt(srt_path)` 호출 → `list[SubtitleEntry]` 반환
   - 각 SubtitleEntry: `index`, `start` (timedelta), `end` (timedelta), `text`
3. project.json의 `files.srt`에 파일 경로 기록
4. 자막 교정이 필요하면 `references/phase-2-proofread.md` 참조

### Step 2: 편집 가이드 생성 (`/video edit-guide`)

1. **주제 세그멘테이션**: 자막 내용을 분석하여 주제 단위로 섹션(A, B, C, ...) 구분
   - 각 섹션: 라벨, 자막 범위, 타임코드 범위, 주제 설명

2. **관심도 스코어 산출**: 각 섹션의 시청자 관심도 예측
   - 스코어링 기준: 갈등/긴장, 구체적 사례, 감정적 순간, 의외성, 실용적 정보
   - 높은 스코어 구간 = 훅(Hook) 후보

3. **훅 선정**: 가장 인상적인 구간을 Hook으로 선택
   - 영상 첫 30초에 배치할 하이라이트
   - `_history.json`의 retention_patterns 참조

4. **구성 재배치**: 섹션들을 최적 시청 순서로 재배열
   - Hook → 인트로/자기소개 → 본론 (관심도 순) → 마무리
   - 비선형 편집: 원본 시간순이 아닌, 시청자 관심 기반 순서

5. **편집 포인트 도출**: 각 세그먼트의 정확한 자막 범위 결정
   - 불필요한 반복, 잡담, 기술적 오류 구간 제외
   - excluded 섹션에 제외 사유 기록

## 프롬프트 템플릿

### 시스템 프롬프트

```
당신은 유튜브 영상 편집 전문가입니다.

SRT 자막 세그멘테이션 결과를 바탕으로, 시청자 이탈을 최소화하고 조회수를 극대화하는
편집 가이드를 YAML 형식으로 생성합니다.

편집 원칙:
- 첫 30초 안에 가장 인상적인 순간(Hook)을 배치
- 원본 시간순이 아닌, 시청자 관심도 기반 순서로 재배치
- 불필요한 반복, 잡담, 기술적 오류 구간은 제외
- 논리적 흐름과 내러티브 일관성 유지
- 목표 영상 길이에 맞춰 분량 조절
- 감정 아크 우선: 꿈→실행→현실→철학 순서. 정보 나열보다 감정 곡선이 먼저
- 서프라이즈 모먼트 2회 이상: 영상 중반·후반에 예상 밖 장면을 배치하여 이탈 방지
- 유통기한 짧은 콘텐츠 최소화: AI 도구 비교는 마인드셋만, 도구명 나열 지양

출력은 YAML 형식으로만. 마크다운 펜스나 설명 없이 순수 YAML만 출력하세요.
```

> **참고**: `src/veast/ai_guide_generator.py:13-24`에 현재 운영 중인 시스템 프롬프트가 있습니다.
> Python 코드의 프롬프트가 권위적 소스이며, 이 문서는 한국어 맥락을 보강한 가이드입니다.

### 입력 변수

| 변수 | 소스 | 설명 |
|------|------|------|
| `{{segmentation_result}}` | Phase 2a 출력 | 섹션 맵 (라벨, 자막 범위, 주제, 관심도 스코어) |
| `{{srt_text}}` | SRT 파일 | 전체 자막 텍스트 |
| `{{concept.md}}` | Phase 1 산출물 | 기획 의도, 질문 리스트 |
| `{{_history.insights.retention_patterns}}` | _history.json | 효과적 구성 패턴 (훅 배치 등) |
| `{{project.meta.expected_length}}` | project.json | 목표 영상 길이 |

### 사용자 메시지 구성

```
아래 세그멘테이션 결과와 자막을 바탕으로 편집 가이드를 생성해주세요.

## 세그멘테이션 결과
{{segmentation_result}}

## SRT 자막 전문
{{srt_text}}

## 기획 의도
{{concept.md}}

## 채널 데이터
- 효과적 패턴: {{_history.insights.retention_patterns}}
- 목표 영상 길이: {{project.meta.expected_length}}

## 요청 사항
아래 YAML 형식으로 편집 가이드를 생성하세요:
(editing-guide-format.md의 YAML 구조)
```

### 출력 포맷

→ `references/editing-guide-format.md` 참조 (YAML sections + sequence + excluded)

---

## Few-shot 예시

### 예시 1: 인터뷰 편집 가이드

**입력 (요약):**
- 세그멘테이션: A(인트로, 4점), B(해커톤 도전기, 9점), C(후일담, 6점), D(제품 개발, 5점)
- 목표 길이: 15분

**출력:**

```yaml
title: "홍길동 인터뷰 편집 가이드"

sections:
  A:
    subtitles: [1, 18]
    time: ["00:00:00", "00:00:33"]
    description: "인트로 + 자기소개"
  B:
    subtitles: [19, 137]
    time: ["00:00:33", "00:04:15"]
    description: "해커톤 3연패 후 우승"
  C:
    subtitles: [138, 180]
    time: ["00:04:15", "00:05:50"]
    description: "해커톤 후일담과 교훈"
  D:
    subtitles: [181, 202]
    time: ["00:05:50", "00:06:30"]
    description: "제품 개발 경험"

sequence:
  - label: "Hook"
    segments:
      - section: B
        subtitles: [69, 75]
      - section: A
        subtitles: [1, 8]
  - label: "자기소개"
    segments:
      - section: A
        subtitles: [9, 18]
  - label: "해커톤 도전기"
    segments:
      - section: B
        subtitles: [19, 68]
      - section: B
        subtitles: [76, 137]
  - label: "교훈과 조언"
    segments:
      - section: C
        subtitles: [138, 180]
  - label: "마무리"
    segments:
      - section: D
        subtitles: [181, 202]

excluded:
  - section: B
    subtitles: [100, 120]
    reason: "앞선 내용과 중복되는 반복 설명"
```

---

## CLI 연동

```bash
# AI 편집 가이드 생성
veast generate-guide --srt interview.srt --output guide.yaml

# 가이드 유효성 검사 (SRT 대비)
veast validate --guide guide.yaml --srt interview.srt

# 가이드로 영상 편집 (FFmpeg)
veast edit --video interview.mp4 --srt interview.srt --guide guide.yaml --output output.mp4

# 미리보기 (영상 처리 없이 계획만 출력)
veast edit --video interview.mp4 --srt interview.srt --guide guide.yaml --preview
```

## 관련 모듈

| 모듈 | 역할 |
|------|------|
| `src/veast/srt_parser.py` | SRT 파싱 → `list[SubtitleEntry]` |
| `src/veast/ai_guide_generator.py` | Claude API로 YAML 편집 가이드 자동 생성 |
| `src/veast/guide_parser.py` | YAML 가이드 파싱 및 유효성 검증 |
| `src/veast/orchestrator.py` | 파이프라인 조율 (resolve_plan → execute_plan) |
| `src/veast/video_processor.py` | FFmpeg 래퍼 (cut_segment, concat_segments) |
| `src/veast/models.py` | 데이터 모델 (EditGuide, EditPlan, EditSegment 등) |

## YAML 편집 가이드 구조

편집 가이드의 세 가지 섹션:

1. **sections**: 원본 영상을 주제 단위로 구획
   - 키: 섹션 라벨 (A, B, C, ...)
   - 값: 자막 범위, 타임코드 범위, 주제 설명

2. **sequence**: 최종 영상의 재배치 순서
   - 각 항목: 라벨 + segments (섹션 참조 + 자막 범위)
   - 한 섹션에서 일부만 사용하거나 분할 가능

3. **excluded**: 사용하지 않는 구간
   - 제외 사유 명시 (중복, 잡담, 기술 오류 등)

→ 포맷 상세: `references/editing-guide-format.md`

## edit-guide.md 출력 형식

최종 산출물은 DaVinci Resolve에서 바로 참조 가능한 마크다운 테이블:

```markdown
# 편집 가이드: 스미스 인터뷰

## 편집 순서

| # | 라벨 | 시작 타임코드 | 종료 타임코드 | 자막 범위 | 설명 |
|---|------|-------------|-------------|----------|------|
| 1 | Hook | 00:02:15.000 | 00:02:45.000 | #69-75 | 해커톤 우승 비결 (가장 인상적) |
| 2 | 인트로 | 00:00:00.000 | 00:00:15.000 | #1-8 | 채널 인트로 |
| 3 | 자기소개 | 00:00:15.000 | 00:00:33.000 | #9-18 | 스미스 소개 |
| 4 | 본론 1 | 00:00:33.000 | 00:02:15.000 | #19-68 | 해커톤 도전기 |
| 5 | 본론 2 | 00:02:45.000 | 00:04:15.000 | #76-137 | 해커톤 후일담 |
| 6 | 마무리 | 00:04:15.000 | 00:06:30.000 | #138-202 | 제품 개발 경험 |

## 제외 구간

| 자막 범위 | 사유 |
|----------|------|
| #100-120 | 중복 내용 |

## 예상 최종 길이: 5분 48초
```

## 유효성 검증 체크리스트

편집 가이드 생성 후 반드시 확인:

1. 모든 자막 인덱스가 SRT에 존재하는가
2. 자막 범위가 유효한가 (시작 ≤ 종료)
3. sequence의 모든 segment가 sections에 정의된 섹션을 참조하는가
4. segment의 자막 범위가 섹션의 자막 범위를 초과하지 않는가
5. `veast validate` 결과가 에러 없는가
