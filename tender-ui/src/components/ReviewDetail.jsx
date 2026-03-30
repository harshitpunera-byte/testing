import { useEffect, useMemo, useState } from "react";
import {
  approveReviewTask,
  approveTenderCriteria,
  correctReviewTask,
  getDocumentFileUrl,
  getReviewTask,
  rejectReviewTask,
} from "../api/api";

function formatValue(value) {
  if (Array.isArray(value)) {
    return value.join(", ");
  }
  if (value && typeof value === "object") {
    return JSON.stringify(value, null, 2);
  }
  return value ?? "";
}

function buildEditableValue(value) {
  if (Array.isArray(value)) {
    return value.join(", ");
  }
  if (value && typeof value === "object") {
    return JSON.stringify(value, null, 2);
  }
  return value === null || value === undefined ? "" : String(value);
}

function parseEditedValue(rawValue, extractedValue) {
  if (rawValue.trim() === "") {
    return Array.isArray(extractedValue) ? [] : null;
  }

  if (Array.isArray(extractedValue)) {
    return rawValue
      .split(/[\n,]/)
      .map((item) => item.trim())
      .filter(Boolean);
  }

  if (typeof extractedValue === "number") {
    const numeric = Number(rawValue);
    return Number.isNaN(numeric) ? extractedValue : numeric;
  }

  if (typeof extractedValue === "boolean") {
    return rawValue === "true";
  }

  if (extractedValue && typeof extractedValue === "object") {
    try {
      return JSON.parse(rawValue);
    } catch (error) {
      return rawValue;
    }
  }

  return rawValue.trim();
}

export default function ReviewDetail({
  taskId = null,
  refreshKey = 0,
  onTaskUpdated,
}) {
  const [detail, setDetail] = useState(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [reviewer, setReviewer] = useState("");
  const [reviewNotes, setReviewNotes] = useState("");
  const [editedValues, setEditedValues] = useState({});

  useEffect(() => {
    let ignore = false;

    const loadTask = async () => {
      if (!taskId) {
        setDetail(null);
        setEditedValues({});
        return;
      }

      try {
        setLoading(true);
        setError("");
        const res = await getReviewTask(taskId);
        if (ignore) {
          return;
        }

        const nextDetail = res.data;
        setDetail(nextDetail);
        setEditedValues(
          Object.fromEntries(
            (nextDetail?.items || []).map((item) => [
              item.field_name,
              buildEditableValue(item.corrected_value ?? item.extracted_value),
            ])
          )
        );
      } catch (loadError) {
        console.error(loadError);
        if (!ignore) {
          setError("Failed to load review task detail.");
        }
      } finally {
        if (!ignore) {
          setLoading(false);
        }
      }
    };

    loadTask();

    return () => {
      ignore = true;
    };
  }, [refreshKey, taskId]);

  const openDocument = () => {
    if (!detail?.document?.id) {
      return;
    }

    window.open(getDocumentFileUrl(detail.document.id), "_blank", "noopener,noreferrer");
  };

  const corrections = useMemo(() => {
    return (detail?.items || [])
      .map((item) => {
        const rawValue = editedValues[item.field_name];
        const parsedValue = parseEditedValue(rawValue ?? "", item.corrected_value ?? item.extracted_value);
        const baseline = item.corrected_value ?? item.extracted_value;

        if (JSON.stringify(parsedValue) === JSON.stringify(baseline)) {
          return null;
        }

        return {
          review_item_id: item.id,
          field_name: item.field_name,
          corrected_value: parsedValue,
        };
      })
      .filter(Boolean);
  }, [detail?.items, editedValues]);

  const saveApproval = async (action) => {
    if (!detail?.id) {
      return;
    }

    try {
      setSaving(true);
      setError("");

      let response;

      if (action === "reject") {
        response = await rejectReviewTask(detail.id, {
          reviewer: reviewer || null,
          review_notes: reviewNotes || null,
        });
      } else if (action === "correct" && detail?.document?.document_type === "tender") {
        response = await approveTenderCriteria(detail.document.id, {
          reviewer: reviewer || null,
          review_notes: reviewNotes || null,
          corrections,
        });
      } else if (action === "approve" && detail?.document?.document_type === "tender") {
        response = await approveTenderCriteria(detail.document.id, {
          reviewer: reviewer || null,
          review_notes: reviewNotes || null,
          corrections: [],
        });
      } else if (action === "correct") {
        response = await correctReviewTask(detail.id, {
          reviewer: reviewer || null,
          review_notes: reviewNotes || null,
          corrections,
        });
      } else {
        response = await approveReviewTask(detail.id, {
          reviewer: reviewer || null,
          review_notes: reviewNotes || null,
        });
      }

      const nextDetail = response.data;
      setDetail(nextDetail);
      onTaskUpdated?.(nextDetail);
    } catch (saveError) {
      console.error(saveError);
      setError("Failed to save review action.");
    } finally {
      setSaving(false);
    }
  };

  if (!taskId) {
    return (
      <div className="rounded-2xl border border-dashed border-slate-700 bg-slate-950/50 px-4 py-10 text-center text-sm text-slate-400">
        Select a review task to inspect extracted fields and approve or correct them.
      </div>
    );
  }

  if (loading) {
    return (
      <div className="rounded-2xl border border-slate-700 bg-slate-950/50 px-4 py-10 text-sm text-slate-300">
        Loading review detail...
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-2xl border border-red-500/30 bg-red-500/10 px-4 py-4 text-sm text-red-200">
        {error}
      </div>
    );
  }

  if (!detail) {
    return null;
  }

  return (
    <div className="space-y-5">
      <div className="rounded-2xl border border-slate-700 bg-slate-950/60 p-4">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <p className="text-sm font-semibold text-white">
              {detail.document?.original_file_name || "Unknown document"}
            </p>
            <p className="mt-1 text-xs text-slate-400">
              Task #{detail.id} · {detail.document?.document_type} · {detail.status}
            </p>
            <p className="mt-1 text-xs text-slate-500">
              Review status: {detail.document?.review_status} · Confidence: {detail.document?.extraction_confidence ?? "n/a"}
            </p>
          </div>

          <button
            type="button"
            onClick={openDocument}
            className="rounded-xl border border-cyan-400/40 px-3 py-2 text-sm text-cyan-200 hover:bg-cyan-500/10"
          >
            Open PDF
          </button>
        </div>

        {detail.document?.review_summary?.issues?.length > 0 && (
          <div className="mt-4 rounded-xl border border-amber-400/20 bg-amber-500/5 px-3 py-3 text-sm text-amber-100">
            {detail.document.review_summary.issues.join(", ")}
          </div>
        )}
      </div>

      <div className="grid grid-cols-1 gap-5 xl:grid-cols-[1.6fr_1fr]">
        <div className="space-y-4">
          {(detail.items || []).map((item) => (
            <div
              key={item.id}
              className="rounded-2xl border border-slate-700 bg-slate-950/60 p-4"
            >
              <div className="flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
                <div>
                  <p className="text-sm font-semibold text-white">{item.field_name}</p>
                  <p className="text-xs text-slate-400">
                    Confidence: {item.confidence ?? "n/a"} · {item.is_critical ? "critical" : "optional"} · {item.review_status}
                  </p>
                </div>

                {item.evidence_page && (
                  <span className="text-xs uppercase tracking-wide text-cyan-300">
                    Page {item.evidence_page}
                  </span>
                )}
              </div>

              <div className="mt-3 grid grid-cols-1 gap-3 lg:grid-cols-2">
                <div className="rounded-xl border border-slate-800 bg-slate-900/90 p-3">
                  <p className="text-xs uppercase tracking-wide text-slate-500">Extracted</p>
                  <pre className="mt-2 whitespace-pre-wrap text-sm text-slate-200">
                    {formatValue(item.extracted_value) || "No value extracted"}
                  </pre>
                </div>

                <div className="rounded-xl border border-slate-800 bg-slate-900/90 p-3">
                  <p className="text-xs uppercase tracking-wide text-slate-500">Corrected</p>
                  <textarea
                    rows={Array.isArray(item.extracted_value) ? 4 : 3}
                    value={editedValues[item.field_name] ?? ""}
                    onChange={(event) =>
                      setEditedValues((current) => ({
                        ...current,
                        [item.field_name]: event.target.value,
                      }))
                    }
                    className="mt-2 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white"
                  />
                </div>
              </div>

              {item.evidence_text && (
                <div className="mt-3 rounded-xl border border-slate-800 bg-slate-900/90 p-3">
                  <p className="text-xs uppercase tracking-wide text-slate-500">Evidence</p>
                  <p className="mt-2 text-sm text-slate-300">{item.evidence_text}</p>
                </div>
              )}
            </div>
          ))}
        </div>

        <div className="space-y-4">
          <div className="rounded-2xl border border-slate-700 bg-slate-950/60 p-4">
            <p className="text-sm font-semibold text-white">Reviewer Action</p>

            <label className="mt-4 block text-sm text-slate-300">
              <span className="mb-1 block text-xs uppercase tracking-wide text-slate-400">Reviewer</span>
              <input
                value={reviewer}
                onChange={(event) => setReviewer(event.target.value)}
                placeholder="optional reviewer name"
                className="w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white"
              />
            </label>

            <label className="mt-4 block text-sm text-slate-300">
              <span className="mb-1 block text-xs uppercase tracking-wide text-slate-400">Notes</span>
              <textarea
                rows={4}
                value={reviewNotes}
                onChange={(event) => setReviewNotes(event.target.value)}
                placeholder="why you approved, corrected, or rejected this extraction"
                className="w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white"
              />
            </label>

            <div className="mt-4 space-y-3">
              <button
                type="button"
                disabled={saving}
                onClick={() => saveApproval("approve")}
                className="w-full rounded-xl bg-emerald-600 px-4 py-3 text-sm font-medium text-white hover:bg-emerald-500 disabled:opacity-50"
              >
                {saving ? "Saving..." : "Approve"}
              </button>

              <button
                type="button"
                disabled={saving}
                onClick={() => saveApproval(corrections.length > 0 ? "correct" : "approve")}
                className="w-full rounded-xl bg-cyan-600 px-4 py-3 text-sm font-medium text-white hover:bg-cyan-500 disabled:opacity-50"
              >
                {saving ? "Saving..." : corrections.length > 0 ? "Save Corrections" : "Approve Current Values"}
              </button>

              <button
                type="button"
                disabled={saving}
                onClick={() => saveApproval("reject")}
                className="w-full rounded-xl border border-red-400/40 bg-transparent px-4 py-3 text-sm font-medium text-red-200 hover:bg-red-500/10 disabled:opacity-50"
              >
                Reject
              </button>
            </div>
          </div>

          <div className="rounded-2xl border border-slate-700 bg-slate-950/60 p-4">
            <p className="text-sm font-semibold text-white">Canonical Snapshot</p>
            <pre className="mt-3 max-h-96 overflow-auto whitespace-pre-wrap rounded-xl border border-slate-800 bg-slate-900/90 p-3 text-xs text-slate-300">
              {JSON.stringify(detail.document?.canonical_structured_data || {}, null, 2)}
            </pre>
          </div>
        </div>
      </div>
    </div>
  );
}
