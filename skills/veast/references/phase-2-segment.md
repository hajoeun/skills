# Phase 2a: SRT 세그멘테이션

## 개요

SRT 자막 전문을 분석하여 주제 단위로 섹션을 나누고, 각 섹션의 시청자 관심도를 예측한다. 이 결과가 Phase 2b(편집 가이드 생성)의 입력이 된다.

## 워크플로우

1. SRT 전문을 시간순으로 읽으며 주제 전환 지점을 탐지
2. 각 섹션에 라벨(A, B, C, ...) 부여
3. 섹션별 관심도 스코어(1~10) 산출
4. 훅(Hook) 후보 구간 표시

---

## 프롬프트 템플릿

### 시스템 프롬프트

```
당신은 유튜브 영상 콘텐츠 분석 전문가입니다.

인터뷰/대화 형식의 SRT 자막을 읽고, 주제 단위로 정확하게 세분화합니다.
각 섹션의 시청자 관심도를 예측하여 편집 우선순위를 결정하는 데 필요한 데이터를 제공합니다.

관심도 스코어 기준 (1~10):
- 갈등/긴장감이 있는 구간: +3
- 구체적 사례나 숫자가 포함된 구간: +2
- 감정적 순간 (웃음, 놀람, 진지한 고백): +2
- 의외성/반전이 있는 구간: +2
- 실용적 정보/팁이 포함된 구간: +1
- 일반적 잡담/인사: 기본 3점

주제 전환 판단 기준:
- 대화 주제가 명확히 바뀌는 지점
- "그런데", "다른 얘기인데", "그때" 같은 전환 표현
- 질문자가 새로운 질문을 시작하는 지점
```

### 입력 변수

| 변수 | 소스 | 설명 |
|------|------|------|
| `{{srt_text}}` | SRT 파일 | 전체 자막 텍스트 (`#인덱스 [시작 --> 종료] 텍스트` 형식) |
| `{{project.meta.expected_length}}` | project.json | 목표 영상 길이 (세그멘테이션 세밀도 조절용) |
| `{{project.type}}` | project.json | 프로젝트 유형 (인터뷰/브이로그 등) |

### 사용자 메시지 구성

```
다음 SRT 자막을 주제 단위로 세그멘테이션해주세요.

프로젝트 유형: {{project.type}}
목표 영상 길이: {{project.meta.expected_length}}

## SRT 자막 전문

{{srt_text}}

## 요청 사항

1. 주제가 전환되는 지점을 기준으로 섹션(A, B, C, ...)을 나누세요.
2. 각 섹션에 관심도 스코어(1~10)를 부여하세요.
3. 관심도가 가장 높은 섹션을 훅(Hook) 후보로 표시하세요.
4. 아래 형식으로 출력하세요.
```

### 출력 포맷

```yaml
segments:
  A:
    subtitles: [1, 18]
    time: ["00:00:00", "00:00:33"]
    topic: "인트로 + 자기소개"
    interest_score: 4
    hook_candidate: false
    notes: "기본 인사와 소개, 편집 시 축약 가능"
  B:
    subtitles: [19, 75]
    time: ["00:00:33", "00:02:45"]
    topic: "해커톤 도전기 — 3번 실패 후 1등"
    interest_score: 9
    hook_candidate: true
    notes: "갈등+구체적 숫자+반전. 자막 #69-75가 클라이맥스"
  C:
    subtitles: [76, 137]
    time: ["00:02:45", "00:04:15"]
    topic: "해커톤 후일담과 교훈"
    interest_score: 6
    hook_candidate: false
    notes: "실용적 정보 포함, 본론으로 적합"
```

---

## Few-shot 예시

### 예시 1: 스타트업 CTO 인터뷰

**입력 (요약):**
- 프로젝트 유형: 인터뷰
- 목표 영상 길이: 15 minutes
- SRT: 202개 자막, 총 25분 분량

**출력:**

```yaml
segments:
  A:
    subtitles: [1, 18]
    time: ["00:00:00", "00:00:33"]
    topic: "인트로 + 자기소개"
    interest_score: 4
    hook_candidate: false
    notes: "기본 인사와 배경 소개"
  B:
    subtitles: [19, 75]
    time: ["00:00:33", "00:02:45"]
    topic: "해커톤 3연패 후 우승 비결"
    interest_score: 9
    hook_candidate: true
    notes: "갈등+반전+구체적 숫자. #69-75가 가장 인상적 (우승 순간 회고)"
  C:
    subtitles: [76, 120]
    time: ["00:02:45", "00:03:50"]
    topic: "팀 빌딩과 역할 분담"
    interest_score: 6
    hook_candidate: false
    notes: "실용적 팁 포함"
  D:
    subtitles: [121, 160]
    time: ["00:03:50", "00:05:10"]
    topic: "제품 출시 실패와 피봇"
    interest_score: 8
    hook_candidate: true
    notes: "실패 스토리+감정적 순간. 2순위 훅 후보"
  E:
    subtitles: [161, 185]
    time: ["00:05:10", "00:06:00"]
    topic: "현재 회사 성장기"
    interest_score: 5
    hook_candidate: false
    notes: "비교적 평이한 성과 나열"
  F:
    subtitles: [186, 202]
    time: ["00:06:00", "00:06:30"]
    topic: "시청자에게 전하는 조언"
    interest_score: 7
    hook_candidate: false
    notes: "마무리로 적합, 감정적 마무리 가능"
```

---

## 완료 조건

- 세그멘테이션 결과가 YAML 형식으로 생성됨
- 모든 자막 인덱스가 빠짐없이 커버됨
- 관심도 스코어가 1~10 범위
- 최소 1개 이상의 hook_candidate 존재
- 결과를 Phase 2b(편집 가이드 생성)에 전달
