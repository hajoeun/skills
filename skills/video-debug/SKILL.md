---
name: video-debug
description: >
  Analyzes device screen recordings (.mp4, .mov, .webm) to debug mobile app issues.
  Use when the user provides a video file and asks to fix a bug, review UI behavior,
  or analyze what's happening on screen. Also use when someone shares a screen recording
  from QA, a tester's bug report video, a screen capture of unexpected behavior, or asks
  you to look at a recording to find what went wrong. Extracts key frames via FFmpeg,
  analyzes them visually, and connects findings to the project codebase.
---

# Video Debug

Debug mobile app issues by analyzing device screen recordings. Drop a video file
(.mp4, .mov, .webm) and describe the problem — this pipeline extracts key frames,
analyzes what happened on screen, traces the issue to source code, and applies a fix.

FFmpeg is required for frame extraction. If not installed, Step 1 provides setup instructions.

## Pipeline

Follow these steps in order. Do not skip steps.

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

### Step 2: Extract key frames

Extract representative frames that capture each distinct screen state in the video.

1. **Clear and create temp directory**

   ```bash
   rm -rf /tmp/video-debug && mkdir -p /tmp/video-debug
   ```

   Starting fresh prevents leftover frames from a previous run from mixing with new results.

2. **Extract scene-change frames**

   ```bash
   ffmpeg -i "{video_path}" -vf "select='gt(scene,0.3)'" -vsync vfr /tmp/video-debug/frame_%03d.png
   ```

   This writes one PNG per visual scene change. The threshold (0.3) controls sensitivity:
   - `0.5` — stricter, fewer frames. Good when the video has many gradual transitions
     and you are getting too many similar frames.
   - `0.3` — default. Works well for most mobile screen recordings.
   - `0.2` — looser, more frames. Use when subtle changes (toast messages, loading spinners)
     are being missed.

3. **Extract first and last frames**

   Scene detection can miss the boundaries if there is no visual transition at the start or end.
   Always capture these separately to establish the starting and ending state.

   ```bash
   ffmpeg -i "{video_path}" -vframes 1 /tmp/video-debug/frame_first.png
   ffmpeg -sseof -1 -i "{video_path}" -vframes 1 /tmp/video-debug/frame_last.png
   ```

4. **Handle zero frames from scene detection**

   If scene detection produced no frames (common with mostly-static recordings), fall back to
   extracting one frame every 2 seconds:

   ```bash
   ffmpeg -i "{video_path}" -vf "fps=1/2" /tmp/video-debug/frame_%03d.png
   ```

5. **Limit frame count**

   ```bash
   ls /tmp/video-debug/frame_*.png | wc -l
   ```

   If there are more than 20 frames (excluding first/last): re-run with a higher threshold
   (try 0.5). If still too many, keep every Nth frame to get down to ~15-20.

   Each frame consumes vision tokens during analysis. Beyond 20 frames, cost increases
   without proportional insight. The first/last frames plus 15-18 scene-change frames are
   enough to reconstruct most mobile app interactions.

6. **Report results**

   Tell the user what was extracted before moving to analysis:
   "Extracted {N} key frames from {duration}s video (scene threshold: {threshold}). Analyzing now."
