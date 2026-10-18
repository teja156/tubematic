"use client";

import { useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

interface ReviseDialogProps {
  open: boolean;
  title: string;
  onClose: () => void;
  onSubmit: (feedback: string) => Promise<void>;
}

export function ReviseDialog({ open, title, onClose, onSubmit }: ReviseDialogProps) {
  const [feedback, setFeedback] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async () => {
    if (!feedback.trim()) return;
    setSubmitting(true);
    try {
      await onSubmit(feedback.trim());
      setFeedback("");
      onClose();
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      {/* Three overrides of DialogContent's defaults, each of which let the
          textarea escape the dialog:
          - Width is inline, not a class: the base `sm:max-w-sm` (384px) beats
            any unprefixed max-w-*, which twMerge cannot collapse against it.
            PublishDialog and VideoModal size themselves the same way.
          - `grid-cols-1` is minmax(0, 1fr). The base is a grid with an auto
            column, and the header's `truncate` line (title || topic, which can
            be a ~2000-char brief) has a nowrap min-content width, so without it
            the column grew to that line and took the w-full textarea with it.
          - The footer's built-in -mx-4/-mb-4 cancel the base p-4, which this
            dialog replaces with p-0, so they are zeroed below. */}
      <DialogContent
        data-testid="revise-dialog"
        className="grid-cols-1 border-[#1e1e30] bg-[#0d0d1a] text-[#f0f0ff] p-0"
        style={{ width: "90vw", maxWidth: 560 }}
      >
        <DialogHeader className="px-6 pt-6 pb-4 border-b border-[#1e1e30]">
          <DialogTitle className="text-sm font-semibold text-[#f0f0ff]">
            Request Revision
          </DialogTitle>
          <p className="mt-1 truncate font-mono text-[10px] uppercase tracking-widest text-[#555572]">
            {title}
          </p>
        </DialogHeader>
        <div className="px-6 py-4">
          <textarea
            className="w-full h-32 resize-none rounded-md border border-[#2a2a42] bg-[#131325]
                       px-4 py-3 text-sm text-[#f0f0ff] placeholder-[#555572]
                       focus:outline-none focus:ring-1 focus:ring-amber-500/40 focus:border-amber-500/40
                       transition-colors"
            placeholder="Describe what needs to change..."
            value={feedback}
            onChange={(e) => setFeedback(e.target.value)}
          />
        </div>
        <DialogFooter className="mx-0 mb-0 px-6 pb-5">
          <button
            onClick={onClose}
            className="rounded px-4 py-2 text-sm text-[#9a9ab8] hover:text-[#f0f0ff] transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            disabled={!feedback.trim() || submitting}
            className="rounded px-4 py-2 text-sm font-medium bg-amber-500/10 hover:bg-amber-500/20
                       text-amber-400 border border-amber-500/25 hover:border-amber-500/50
                       transition-all duration-150 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {submitting ? "Sending…" : "Send Revision Request"}
          </button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
