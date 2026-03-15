import { getDocumentFileUrl } from "../api/api";

const TAB_OPTIONS = [
  { id: "resume", label: "Resume JSON" },
  { id: "tender", label: "Tender JSON" },
  { id: "profiles", label: "Profiles" },
];

function buildResumeJson(resumeUploads) {
  return resumeUploads.map((item) => ({
    document_id: item.document_id,
    filename: item.filename,
    status: item.status,
    pages: item.pages,
    extraction_backend: item.extraction_backend,
    structured_data: item.structured_data || {},
    evidence_map: item.evidence_map || {},
  }));
}

function buildTenderJson(tenderUpload) {
  if (!tenderUpload) {
    return null;
  }

  return {
    document_id: tenderUpload.document_id,
    filename: tenderUpload.filename,
    status: tenderUpload.status,
    pages: tenderUpload.pages,
    extraction_backend: tenderUpload.extraction_backend,
    structured_data: tenderUpload.structured_data || {},
    evidence_map: tenderUpload.evidence_map || {},
  };
}

function sortProfiles(matches) {
  return [...matches].sort((left, right) => {
    if ((right.score || 0) !== (left.score || 0)) {
      return (right.score || 0) - (left.score || 0);
    }

    if (Boolean(right.experience_match) !== Boolean(left.experience_match)) {
      return Number(Boolean(right.experience_match)) - Number(Boolean(left.experience_match));
    }

    return String(left.candidate_name || left.filename || "").localeCompare(
      String(right.candidate_name || right.filename || "")
    );
  });
}

function JsonBlock({ value }) {
  return (
    <pre className="max-h-[28rem] overflow-auto rounded-2xl border border-cyan-500/20 bg-slate-950/90 p-4 font-mono text-xs leading-6 text-cyan-100">
      {JSON.stringify(value, null, 2)}
    </pre>
  );
}

function EmptyState({ title, description }) {
  return (
    <div className="rounded-2xl border border-dashed border-slate-600 bg-slate-900/60 px-5 py-12 text-center">
      <p className="text-base font-semibold text-slate-100">{title}</p>
      <p className="mt-2 text-sm text-slate-400">{description}</p>
    </div>
  );
}

export default function InsightsPanel({
  activeTab = "resume",
  onTabChange,
  resumeUploads = [],
  tenderUpload = null,
  latestMatchResult = null,
}) {
  const resumeJson = buildResumeJson(resumeUploads);
  const tenderJson = buildTenderJson(tenderUpload);
  const profiles = sortProfiles(latestMatchResult?.matches || []);

  const openDocument = (documentId) => {
    if (!documentId) {
      return;
    }

    window.open(getDocumentFileUrl(documentId), "_blank", "noopener,noreferrer");
  };

  return (
    <section className="mx-8 mb-10 rounded-[28px] border border-slate-700/80 bg-slate-900/90 shadow-2xl shadow-black/20">
      <div className="border-b border-slate-700/80 px-6 py-5">
        <p className="text-xs font-semibold uppercase tracking-[0.3em] text-cyan-300/80">
          Data Workspace
        </p>
        <div className="mt-3 flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
          <div>
            <h2 className="text-2xl font-semibold text-white">Structured Outputs and Profiles</h2>
            <p className="mt-1 text-sm text-slate-400">
              Extracted JSON appears here after upload, and ranked profiles open here after matching.
            </p>
          </div>

          <div className="inline-flex rounded-2xl border border-slate-700 bg-slate-950/70 p-1">
            {TAB_OPTIONS.map((tab) => {
              const isActive = activeTab === tab.id;
              return (
                <button
                  key={tab.id}
                  type="button"
                  onClick={() => onTabChange?.(tab.id)}
                  className={`rounded-xl px-4 py-2 text-sm font-medium transition ${
                    isActive
                      ? "bg-cyan-400 text-slate-950 shadow-lg shadow-cyan-500/20"
                      : "text-slate-300 hover:bg-slate-800 hover:text-white"
                  }`}
                >
                  {tab.label}
                </button>
              );
            })}
          </div>
        </div>
      </div>

      <div className="p-6">
        {activeTab === "resume" && (
          <>
            {resumeJson.length > 0 ? (
              <div className="space-y-5">
                {resumeUploads.map((item) => (
                  <div
                    key={`${item.document_id}-${item.filename}`}
                    className="rounded-2xl border border-slate-700 bg-slate-900/70 p-4"
                  >
                    <div className="mb-3 flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                      <div>
                        <p className="text-sm font-semibold text-white">{item.filename}</p>
                        <p className="text-xs text-slate-400">
                          Document ID: {item.document_id} | Status: {item.status || "unknown"}
                        </p>
                      </div>

                      <button
                        type="button"
                        onClick={() => openDocument(item.document_id)}
                        disabled={!item.document_id}
                        className="rounded-xl border border-cyan-400/50 px-3 py-2 text-sm text-cyan-200 hover:bg-cyan-500/10 disabled:cursor-not-allowed disabled:opacity-40"
                      >
                        Open Resume
                      </button>
                    </div>

                    <JsonBlock
                      value={{
                        document_id: item.document_id,
                        filename: item.filename,
                        status: item.status,
                        pages: item.pages,
                        extraction_backend: item.extraction_backend,
                        structured_data: item.structured_data || {},
                        evidence_map: item.evidence_map || {},
                      }}
                    />
                  </div>
                ))}
              </div>
            ) : (
              <EmptyState
                title="No resume JSON yet"
                description="Upload a resume to view its structured extraction in formatted JSON."
              />
            )}
          </>
        )}

        {activeTab === "tender" && (
          <>
            {tenderJson ? (
              <div className="space-y-4">
                <div className="flex flex-col gap-3 rounded-2xl border border-slate-700 bg-slate-900/70 p-4 md:flex-row md:items-center md:justify-between">
                  <div>
                    <p className="text-sm font-semibold text-white">{tenderUpload.filename}</p>
                    <p className="text-xs text-slate-400">
                      Document ID: {tenderUpload.document_id} | Status: {tenderUpload.status || "unknown"}
                    </p>
                  </div>

                  <button
                    type="button"
                    onClick={() => openDocument(tenderUpload.document_id)}
                    disabled={!tenderUpload.document_id}
                    className="rounded-xl border border-emerald-400/50 px-3 py-2 text-sm text-emerald-200 hover:bg-emerald-500/10 disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    Open Tender
                  </button>
                </div>

                <JsonBlock value={tenderJson} />
              </div>
            ) : (
              <EmptyState
                title="No tender JSON yet"
                description="Upload a tender to view the extracted requirements in JSON."
              />
            )}
          </>
        )}

        {activeTab === "profiles" && (
          <>
            {profiles.length > 0 ? (
              <div className="space-y-5">
                {latestMatchResult?.reasoning_summary && (
                  <div className="rounded-2xl border border-amber-400/20 bg-amber-500/5 p-4 text-sm text-amber-100">
                    {latestMatchResult.reasoning_summary}
                  </div>
                )}

                <div className="overflow-hidden rounded-2xl border border-slate-700 bg-slate-950/60">
                  {profiles.map((profile, index) => (
                    <button
                      key={`${profile.document_id || profile.filename}-${index}`}
                      type="button"
                      onClick={() => openDocument(profile.document_id)}
                      disabled={!profile.document_id}
                      className="flex w-full items-start justify-between gap-4 border-b border-slate-800 px-4 py-4 text-left transition hover:bg-slate-800/80 disabled:cursor-not-allowed disabled:opacity-50 last:border-b-0"
                    >
                      <div className="min-w-0">
                        <p className="text-sm font-semibold text-white">
                          #{index + 1} {profile.candidate_name || profile.filename || "Unknown Candidate"}
                        </p>
                        <p className="mt-1 text-xs text-slate-400">
                          {profile.candidate_role || "Role not detected"} | {profile.candidate_domain || "Domain not detected"}
                        </p>
                        <p className="mt-1 line-clamp-2 text-xs text-slate-500">
                          {profile.filename}
                        </p>
                      </div>

                      <div className="shrink-0 text-right">
                        <p className="text-lg font-semibold text-cyan-300">{profile.score || 0}%</p>
                        <p className="text-xs text-slate-300">{profile.verdict || "Unranked"}</p>
                      </div>
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              <EmptyState
                title="No ranked profiles yet"
                description="Run matching from Ask AI to view ranked resumes here and open each PDF directly."
              />
            )}
          </>
        )}
      </div>
    </section>
  );
}
