"use client";

import { useEffect, useRef, useState } from "react";
import { videoToStreamUrl } from "@/lib/utils";

// On-demand, cached voice preview (TMDEV-51 follow-up). First click POSTs
// /voices/<id>/preview (generates + caches server-side, or replays an
// existing cache); later clicks just toggle play/pause on the already-loaded
// <audio> element — no second request. Deliberately not auto-generated on
// settings save, which would couple an unrelated DB write to a paid, slow,
// fallible ElevenLabs call.
//
// The sample is spoken with the voice's own model (TMDEV-121). modelId, when
// given, names the model to preview instead — the Settings page passes the
// row's current pick so an unsaved model change can be heard before saving.
// The server keys its cache on the model, so a changed model is a fresh
// sample on the next play.

type PreviewState = "idle" | "loading" | "ready" | "playing" | "error";

export function VoicePreviewButton({
  voiceId,
  modelId,
  disabled,
  style,
}: {
  voiceId: string;
  modelId?: string;
  disabled?: boolean;
  style?: React.CSSProperties;
}) {
  const [state, setState] = useState<PreviewState>("idle");
  const [url, setUrl] = useState<string | null>(null);
  const [error, setError] = useState("");
  const audioRef = useRef<HTMLAudioElement | null>(null);
  // Bumped whenever the voice or model changes, so a slow response for the
  // previous pick is dropped instead of playing the wrong sample.
  const requestRef = useRef(0);

  function play(audio: HTMLAudioElement) {
    // play() rejects when the browser blocks autoplay; the button then stays
    // on ▶ for a manual click rather than claiming to be playing.
    audio.play()?.catch?.(() => setState("ready"));
  }

  useEffect(() => {
    if (url && audioRef.current) play(audioRef.current);
  }, [url]);

  // ActionPane/VideoModal pass the currently *selected* voice_id, and the
  // Settings page the row's current model, both of which change as the human
  // works the dropdowns — without this reset, a cached url/state from a
  // previous pick would make the next click replay the wrong audio.
  useEffect(() => {
    requestRef.current += 1;
    audioRef.current?.pause();
    setUrl(null);
    setState("idle");
  }, [voiceId, modelId]);

  const isDisabled = disabled || !voiceId || state === "loading";

  async function handleClick() {
    if (isDisabled) return;

    if (url) {
      const audio = audioRef.current;
      if (!audio) return;
      if (audio.paused) play(audio);
      else audio.pause();
      return;
    }

    const request = ++requestRef.current;
    setState("loading");
    setError("");
    try {
      const r = await fetch(`/api/proxy/voices/${encodeURIComponent(voiceId)}/preview`, {
        method: "POST",
        // The proxy refuses a body without a JSON Content-Type (TMDEV-156).
        ...(modelId ? {
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ model_id: modelId }),
        } : {}),
      });
      const data = await r.json();
      if (request !== requestRef.current) return;
      if (!r.ok) throw new Error(data.error || "Preview failed");
      setUrl(videoToStreamUrl(data.path));
      setState("ready");
    } catch (e) {
      if (request !== requestRef.current) return;
      setState("error");
      setError(e instanceof Error ? e.message : "Preview failed");
    }
  }

  const label =
    state === "loading" ? "…"
    : state === "error" ? "!"
    : state === "playing" ? "❚❚"
    : "▶";
  const title =
    state === "error" ? error
    : state === "playing" ? "Pause the preview"
    : "Preview this voice";

  return (
    <>
      <button
        type="button"
        data-testid={`voice-preview-${voiceId}`}
        data-state={state}
        onClick={handleClick}
        disabled={isDisabled}
        title={title}
        aria-label={title}
        style={{
          fontFamily: "var(--mono)",
          fontSize: 11,
          color: state === "error" ? "var(--red, #ef4444)" : "var(--ink-2)",
          background: "transparent",
          border: "1px solid var(--border)",
          padding: "4px 8px",
          minWidth: 30,
          cursor: isDisabled ? "not-allowed" : "pointer",
          opacity: isDisabled && state !== "loading" ? 0.5 : 1,
          ...style,
        }}
      >
        {label}
      </button>
      {url && (
        <audio
          ref={audioRef}
          src={url}
          onPlay={() => setState("playing")}
          onEnded={() => setState("ready")}
          onPause={() => setState("ready")}
          style={{ display: "none" }}
        />
      )}
    </>
  );
}
