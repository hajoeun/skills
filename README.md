# video-debug

Debug mobile app issues from screen recordings. Drop a video and describe the problem — Claude extracts key frames via FFmpeg, visually analyzes what happened, and traces the issue back to your code.

Instead of scrubbing through a video yourself and describing what you see, hand the recording directly to Claude. The skill progressively narrows down: it starts with a low-fps overview of the full video, you point to the problem area, and it zooms in at higher frame rates until it catches the exact bug frame — even glitches as brief as 50ms.

## Install

```bash
npx skills add hajoeun/skills --skill video-debug
```

**Requires [FFmpeg](https://ffmpeg.org/)** for frame extraction:

```bash
# macOS
brew install ffmpeg

# Ubuntu/Debian
sudo apt install ffmpeg

# Windows
winget install FFmpeg
```

## Quick start

1. Record the bug on your device (iOS screen recording, Android screencast, etc.)
2. Drop the `.mp4`, `.mov`, or `.webm` file into the conversation
3. Describe what's wrong — or just say "check this video" and let Claude ask

```
You:    [attaches recording.mov] The header flickers when the keyboard comes up
Claude: Zoomed into 0.8s–1.2s at 10fps (4 frames):
        - 0.9s: Keyboard rising, header in normal position
        - 1.0s: Header pushed above screen — layout overlap
        - 1.05s: Header snaps back into place
        Found it: header bounces for ~50ms during keyboard transition.
```

## How it works

The skill uses a **progressive narrowing** approach rather than extracting all frames at once:

```
Pass 1: Overview (1 fps)     → "Here's what happens in the video"
         ↓ you point to the problem area
Pass 2: Zoom in (10 fps)     → "Found a layout shift at 3.0s"
         ↓ need more detail?
Pass 3: Fine detail (20 fps) → "Header overlaps content for exactly 50ms at 2.95s"
```

If you already describe the problem when sharing the video, the skill skips the overview and jumps straight to targeted extraction — saving time and tokens.

### What it catches

- **Layout shifts** — content jumping position during transitions
- **Overlap / z-index issues** — headers, modals, or keyboards stacking incorrectly
- **White flashes** — blank screens during navigation (component unmount/remount)
- **Frozen states** — spinners or loading indicators that never resolve
- **Animation jank** — dropped frames, stuttering, or snapping during transitions
- **Clipping** — content cut off at edges or hidden behind other elements

## Customization

After installing, add a **Project context** section to the SKILL.md to help Claude navigate your codebase:

**React Native**
```markdown
## Project context
- Framework: React Native 0.76
- Screens: src/screens/
- Components: src/components/
- Navigation: React Navigation (Stack + Bottom Tab)
- State: Zustand (src/stores/)
```

**Flutter**
```markdown
## Project context
- Framework: Flutter 3.x
- Screens: lib/screens/
- Widgets: lib/widgets/
- Navigation: GoRouter
- State: Riverpod (lib/providers/)
```

**SwiftUI**
```markdown
## Project context
- Framework: SwiftUI (iOS 17+)
- Views: Sources/Views/
- ViewModels: Sources/ViewModels/
- Navigation: NavigationStack
- State: @Observable classes
```

## Limitations

- **Video length**: Works best under 5 minutes. Longer recordings increase analysis time and token usage — trim to the relevant section if possible.
- **Supported formats**: `.mp4`, `.mov`, `.webm` only.
- **Static content bugs**: CSS/layout issues visible in a single screenshot are better debugged with a screenshot, not a video. This skill is for bugs that involve *motion* — transitions, animations, timing.
- **Token cost**: Each extracted frame consumes vision tokens. The progressive approach minimizes this, but long videos with many passes will use more tokens.

## License

MIT
