import { useState } from "react";
import { submitMatchFeedback } from "../api/api";

const DECISIONS = ["approved", "rejected", "hold"];

export default function MatchFeedbackPanel({
  tenderDocumentId = null,
  match = null,
}) {
  const [decision, setDecision] = useState("approved");
  const [reasonCode, setReasonCode] = useState("");
  const [comment, setComment] = useState("");
  const [reviewedBy, setReviewedBy] = useState("");
  const [saving, setSaving] = useState(false);
  const [savedMessage, setSavedMessage] = useState("");

  const handleSubmit = async () => {
    if (!tenderDocumentId || !match?.document_id) {
      return;
    }

    try {
      setSaving(true);
      setSavedMessage("");
      await submitMatchFeedback({
        tender_document_id: tenderDocumentId,
        resume_document_id: match.document_id,
        system_score: match.score,
        human_decision: decision,
        reason_code: reasonCode || null,
        review_comment: comment || null,
        reviewed_by: reviewedBy || null,
      });
      setSavedMessage("Feedback saved.");
    } catch (error) {
      console.error(error);
      setSavedMessage("Failed to save feedback.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="mt-4 rounded-xl border border-slate-700 bg-slate-900/90 p-3">
      <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Match Feedback</p>

      <div className="mt-3 grid grid-cols-1 gap-3">
        <select
          value={decision}
          onChange={(event) => setDecision(event.target.value)}
          className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white"
        >
          {DECISIONS.map((item) => (
            <option key={item} value={item}>
              {item}
            </option>
          ))}
        </select>

        <input
          value={reasonCode}
          onChange={(event) => setReasonCode(event.target.value)}
          placeholder="reason code"
          className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white"
        />

        <input
          value={reviewedBy}
          onChange={(event) => setReviewedBy(event.target.value)}
          placeholder="reviewed by"
          className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white"
        />

        <textarea
          rows={3}
          value={comment}
          onChange={(event) => setComment(event.target.value)}
          placeholder="comment"
          className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white"
        />
      </div>

      <button
        type="button"
        disabled={saving || !tenderDocumentId || !match?.document_id}
        onClick={handleSubmit}
        className="mt-3 w-full rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-50"
      >
        {saving ? "Saving..." : "Save Feedback"}
      </button>

      {savedMessage && (
        <p className="mt-2 text-xs text-slate-300">{savedMessage}</p>
      )}
    </div>
  );
}
