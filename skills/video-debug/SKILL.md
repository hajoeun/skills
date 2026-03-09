---
name: video-debug
description: >
  Analyzes device screen recordings (.mp4, .mov, .webm) to debug mobile app issues.
  Use when the user provides a video file and asks to fix a bug, review UI behavior,
  or analyze what's happening on screen. Also use when someone shares a screen recording
  from QA, a tester's bug report video, a screen capture of unexpected behavior, asks
  you to look at a recording to find what went wrong, or says they have a screen recording
  but have not pasted the file path yet. Extracts key frames via FFmpeg, analyzes them
  visually, can help locate a recent video file when needed, and connects findings to
  the project codebase.
---

# Video Debug

Debug mobile app issues by analyzing device screen recordings. Share a video file
(.mp4, .mov, .webm) and describe the problem — this pipeline extracts key frames,
analyzes what happened on screen, traces the issue to source code, and applies a fix.

You can provide a video file path directly, or just describe the problem and the skill
can help locate a recent video file from your Downloads, Desktop, and current directory
before continuing.

FFmpeg is required for frame extraction. If not installed, Step 1 provides setup instructions.

## Pipeline

Follow these steps in order. Step 2 has built-in shortcuts — read the decision tree before
extracting frames, since you may be able to skip the overview pass.

### Step 0: Locate video file

If the user already provided a video file path in their message, use that path as `{video_path}`
and skip to Step 1.

If no video path was provided, help the user find their video:

1. **Ask before searching**

   Say:

   "I can search your Downloads, Desktop, and current directory for recent video files.
   Want me to look there, or would you rather paste the path directly?"

   Only run the search if the user agrees. If they prefer to paste the path, wait for it
   and skip to Step 1.

2. **Search common directories for recent videos**

   ```bash
   find ~/Downloads ~/Desktop . -maxdepth 2 -type f \( -iname "*.mp4" -o -iname "*.mov" -o -iname "*.webm" \) -mtime -1 -exec ls -t {} + 2>/dev/null | head -20
   ```

   If no results within the last 24 hours, widen to 7 days:

   ```bash
   find ~/Downloads ~/Desktop . -maxdepth 2 -type f \( -iname "*.mp4" -o -iname "*.mov" -o -iname "*.webm" \) -mtime -7 -exec ls -t {} + 2>/dev/null | head -20
   ```

3. **Present results to the user**

   If videos were found, show the results in the order returned by the command above
   (already newest first) and present a numbered list:

   "Found these recent video files:
   1. ~/Downloads/screen-recording-2026-03-09.mov (2 minutes ago)
   2. ~/Downloads/bug-demo.mp4 (3 hours ago)
   3. ~/Desktop/app-crash.webm (yesterday)

   Which one should I analyze? Enter a number, or paste a different file path."

4. **If no videos found**

   "No recent video files found in Downloads, Desktop, or the current directory.

   Paste the video file path here. Tip: you can drag a file from Finder into this terminal
   to paste its path automatically."

5. Set `{video_path}` to the chosen or provided path and continue to Step 1.

### Step 1: Validate environment

Before extracting frames, confirm the tools and input are ready.

1. **Check FFmpeg is installed**

   ```bash
   which ffmpeg && which ffprobe
   ```

   If either is not found, show installation instructions for the user's OS:
   - macOS: `brew install ffmpeg`
   - Ubuntu/Debian: `sudo apt install ffmpeg`
   - Windows: `winget install FFmpeg`

   Wait until FFmpeg is available before continuing.

2. **Inspect video metadata**

   ```bash
   ffprobe -v quiet -print_format json -show_format -show_streams "{video_path}"
   ```

   From the JSON output, note these three values (ignore the rest to save context):
   - `format.duration` — total length in seconds
   - `streams[0].codec_name` — video codec (h264, hevc, vp9, etc.)
   - `streams[0].width` and `streams[0].height` — resolution

3. **Verify supported format**

   Accepted extensions: `.mp4`, `.mov`, `.webm`.
   If the file has a different extension, tell the user which formats are supported and stop.

4. **Check duration**

   If the video is longer than 5 minutes (300 seconds), warn the user:
   "This video is {duration}s. Videos under 5 minutes work best — longer recordings
   produce many frames and increase analysis time. Consider trimming to the relevant section."
   Proceed if the user confirms, but expect higher token usage.

### Step 2: Extract and narrow

Find the bug by progressively narrowing down — start with a broad overview, then zoom into
the problem area at higher frame rates. This avoids wasting tokens on irrelevant frames and
catches subtle bugs (like a 50ms header bounce) that a single fixed-rate extraction would miss.

Before extracting anything, check what the user said when they shared the video. If their
message already describes the problem with enough detail to act on — a specific moment,
a screen transition, a UI element misbehaving — skip Pass 1 and go straight to targeted
extraction. The decision tree:

- **"Check this video" / "이 영상 봐줘"** (no context) → Pass 1. You need the overview to
  understand what's in the video.
- **"The header flickers when the keyboard comes up" / "키보드 올라올 때 헤더가 깜빡여"**
  (symptom described) → Pass 1, but focus your summary on keyboard/header transitions so
  you can quickly identify the right time range for Pass 2.
- **"Layout breaks during the screen transition around 3s" / "3초쯤에 화면 전환할 때 레이아웃이 깨져"**
  (timing + symptom) → Skip Pass 1. Go directly to Pass 2 targeting 2.5s–4s.

When skipping Pass 1, still extract 2-3 overview frames (first, middle, last) to confirm
you're looking at the right screen before spending tokens on the zoom-in pass.

#### Pass 1: Overview

Get a bird's-eye view of the entire video. The goal is ~10-15 frames that summarize what
happens across the full timeline. Present these to the user so they can point to the problem area.

1. **Clear and create temp directory**

   ```bash
   rm -rf /tmp/video-debug && mkdir -p /tmp/video-debug/pass1
   ```

   Starting fresh prevents leftover frames from a previous run from mixing with new results.

2. **Extract overview frames**

   Choose frame rate based on duration to keep the overview at ~10-15 frames:

   | Duration | Strategy | Rationale |
   |----------|----------|-----------|
   | Under 3s | 5 fps | Very short clip — 5fps gives 10-15 frames covering every moment |
   | 3s – 30s | 1 fps | One frame per second provides a clear timeline |
   | 30s – 120s | 0.5 fps | One frame every 2 seconds keeps count manageable |
   | Over 120s | scene detection (0.3) | Let FFmpeg pick the transitions |

   ```bash
   # Under 3s:
   ffmpeg -i "{video_path}" -vf "fps=5" /tmp/video-debug/pass1/frame_%03d.png
   # 3s – 30s:
   ffmpeg -i "{video_path}" -vf "fps=1" /tmp/video-debug/pass1/frame_%03d.png
   # 30s – 120s:
   ffmpeg -i "{video_path}" -vf "fps=1/2" /tmp/video-debug/pass1/frame_%03d.png
   # Over 120s:
   ffmpeg -i "{video_path}" -vf "select='gt(scene,0.3)'" -vsync vfr /tmp/video-debug/pass1/frame_%03d.png
   ```

3. **Always capture first and last frames**

   ```bash
   ffmpeg -i "{video_path}" -vframes 1 /tmp/video-debug/pass1/frame_first.png
   ffmpeg -sseof -0.1 -i "{video_path}" -vframes 1 /tmp/video-debug/pass1/frame_last.png
   ```

4. **Handle edge cases**

   If scene detection produced no frames (common with mostly-static recordings), fall back
   to 0.5 fps:

   ```bash
   ffmpeg -i "{video_path}" -vf "fps=1/2" /tmp/video-debug/pass1/frame_%03d.png
   ```

   If any strategy produced more than 20 frames, keep every Nth frame to get down to ~15.
   The overview is just for orientation — spending too many tokens here defeats the purpose
   of the progressive approach.

5. **Present the timeline to the user**

   Read all overview frames and summarize each in one line with its timestamp:

   "Here's what happens across the {duration}s video:
   - 0s: Login screen with email field focused
   - 1s: User taps submit, loading spinner appears
   - 2s: Spinner still active
   - 3s: Error toast appears briefly
   - 4s: Screen returns to login, fields cleared
   ...
   Which part shows the problem? I'll zoom in on that section."

   Wait for the user to identify the problem area before continuing.

#### Pass 2: Zoom in

Once the user identifies a time range (e.g., "the transition around 3-4 seconds"), extract
that specific section at a higher frame rate to catch the details.

1. **Create pass 2 directory**

   ```bash
   mkdir -p /tmp/video-debug/pass2
   ```

2. **Extract the target range at 10 fps**

   Use `-ss` (start time) and `-t` (duration) to target just the problem area.
   Add 0.5s padding on each side to capture the lead-in and aftermath.

   ```bash
   # Example: user says "around 3-4 seconds" → extract 2.5s to 4.5s at 10fps
   ffmpeg -ss 2.5 -i "{video_path}" -t 2.0 -vf "fps=10" /tmp/video-debug/pass2/frame_%03d.png
   ```

   10 fps at 2 seconds = ~20 frames. This gives 100ms resolution — enough to catch most
   UI transitions, layout shifts, and animation glitches.

3. **Analyze the zoomed frames**

   Read all pass 2 frames and describe what's happening at each step. Focus on the visual
   changes the user called out. Common patterns to look for:
   - **Layout shift**: content jumps position between frames
   - **Overlap/z-index**: elements stacking on top of each other (headers, modals, keyboards)
   - **White flash**: screen goes blank during transitions (component unmount/remount)
   - **Frozen state**: identical frames where animation or loading should be progressing
   - **Clipping**: content cut off at screen edges or behind other elements

   Report findings with timestamps:

   "Zoomed into 2.5s–4.5s at 10fps (20 frames):
   - 2.5s: Header visible, normal state
   - 2.8s: Keyboard appearing, content shifts up
   - 2.9s: Header starts sliding out of view
   - 3.0s: Header hidden — layout overlap detected
   - 3.1s: Header snaps back into position
   Found it: header bounces at 2.9-3.1s during keyboard transition."

#### Pass 3: Fine detail (if needed)

If the bug is a fast glitch (a 50ms header bounce, a single-frame layout overlap, a flash
of misplaced content), pass 2 at 10fps might still miss it. When the user says the issue
isn't clearly visible in pass 2, or when you see signs of a transition but can't pinpoint
the exact frame:

1. **Narrow further and increase fps to 20**

   ```bash
   mkdir -p /tmp/video-debug/pass3
   # Example: narrow from 2.8s-3.2s at 20fps
   ffmpeg -ss 2.8 -i "{video_path}" -t 0.4 -vf "fps=20" /tmp/video-debug/pass3/frame_%03d.png
   ```

   20 fps on a 0.4s window = ~8 frames at 50ms resolution. This catches even single-frame
   glitches like layout thrashing, z-index flicker, or animation jank.

2. **Report the exact bug frame**

   At this resolution, you should be able to identify the exact moment and describe
   what went wrong visually.

#### Short video shortcut

For videos under 3 seconds, the overview (pass 1 at 5fps) already provides enough detail
to spot most issues. If the user's description matches what you see in pass 1, skip
straight to analysis without a separate zoom-in pass. If something subtle is happening
(e.g., a quick flash or bounce the user mentioned but you don't see), go directly to
pass 2 on the full video at 10-20fps — the frame count will still be manageable.
