# skills

Claude Code skills for video analysis and editing.

## Skills

| Skill | Description |
|-------|-------------|
| [video-debug](#video-debug) | Debug mobile app issues from screen recordings |
| [video-editor](#video-editor) | SRT-based video cut editing with FFmpeg |
| [veast](#veast) | YouTube video production 6-phase pipeline |

## Prerequisites

Both skills require [FFmpeg](https://ffmpeg.org/):

```bash
# macOS
brew install ffmpeg

# Ubuntu/Debian
sudo apt install ffmpeg

# Windows
winget install FFmpeg
```

**video-editor** and **veast** additionally require Python 3.

## video-debug

Debug mobile app issues from screen recordings. Drop a video and describe the problem — Claude extracts key frames via FFmpeg, analyzes what happened, and traces the issue back to your code.

### Install

```bash
npx skills add hajoeun/skills --skill video-debug
```

### Quick start

1. Record the bug on your device (iOS screen recording, Android screencast, etc.)
2. Drop the `.mp4`, `.mov`, or `.webm` file into the conversation
3. Describe what's wrong — or just say "check this video"

```
You:    [attaches recording.mov] The header flickers when the keyboard comes up
Claude: Zoomed into 0.8s–1.2s at 10fps (4 frames):
        - 0.9s: Keyboard rising, header in normal position
        - 1.0s: Header pushed above screen — layout overlap
        - 1.05s: Header snaps back into place
        Found it: header bounces for ~50ms during keyboard transition.
```

The skill uses **progressive narrowing** — overview at 1 fps, zoom in at 10 fps, fine detail at 20 fps. It catches layout shifts, overlap issues, white flashes, frozen states, animation jank, and clipping.

See [SKILL.md](skills/video-debug/SKILL.md) for the full pipeline and customization options.

## video-editor

Rearrange video segments based on SRT subtitle timestamps. Provide a video file, an SRT subtitle file, and an editing guide document — Claude parses the subtitles, builds a cut-by-cut edit plan from your guide, and executes it via FFmpeg.

### Install

```bash
npx skills add hajoeun/skills --skill video-editor
```

### Quick start

1. Prepare three files:
   - Video file (`.mp4`, `.mov`, `.mkv`)
   - SRT subtitle file
   - Editing guide document (`.md` or `.txt`) — see [format reference](skills/video-editor/references/editing_guide_format.md)
2. Provide all three file paths to Claude
3. Claude parses the SRT, builds an edit plan from your guide, shows it for confirmation, then executes the cuts

### How it works

```
SRT file  ──→  parse_srt.py  ──→  JSON timestamps
                                        │
Guide doc ──→  Claude builds  ◄─────────┘
               edit plan
                  │
            User confirms
                  │
              execute_edit.py  ──→  FFmpeg cuts + concat  ──→  Final video
```

The editing guide specifies which subtitle ranges to include, exclude, or compress, and in what order. Claude converts subtitle numbers to timestamps and assembles the segments into a single output file.

See [SKILL.md](skills/video-editor/SKILL.md) for the full pipeline, security details, and script documentation.

## veast

YouTube video production 6-phase pipeline — from concept planning to performance analysis. Manages concept, SRT segmentation, edit guide generation, title/thumbnail packaging, upload kit, and YouTube Analytics review as a single context.

### Install

```bash
npx skills add hajoeun/skills --skill veast
```

### Prerequisites (optional, per phase)

```bash
# Phase 3 (video editing) — YAML guide parsing
pip install pyyaml

# Phase 6 (YouTube Analytics collection)
pip install google-api-python-client google-auth google-auth-oauthlib
```

### Quick start

```
You:    /video new
Claude: PD 에이전트 모드로 전환합니다. 어떤 유형의 영상인가요?
        (인터뷰, 브이로그, 팟캐스트, 탐방로그, 숏폼)
You:    인터뷰, 게스트는 홍길동
Claude: [5단계 대화형 세션 → concept.md 생성]
```

### 6-phase pipeline

1. **Concept** (`/video new`) — PD agent interactive session → `concept.md`
2. **Edit Guide** (`/video transcript`, `/video edit-guide`) — SRT segmentation + AI edit guide → `edit-guide.yaml`
3. **Editing** (`/video edit`) — Manual (DaVinci Resolve) or auto (FFmpeg)
4. **Packaging** (`/video package`) — Title candidates + thumbnail direction → `packaging.md`
5. **Upload Kit** (`/video timestamp`) — Timestamps + description → `upload-kit.md`
6. **Analysis** (`/video analyze`) — YouTube Analytics + feedback loop → `review.md`

See [SKILL.md](skills/veast/SKILL.md) for the full pipeline and reference map.

## License

MIT
