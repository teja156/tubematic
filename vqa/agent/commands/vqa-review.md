Run an on-demand Gemini quality review of an already-rendered VQA video.

User's input: $ARGUMENTS (a video_id, e.g. vid_abc123def456)

If $ARGUMENTS is empty, ask: "Which video_id would you like reviewed?" (use /tubematic-status or
tubematic:list_videos(status="VIDEO_READY") to help the user find it if needed).

This is separate from the automatic review the render worker can run — this environment seeds
`gemini_review_enabled=false`, so review only happens when explicitly requested here. Unlike the
automatic path, this makes no DB writes: it doesn't touch `gemini_feedback`, `ai_review_count`, or
the video's status, so it can be re-run on the same video any number of times.

Warn the user this can take several minutes (worst case ~7, due to Gemini's upload processing
poll), then run:

  /opt/tubematic/.venv/bin/python "$(ls -d ~/tubematic 2>/dev/null || echo /opt/tubematic)"/vqa/review_video.py $ARGUMENTS

Show the command's output directly — it's already formatted markdown (overall critique, must-fix
findings with scene/timestamp, and suggestions). The command also writes this same feedback to
`~/.tubematic-data/jobs/<video_id>/ai_review.txt` (overwritten on each re-run) and prints that
path as its last line — **state that path explicitly once the review is shown**, so the user can
reopen it later without re-running the review. If it exits with an error (unrendered video,
unknown video_id, missing files on disk), relay the error message as-is; it already names the
specific problem.
