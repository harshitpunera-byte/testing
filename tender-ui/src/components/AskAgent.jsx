import { useEffect, useRef, useState } from "react";
import API from "../api/api";

function buildConversationId() {
  return `chat-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

function MatchCard({ item, index }) {
  return (
    <div className="rounded-2xl border border-slate-700/80 bg-slate-950/70 p-4">
      <div className="flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
        <div>
          <p className="text-sm font-semibold text-white">
            #{index + 1} {item.candidate_name || item.filename || "Unknown Candidate"}
          </p>
          <p className="mt-1 text-xs text-slate-400">
            {item.candidate_role || "Role not detected"} | {item.candidate_domain || "Domain not detected"}
          </p>
        </div>

        <div className="rounded-xl bg-cyan-500/10 px-3 py-2 text-xs font-medium text-cyan-100">
          Score {item.score ?? 0}% | {item.verdict || "Pending"}
        </div>
      </div>

      <div className="mt-3 grid gap-2 text-xs text-slate-300 md:grid-cols-2">
        <p>Review Status: {item.review_status || "unknown"}</p>
        <p>Candidate Experience: {item.candidate_experience ?? "Not detected"} years</p>
        <p>Experience Match: {item.experience_match ? "Yes" : "No"}</p>
        <p>Domain Match: {item.domain_match ? "Yes" : "No"}</p>
        {item.phone && <p className="text-cyan-400 font-medium">Phone: {item.phone}</p>}
        {item.email && <p className="text-cyan-400 font-medium truncate">Email: {item.email}</p>}
      </div>

      <div className="mt-3 space-y-2 text-xs text-slate-300">
        <p>
          <span className="font-semibold text-slate-200">Matched Skills:</span>{" "}
          {item.matched_skills?.length ? item.matched_skills.join(", ") : "None"}
        </p>
        <p>
          <span className="font-semibold text-slate-200">Matched Preferred Skills:</span>{" "}
          {item.matched_preferred_skills?.length ? item.matched_preferred_skills.join(", ") : "None"}
        </p>
        <p>
          <span className="font-semibold text-slate-200">Missing Skills:</span>{" "}
          {item.missing_skills?.length ? item.missing_skills.join(", ") : "None"}
        </p>
        <p>
          <span className="font-semibold text-slate-200">Reasoning:</span> {item.reasoning || "Not available"}
        </p>
      </div>
    </div>
  );
}

function DiagnosticTrace({ steps }) {
  if (!Array.isArray(steps) || steps.length === 0) return null;

  return (
    <details className="group rounded-2xl border border-slate-700/50 bg-black/40 p-4 text-xs">
      <summary className="flex cursor-pointer items-center justify-between font-semibold text-slate-400 transition hover:text-slate-300">
        <span>⚡ Execution Trace & Decision Logic</span>
        <span className="text-[10px] uppercase tracking-widest text-slate-500 group-open:hidden">
          Show Steps
        </span>
      </summary>
      <div className="mt-3 space-y-2 border-t border-slate-800/50 pt-3">
        {steps.map((step, i) => (
          <div key={i} className="flex gap-3 text-slate-400">
            <span className="shrink-0 text-slate-600">{i + 1}.</span>
            <span className="leading-relaxed">{step}</span>
          </div>
        ))}
      </div>
    </details>
  );
}

function AnswerTextBlock({ text }) {
  const blocks = String(text || "")
    .split(/\n\s*\n/)
    .map((block) => block.split("\n").map((line) => line.trim()).filter(Boolean))
    .filter((block) => block.length > 0);

  return (
    <div className="space-y-4 text-sm text-slate-100">
      {blocks.map((lines, index) => {
        const isNumberedList = lines.every((line) => /^\d+\.\s+/.test(line));
        const isBulletList = lines.every((line) => /^[-•]\s+/.test(line));
        const isStandaloneHeading = lines.length === 1 && lines[0].endsWith(":");

        if (isStandaloneHeading) {
          return (
            <p key={`heading-${index}`} className="font-semibold text-white">
              {lines[0]}
            </p>
          );
        }

        if (isNumberedList) {
          return (
            <ol key={`olist-${index}`} className="space-y-2 pl-5 text-slate-200 list-decimal">
              {lines.map((line, itemIndex) => (
                <li key={`olist-item-${index}-${itemIndex}`}>{line.replace(/^\d+\.\s+/, "")}</li>
              ))}
            </ol>
          );
        }

        if (isBulletList) {
          return (
            <ul key={`ulist-${index}`} className="space-y-2 pl-5 text-slate-200 list-disc">
              {lines.map((line, itemIndex) => (
                <li key={`ulist-item-${index}-${itemIndex}`}>{line.replace(/^[-•]\s+/, "")}</li>
              ))}
            </ul>
          );
        }

        return (
          <div key={`block-${index}`} className="space-y-2">
            {lines.map((line, lineIndex) => {
              const isSectionLabel = line.endsWith(":");
              return (
                <p
                  key={`line-${index}-${lineIndex}`}
                  className={isSectionLabel ? "font-semibold text-white" : "leading-7 text-slate-100"}
                >
                  {line}
                </p>
              );
            })}
          </div>
        );
      })}
    </div>
  );
}

function AssistantAnswer({ answer, error = false, errorMessage = "" }) {
  if (error) {
    return (
      <div className="rounded-2xl border border-rose-400/30 bg-rose-500/10 p-4 text-sm text-rose-100">
        {errorMessage || "Matching failed. Please try again."}
      </div>
    );
  }

  if (!answer) {
    return (
      <div className="space-y-3">
        <div className="flex items-center gap-3">
          <div className="h-4 w-4 animate-spin rounded-full border-2 border-cyan-400 border-t-transparent" />
          <p className="text-sm font-semibold text-white">AI is analyzing your request...</p>
        </div>
        <div className="h-1.5 w-full overflow-hidden rounded-full bg-slate-800">
          <div className="h-full w-1/2 animate-[progress_1.5s_ease-in-out_infinite] rounded-full bg-cyan-400" />
        </div>
        <p className="text-xs text-slate-400">
          Reviewing thousands of data points across your uploaded documents.
        </p>
      </div>
    );
  }

  const hasMatches = Array.isArray(answer.matches) && answer.matches.length > 0;
  const hasVisibleContent =
    answer.message ||
    answer.answer_text ||
    hasMatches ||
    answer.reasoning_summary ||
    answer.human_intervention_required ||
    answer.uses_unreviewed_data;

  return (
    <div className="space-y-4">
      {answer.message && <p className="text-sm font-semibold text-white">{answer.message}</p>}

      {answer.human_intervention_required && (
        <div className="rounded-2xl border border-amber-400/30 bg-amber-500/10 p-4 text-sm text-amber-100">
          <p>{answer.human_intervention_reason || "Human review is needed before relying on this answer."}</p>
          {answer.review_tasks?.length > 0 && (
            <p className="mt-2 text-xs text-amber-200">
              Pending review tasks: {answer.review_tasks.map((task) => `#${task.id}`).join(", ")}
            </p>
          )}
        </div>
      )}

      {!answer.human_intervention_required && answer.uses_unreviewed_data && (
        <div className="rounded-2xl border border-amber-400/20 bg-amber-500/5 p-4 text-sm text-amber-100">
          One or more retrieval or matching steps used unreviewed extracted data. Canonical review-approved data will take priority automatically when available.
        </div>
      )}

      {answer.answer_text && (
        <div className="rounded-2xl bg-slate-950/70 p-4 text-sm text-slate-100">
          <AnswerTextBlock text={answer.answer_text} />
        </div>
      )}

      {answer.sources?.length > 0 && (
        <div className="rounded-2xl bg-slate-950/70 p-4 text-sm text-slate-200">
          <p className="mb-2 font-semibold text-white">Sources</p>
          <ul className="space-y-2 text-xs text-slate-300">
            {answer.sources.map((source, index) => (
              <li key={`${source.filename}-${source.page_start ?? "na"}-${index}`}>
                {source.filename} | page {source.page_start ?? "?"}
                {source.page_end && source.page_end !== source.page_start ? `-${source.page_end}` : ""}
                {source.section ? ` | ${source.section}` : ""}
              </li>
            ))}
          </ul>
        </div>
      )}

      {answer.tender_requirements && (
        <div className="rounded-2xl bg-slate-950/70 p-4 text-sm text-slate-200">
          <p className="mb-2 font-semibold text-white">Extracted Tender Requirements</p>
          <p>
            <span className="font-semibold text-slate-100">Skills:</span>{" "}
            {answer.tender_requirements.skills_required?.length
              ? answer.tender_requirements.skills_required.join(", ")
              : "None detected"}
          </p>
          <p className="mt-1">
            <span className="font-semibold text-slate-100">Experience:</span>{" "}
            {answer.tender_requirements.experience_required || "Not detected"} years
          </p>
        </div>
      )}

      {answer.tender_evidence_map && (
        <div className="rounded-2xl bg-slate-950/70 p-4 text-sm text-slate-200">
          <p className="mb-2 font-semibold text-white">Tender Evidence</p>
          <p>
            <span className="font-semibold text-slate-100">Role Page:</span>{" "}
            {answer.tender_evidence_map.role?.page ?? "Not detected"}
          </p>
          <p className="mt-1">
            <span className="font-semibold text-slate-100">Experience Page:</span>{" "}
            {answer.tender_evidence_map.experience_required?.page ?? "Not detected"}
          </p>
        </div>
      )}

      {answer.reasoning_summary && (
        <div className="rounded-2xl bg-slate-950/70 p-4 text-sm text-slate-200">
          <p className="mb-2 font-semibold text-white">Reasoning Summary</p>
          <AnswerTextBlock text={answer.reasoning_summary} />
        </div>
      )}

      {/* Execution Trace - Professional Transparency */}
      {answer.execution_steps && (
        <DiagnosticTrace steps={answer.execution_steps} />
      )}
      
      {/* Generated SQL Section - Always available if returned */}
      {answer.generated_sql && (
        <details className="group rounded-2xl border border-slate-700/50 bg-slate-950/70 p-4 text-xs">
          <summary className="cursor-pointer font-semibold text-cyan-400 transition hover:text-cyan-300">
            View Structural SQL Query (Transparency Tool)
          </summary>
          <div className="mt-3 overflow-x-auto rounded-xl bg-black/60 p-3">
            <pre className="whitespace-pre text-cyan-100/70 font-mono">
              {answer.generated_sql}
            </pre>
          </div>
        </details>
      )}

      {hasMatches ? (
        <div className="space-y-3">
          <p className="text-sm font-semibold text-white">Matching Resumes</p>
          {answer.matches.map((item, index) => (
            <MatchCard
              key={`${item.document_id || item.filename || "match"}-${index}`}
              item={item}
              index={index}
            />
          ))}
        </div>
      ) : answer.mode === "matching" ? (
        <p className="text-sm text-slate-300">No matches found.</p>
      ) : null}

      {!hasVisibleContent && (
        <p className="text-sm text-slate-300">No answer content was returned for this question.</p>
      )}
    </div>
  );
}

export default function AskAgent({
  activeResumeDocumentIds = [],
  activeTenderDocumentId = null,
  onAnswerReady,
}) {
  const [query, setQuery] = useState("");
  const [conversation, setConversation] = useState([]);
  const [loading, setLoading] = useState(false);
  const conversationEndRef = useRef(null);

  useEffect(() => {
    conversationEndRef.current?.scrollIntoView({
      behavior: conversation.length > 1 ? "smooth" : "auto",
      block: "end",
    });
  }, [conversation]);

  const updateConversationEntry = (entryId, updates) => {
    setConversation((current) =>
      current.map((entry) => (entry.id === entryId ? { ...entry, ...updates } : entry))
    );
  };

  const fetchRankedProfiles = async () => {
    if (!activeTenderDocumentId || !activeResumeDocumentIds.length) {
      return null;
    }

    const res = await API.post("/match/", {
      query: "shortlist top matching profiles for the uploaded tender",
      tender_document_id: activeTenderDocumentId,
      resume_document_ids: activeResumeDocumentIds,
      restrict_to_active_uploads: true,
    });

    return res.data?.matches || null;
  };

  const askAI = async () => {
    const nextQuery = query.trim();

    if (!nextQuery) {
      return;
    }

    const conversationId = buildConversationId();

    setConversation((current) => [
      ...current,
      {
        id: conversationId,
        question: nextQuery,
        answer: null,
        loading: true,
        error: false,
        errorMessage: "",
      },
    ]);
    setQuery("");

    try {
      setLoading(true);

      const res = await API.post("/match/", {
        query: nextQuery,
        tender_document_id: activeTenderDocumentId,
        resume_document_ids: activeResumeDocumentIds,
        restrict_to_active_uploads: true,
      });

      const answerPayload = res.data?.matches || {
        message: "No response returned.",
        answer_text: "",
      };

      updateConversationEntry(conversationId, {
        answer: answerPayload,
        loading: false,
      });

      let profilesPayload = answerPayload;
      const needsProfileFetch =
        answerPayload?.mode !== "matching" &&
        activeTenderDocumentId &&
        activeResumeDocumentIds.length > 0;

      if (needsProfileFetch) {
        try {
          const rankedProfiles = await fetchRankedProfiles();
          if (rankedProfiles) {
            profilesPayload = {
              ...rankedProfiles,
              human_intervention_required:
                answerPayload?.human_intervention_required || rankedProfiles?.human_intervention_required || false,
              human_intervention_reason:
                answerPayload?.human_intervention_reason || rankedProfiles?.human_intervention_reason || "",
              review_tasks:
                (answerPayload?.review_tasks?.length ? answerPayload.review_tasks : rankedProfiles?.review_tasks) || [],
            };
          }
        } catch (profileError) {
          console.error(profileError);
        }
      }

      onAnswerReady?.(profilesPayload);
    } catch (error) {
      console.error(error);
      updateConversationEntry(conversationId, {
        loading: false,
        error: true,
        errorMessage: "Matching failed. Please try again.",
      });
    } finally {
      setLoading(false);
    }
  };

  const handleQueryKeyDown = (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();

      if (!loading) {
        askAI();
      }
    }
  };

  const hasTender = Boolean(activeTenderDocumentId);
  const resumeCount = activeResumeDocumentIds.length;

  return (
    <div className="flex h-[34rem] flex-col overflow-hidden rounded-2xl border border-slate-700/80 bg-slate-950/40">
      <div className="flex-1 space-y-5 overflow-y-auto p-4">
        {conversation.length === 0 ? (
          <div className="rounded-2xl border border-dashed border-slate-700 bg-slate-950/60 px-5 py-10 text-center">
            <p className="text-base font-semibold text-white">Start the conversation</p>
            <p className="mt-2 text-sm text-slate-400">
              Each submitted question will move into the chat and the answer will appear directly below it.
            </p>
            <p className="mt-3 text-xs text-slate-500">
              Tender: {hasTender ? "ready" : "not uploaded"} | Resumes: {resumeCount}
            </p>
          </div>
        ) : (
          conversation.map((entry) => (
            <div key={entry.id} className="space-y-3">
              <div className="flex justify-end">
                <div className="max-w-[88%] rounded-[24px] rounded-br-md bg-cyan-400 px-4 py-3 text-sm font-medium text-slate-950 shadow-lg shadow-cyan-500/10">
                  {entry.question}
                </div>
              </div>

              <div className="flex justify-start">
                <div className="max-w-[92%] rounded-[24px] rounded-bl-md border border-slate-700 bg-slate-900/95 px-4 py-4 text-sm text-slate-100 shadow-lg shadow-black/20">
                  {entry.loading ? (
                    <AssistantAnswer />
                  ) : (
                    <AssistantAnswer
                      answer={entry.answer}
                      error={entry.error}
                      errorMessage={entry.errorMessage}
                    />
                  )}
                </div>
              </div>
            </div>
          ))
        )}

        <div ref={conversationEndRef} />
      </div>

      <div className="border-t border-slate-700/80 bg-slate-950/90 p-4">
        <div className="rounded-[26px] border border-slate-700 bg-slate-900/90 p-3">
          <textarea
            className="min-h-[88px] w-full resize-none bg-transparent px-1 py-2 text-sm text-white outline-none placeholder:text-slate-500"
            rows="3"
            placeholder="Ask about the uploaded tender, uploaded resumes, or ask for matching"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            onKeyDown={handleQueryKeyDown}
          />

          <div className="mt-3 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <p className="text-xs text-slate-500">
              {hasTender ? "Tender uploaded" : "Upload a tender"}
              {" | "}
              {resumeCount > 0 ? `${resumeCount} resume${resumeCount > 1 ? "s" : ""} uploaded` : "Upload resumes for matching"}
            </p>

            <button
              type="button"
              onClick={askAI}
              disabled={loading || !query.trim()}
              className="rounded-xl bg-cyan-400 px-4 py-2 text-sm font-semibold text-slate-950 transition hover:bg-cyan-300 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {loading ? "Analyzing..." : "Send"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
