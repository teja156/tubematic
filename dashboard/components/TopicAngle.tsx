"use client";

import { useEffect, useId, useState } from "react";
import type { Video } from "@/lib/types";
import {
  ANGLE_MAX_CHARS,
  angleKindLabel,
  angleLength,
  angleScoreLabel,
  cleanAngle,
  fetchAngleKinds,
  hasAngle,
  type AngleKind,
} from "@/lib/angles";
import { patchVideo } from "@/lib/videoStatus";

const caption: React.CSSProperties = {
  fontFamily: "var(--mono)",
  fontSize: 9,
  textTransform: "uppercase",
  letterSpacing: "0.14em",
  color: "var(--dim)",
};

const button: React.CSSProperties = {
  fontFamily: "var(--mono)",
  fontSize: 10,
  textTransform: "uppercase",
  letterSpacing: "0.1em",
  padding: "5px 10px",
  background: "transparent",
  border: "1px solid var(--border-2)",
  color: "var(--ink-2)",
  cursor: "pointer",
};

const field: React.CSSProperties = {
  width: "100%",
  boxSizing: "border-box",
  background: "var(--bg)",
  border: "1px solid var(--border-2)",
  color: "var(--ink)",
  fontFamily: "var(--sans)",
  fontSize: 13,
  padding: "8px 10px",
};

/** A topic's angle on the video window's Topic tab: the sentence saying what
 *  the opening will use, its kind and the agent's score for it.
 *
 *  `editable` is true at Topic Proposed on a live video, the one place a
 *  person may change it (the API refuses it anywhere else). There the block
 *  also shows for a topic with no angle, so one can be added. Past the topic
 *  it is read-only, and a video with no angle shows nothing.
 *
 *  The parent gives it a `key` of the video's id: the window stays mounted
 *  between videos, and a draft must not carry from one to the next.
 *
 *  `onEditingChange` tells the parent while the editor is open, so the window
 *  can hold back Approve Topic: an approval does not carry the draft, and the
 *  agent would then write its own angle over a topic the person meant to
 *  give one. */
export function TopicAngle({ video, editable, onSaved, onEditingChange }: {
  video: Video;
  editable: boolean;
  onSaved: () => void;
  onEditingChange?: (open: boolean) => void;
}) {
  const present = hasAngle(video);
  const show = present || editable;
  const [kinds, setKinds] = useState<AngleKind[] | null>(null);
  // The list was asked for and did not come. A sentence cannot be saved
  // without a kind, so the editor has to say why its picker is empty.
  const [kindsFailed, setKindsFailed] = useState(false);
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState("");
  const [kind, setKind] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const countId = useId();
  const kindHintId = useId();

  // The video left Topic Proposed (approved elsewhere, or by Auto Pilot):
  // the API would refuse the draft, so the editor closes.
  useEffect(() => {
    if (!editable) setEditing(false);
  }, [editable]);

  useEffect(() => {
    onEditingChange?.(editing);
  }, [editing, onEditingChange]);
  // Closed on the way out too, so a window that moves to another video does
  // not keep Approve held back for one whose editor is gone.
  useEffect(() => () => onEditingChange?.(false), [onEditingChange]);

  useEffect(() => {
    if (!show) return;
    let cancelled = false;
    fetchAngleKinds().then((list) => {
      if (cancelled) return;
      if (list) setKinds(list);
      else setKindsFailed(true);
    });
    return () => { cancelled = true; };
  }, [show]);

  if (!show) return null;

  const startEditing = () => {
    setText(video.angle ?? "");
    setKind(video.angle_kind ?? "");
    setError("");
    setEditing(true);
  };

  const trimmed = cleanAngle(text);
  const length = angleLength(text);
  const tooLong = length > ANGLE_MAX_CHARS;
  // An empty sentence saves as "no angle"; a sentence needs its kind.
  const needsKind = trimmed !== "" && kind === "";
  const canSave = !saving && !tooLong && !needsKind;

  const save = async () => {
    if (!canSave) return;
    setSaving(true);
    setError("");
    try {
      await patchVideo(video.id, trimmed === ""
        ? { angle: "", angle_kind: "" }
        : { angle: trimmed, angle_kind: kind });
      setEditing(false);
      onSaved();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Saving the angle failed.");
    } finally {
      setSaving(false);
    }
  };

  // The stored kind stays offered even if the list does not know it, so
  // opening the editor never changes the kind by itself.
  const options = kinds ?? [];
  const storedKind = video.angle_kind ?? "";
  const kindOptions = storedKind && !options.some((k) => k.id === storedKind)
    ? [{ id: storedKind, label: angleKindLabel(storedKind, kinds), means: "" }, ...options]
    : options;

  return (
    <div
      data-testid="topic-angle"
      style={{ border: "1px solid var(--border)", padding: "14px 16px", marginBottom: 18 }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
        <span style={caption}>Angle</span>
        {present && !editing && (
          <>
            <span data-testid="topic-angle-kind" style={{ ...caption, color: "var(--amber)" }}>
              {angleKindLabel(storedKind, kinds)}
            </span>
            <span data-testid="topic-angle-score" style={{ ...caption, color: "var(--ink-2)" }}>
              {angleScoreLabel(video.angle_score)}
            </span>
          </>
        )}
        {editable && !editing && (
          <button
            type="button"
            data-testid="topic-angle-edit"
            onClick={startEditing}
            aria-label={present ? "Edit angle" : "Add angle"}
            style={{ ...button, marginLeft: "auto" }}
          >
            {present ? "Edit" : "Add angle"}
          </button>
        )}
      </div>

      {!editing && (
        present ? (
          <p
            data-testid="topic-angle-text"
            style={{ margin: "8px 0 0", fontSize: 13, lineHeight: 1.6, color: "var(--ink)", fontFamily: "var(--sans)" }}
          >
            {video.angle}
          </p>
        ) : (
          <p
            data-testid="topic-angle-none"
            style={{ margin: "8px 0 0", fontSize: 12, lineHeight: 1.6, color: "var(--dim)", fontFamily: "var(--sans)" }}
          >
            No angle. The agent adds one when it picks the video up after approval.
          </p>
        )
      )}

      {editing && (
        <div style={{ marginTop: 10, display: "flex", flexDirection: "column", gap: 8 }}>
          <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            <span style={caption}>What the opening will use</span>
            <textarea
              data-testid="topic-angle-input"
              value={text}
              onChange={(e) => setText(e.target.value)}
              aria-invalid={tooLong}
              aria-describedby={countId}
              rows={3}
              style={{ ...field, resize: "vertical", lineHeight: 1.5, borderColor: tooLong ? "var(--red)" : "var(--border-2)" }}
            />
          </label>
          <div
            id={countId}
            data-testid="topic-angle-count"
            style={{ ...caption, color: tooLong ? "var(--red)" : "var(--dim)" }}
          >
            {length}/{ANGLE_MAX_CHARS}
          </div>
          <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            <span style={caption}>Kind</span>
            <select
              data-testid="topic-angle-kind-select"
              value={kind}
              onChange={(e) => setKind(e.target.value)}
              aria-invalid={needsKind}
              aria-describedby={needsKind ? kindHintId : undefined}
              style={{ ...field, borderColor: needsKind ? "var(--red)" : "var(--border-2)" }}
            >
              <option value="">Choose a kind</option>
              {kindOptions.map((k) => (
                <option key={k.id} value={k.id}>{k.label}</option>
              ))}
            </select>
          </label>
          {kind !== "" && (kinds?.find((k) => k.id === kind)?.means ?? "") !== "" && (
            <div data-testid="topic-angle-means" style={{ fontSize: 12, lineHeight: 1.5, color: "var(--dim)" }}>
              {kinds?.find((k) => k.id === kind)?.means}
            </div>
          )}
          {needsKind && (
            <div id={kindHintId} data-testid="topic-angle-needs-kind" style={{ fontSize: 12, color: "var(--dim)" }}>
              Choose the angle&apos;s kind to save it.
            </div>
          )}
          {kindsFailed && (
            <div role="alert" data-testid="topic-angle-kinds-failed" style={{ fontSize: 12, color: "var(--red)" }}>
              The list of kinds could not be loaded, so a new kind cannot be chosen. Reload the page
              and try again.
            </div>
          )}
          {error && (
            <div role="alert" data-testid="topic-angle-error" style={{ fontSize: 12, color: "var(--red)" }}>
              {error}
            </div>
          )}
          <div style={{ display: "flex", gap: 8 }}>
            <button
              type="button"
              data-testid="topic-angle-save"
              onClick={save}
              disabled={!canSave}
              style={{ ...button, opacity: canSave ? 1 : 0.5, cursor: canSave ? "pointer" : "not-allowed" }}
            >
              {saving ? "Saving" : "Save"}
            </button>
            <button
              type="button"
              data-testid="topic-angle-cancel"
              onClick={() => setEditing(false)}
              disabled={saving}
              style={button}
            >
              Cancel
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
