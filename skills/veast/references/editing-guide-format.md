# YAML 편집 가이드 포맷 레퍼런스

## 전체 구조

```yaml
title: "프로젝트 제목"

sections:
  <라벨>:
    subtitles: [시작_인덱스, 종료_인덱스]
    time: ["HH:MM:SS", "HH:MM:SS"]
    description: "주제 설명"

sequence:
  - label: "편집 순서 라벨"
    segments:
      - section: <섹션_라벨>
        subtitles: [시작_인덱스, 종료_인덱스]

excluded:
  - section: <섹션_라벨>
    subtitles: [시작_인덱스, 종료_인덱스]
    reason: "제외 사유"
```

## 필드 상세

### sections (필수)

원본 영상을 주제 단위로 구획하는 맵.

| 필드 | 타입 | 설명 |
|------|------|------|
| `<라벨>` | string | 섹션 식별자 (A, B, C, ...) |
| `subtitles` | [int, int] | SRT 자막 인덱스 범위 (1-based, 양 끝 포함) |
| `time` | [string, string] | 타임코드 범위 ("HH:MM:SS" 또는 "HH:MM:SS.mmm") |
| `description` | string | 이 구간의 주제 요약 |

### sequence (필수)

최종 영상의 편집 순서를 정의하는 배열.

| 필드 | 타입 | 설명 |
|------|------|------|
| `label` | string | 편집 블록 이름 (Hook, 인트로, 본론, 마무리 등) |
| `segments` | array | 이 블록에 포함할 세그먼트 목록 |
| `segments[].section` | string | 참조할 섹션 라벨 (sections에 정의된 것) |
| `segments[].subtitles` | [int, int] | 이 세그먼트에서 사용할 자막 범위 |

한 sequence 항목에 여러 segment를 넣으면 순서대로 이어붙인다.
한 섹션에서 일부만 사용하거나, 같은 섹션을 여러 곳에서 참조할 수 있다.

### excluded (선택)

사용하지 않는 구간을 명시적으로 기록한다.

| 필드 | 타입 | 설명 |
|------|------|------|
| `section` | string | 참조할 섹션 라벨 |
| `subtitles` | [int, int] | 제외할 자막 범위 |
| `reason` | string | 제외 사유 (중복, 잡담, 기술 오류 등) |

## 검증 규칙

1. 모든 `subtitles` 인덱스는 SRT 파일에 존재해야 한다
2. 자막 범위의 시작 ≤ 종료
3. sequence의 segment가 참조하는 section은 sections에 정의되어 있어야 한다
4. segment의 자막 범위는 해당 section의 자막 범위를 초과할 수 없다

검증 CLI: `veast validate --guide <guide.yaml> --srt <file.srt>`

## 예시

```yaml
title: "스미스 인터뷰 편집 가이드"

sections:
  A:
    subtitles: [1, 18]
    time: ["00:00:00", "00:00:33"]
    description: "인트로 + 자기소개"
  B:
    subtitles: [19, 137]
    time: ["00:00:33", "00:04:15"]
    description: "해커톤 1등 이야기"
  C:
    subtitles: [138, 202]
    time: ["00:04:15", "00:06:30"]
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
  - label: "본론"
    segments:
      - section: B
        subtitles: [19, 68]
      - section: B
        subtitles: [76, 137]
  - label: "마무리"
    segments:
      - section: C
        subtitles: [138, 202]

excluded:
  - section: B
    subtitles: [100, 120]
    reason: "중복 내용, 삭제"
```
