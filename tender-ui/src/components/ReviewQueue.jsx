import { useEffect, useState } from "react";
import { getReviewTasks } from "../api/api";

const STATUS_OPTIONS = ["pending", "in_review", "approved", "corrected", "rejected"];
const DOCUMENT_TYPE_OPTIONS = ["resume", "tender"];

export default function ReviewQueue({
  refreshKey = 0,
  selectedTaskId = null,
  onSelectTask,
}) {
  const [tasks, setTasks] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [statusFilter, setStatusFilter] = useState("pending");
  const [documentTypeFilter, setDocumentTypeFilter] = useState("");

  useEffect(() => {
    let ignore = false;

    const loadTasks = async () => {
      try {
        setLoading(true);
        setError("");
        const res = await getReviewTasks({
          status: statusFilter || undefined,
          document_type: documentTypeFilter || undefined,
        });

        if (ignore) {
          return;
        }

        const nextTasks = res.data?.tasks || [];
        setTasks(nextTasks);

        if (!selectedTaskId && nextTasks[0]?.id) {
          onSelectTask?.(nextTasks[0].id);
        }
      } catch (loadError) {
        console.error(loadError);
        if (!ignore) {
          setError("Failed to load review queue.");
        }
      } finally {
        if (!ignore) {
          setLoading(false);
        }
      }
    };

    loadTasks();

    return () => {
      ignore = true;
    };
  }, [documentTypeFilter, onSelectTask, refreshKey, selectedTaskId, statusFilter]);

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
        <label className="text-sm text-slate-300">
          <span className="mb-1 block text-xs uppercase tracking-wide text-slate-400">Status</span>
          <select
            value={statusFilter}
            onChange={(event) => setStatusFilter(event.target.value)}
            className="w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white"
          >
            {STATUS_OPTIONS.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
        </label>

        <label className="text-sm text-slate-300">
          <span className="mb-1 block text-xs uppercase tracking-wide text-slate-400">Document Type</span>
          <select
            value={documentTypeFilter}
            onChange={(event) => setDocumentTypeFilter(event.target.value)}
            className="w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white"
          >
            <option value="">all</option>
            {DOCUMENT_TYPE_OPTIONS.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
        </label>
      </div>

      {loading && (
        <div className="rounded-2xl border border-slate-700 bg-slate-950/50 px-4 py-6 text-sm text-slate-300">
          Loading review queue...
        </div>
      )}

      {error && (
        <div className="rounded-2xl border border-red-500/30 bg-red-500/10 px-4 py-4 text-sm text-red-200">
          {error}
        </div>
      )}

      {!loading && !error && tasks.length === 0 && (
        <div className="rounded-2xl border border-dashed border-slate-700 bg-slate-950/50 px-4 py-6 text-sm text-slate-400">
          No review tasks found for the selected filters.
        </div>
      )}

      {!loading && tasks.length > 0 && (
        <div className="overflow-hidden rounded-2xl border border-slate-700 bg-slate-950/60">
          {tasks.map((task) => {
            const isActive = task.id === selectedTaskId;
            return (
              <button
                key={task.id}
                type="button"
                onClick={() => onSelectTask?.(task.id)}
                className={`flex w-full items-start justify-between gap-4 border-b border-slate-800 px-4 py-4 text-left transition last:border-b-0 ${
                  isActive ? "bg-cyan-500/10" : "hover:bg-slate-900"
                }`}
              >
                <div className="min-w-0">
                  <p className="text-sm font-semibold text-white">
                    Task #{task.id} · {task.document_name || "Unknown document"}
                  </p>
                  <p className="mt-1 text-xs text-slate-400">
                    {task.document_type} · {task.task_type} · {task.status}
                  </p>
                  <p className="mt-1 text-xs text-slate-500">
                    Priority: {task.priority} · Confidence: {task.extraction_confidence ?? "n/a"}
                  </p>
                </div>

                <div className="shrink-0 text-right">
                  <p className="text-xs uppercase tracking-wide text-slate-400">
                    {task.created_at ? new Date(task.created_at).toLocaleString() : ""}
                  </p>
                  {task.issues?.length > 0 && (
                    <p className="mt-2 text-xs text-amber-300">
                      {task.issues.slice(0, 2).join(", ")}
                    </p>
                  )}
                </div>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
