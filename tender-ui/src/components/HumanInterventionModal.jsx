import { useEffect } from "react";

function formatTimestamp(value) {
  if (!value) {
    return "";
  }

  try {
    return new Date(value).toLocaleString();
  } catch (error) {
    return "";
  }
}

export default function HumanInterventionModal({
  open = false,
  reason = "",
  reviewTasks = [],
  selectedTaskId = null,
  onSelectTask,
  onReviewNow,
  onClose,
}) {
  useEffect(() => {
    if (!open) {
      return undefined;
    }

    const handleKeyDown = (event) => {
      if (event.key === "Escape") {
        onClose?.();
      }
    };

    const originalOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", handleKeyDown);

    return () => {
      document.body.style.overflow = originalOverflow;
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [onClose, open]);

  if (!open) {
    return null;
  }

  const activeTaskId = selectedTaskId ?? reviewTasks[0]?.id ?? null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center px-4 py-6 sm:px-6">
      <button
        type="button"
        aria-label="Close human intervention dialog"
        onClick={() => onClose?.()}
        className="absolute inset-0 bg-slate-950/80 backdrop-blur-sm"
      />

      <div className="relative z-10 w-full max-w-3xl overflow-hidden rounded-[28px] border border-amber-400/30 bg-slate-950 text-white shadow-2xl shadow-black/40">
        <div className="border-b border-amber-400/20 bg-[radial-gradient(circle_at_top_left,_rgba(251,191,36,0.18),_transparent_45%),linear-gradient(180deg,rgba(30,41,59,0.98),rgba(2,6,23,0.98))] px-6 py-5 sm:px-8">
          <p className="text-xs font-semibold uppercase tracking-[0.35em] text-amber-300/90">
            Human Intervention
          </p>
          <h2 className="mt-3 text-2xl font-semibold text-white">
            Review needed before relying on this result
          </h2>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-300">
            {reason || "One or more uploaded documents still need review approval."}
          </p>
        </div>

        <div className="px-6 py-6 sm:px-8">
          <div className="rounded-2xl border border-amber-400/15 bg-amber-500/5 px-4 py-4 text-sm text-amber-100">
            {reviewTasks.length} pending review task{reviewTasks.length === 1 ? "" : "s"} detected for the current query.
          </div>

          <div className="mt-5 space-y-3">
            {reviewTasks.map((task) => {
              const isActive = task.id === activeTaskId;
              return (
                <button
                  key={task.id}
                  type="button"
                  onClick={() => onSelectTask?.(task.id)}
                  className={`w-full rounded-2xl border px-4 py-4 text-left transition ${
                    isActive
                      ? "border-amber-300/60 bg-amber-500/10 shadow-lg shadow-amber-500/10"
                      : "border-slate-700 bg-slate-900/70 hover:border-slate-500 hover:bg-slate-900"
                  }`}
                >
                  <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
                    <div className="min-w-0">
                      <p className="text-sm font-semibold text-white">
                        Task #{task.id} · {task.document_name || "Unknown document"}
                      </p>
                      <p className="mt-1 text-xs uppercase tracking-wide text-slate-400">
                        {task.document_type} · {task.task_type} · {task.status}
                      </p>
                      <p className="mt-2 text-sm text-slate-300">
                        Confidence: {task.extraction_confidence ?? "n/a"} · Priority: {task.priority || "unknown"}
                      </p>
                      {task.issues?.length > 0 && (
                        <p className="mt-2 text-sm text-amber-200">
                          {task.issues.slice(0, 3).join(", ")}
                        </p>
                      )}
                    </div>

                    <div className="shrink-0 text-xs text-slate-500">
                      {formatTimestamp(task.created_at)}
                    </div>
                  </div>
                </button>
              );
            })}
          </div>
        </div>

        <div className="flex flex-col-reverse gap-3 border-t border-slate-800 bg-slate-950/95 px-6 py-5 sm:flex-row sm:items-center sm:justify-between sm:px-8">
          <button
            type="button"
            onClick={() => onClose?.()}
            className="rounded-xl border border-slate-700 px-4 py-3 text-sm text-slate-300 hover:bg-slate-900"
          >
            Review Later
          </button>

          <button
            type="button"
            onClick={() => onReviewNow?.(activeTaskId)}
            className="rounded-xl border border-amber-300/60 bg-amber-300 px-4 py-3 text-sm font-semibold text-slate-950 hover:bg-amber-200"
          >
            Open Review Queue
          </button>
        </div>
      </div>
    </div>
  );
}
