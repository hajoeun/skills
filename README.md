# skills

Claude Code skills for video analysis and editing.

## Skills

| Skill | Description |
|-------|-------------|
| [video-debug](#video-debug) | Debug mobile app issues from screen recordings |
| [video-editor](#video-editor) | SRT-based video cut editing with FFmpeg |

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

**video-editor** additionally requires Python 3.

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

## License

MIT
