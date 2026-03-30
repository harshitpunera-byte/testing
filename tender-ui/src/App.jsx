import { useState } from "react";
import API from "./api/api";
import ResumeUpload from "./components/ResumeUpload";
import TenderUpload from "./components/TenderUpload";
import AskAgent from "./components/AskAgent";
import InsightsPanel from "./components/InsightsPanel";
import HumanInterventionModal from "./components/HumanInterventionModal";

function App() {
  const [activeResumeDocumentIds, setActiveResumeDocumentIds] = useState([]);
  const [activeTenderDocumentId, setActiveTenderDocumentId] = useState(null);
  const [resumeUploads, setResumeUploads] = useState([]);
  const [tenderUpload, setTenderUpload] = useState(null);
  const [latestMatchResult, setLatestMatchResult] = useState(null);
  const [activeWorkspaceTab, setActiveWorkspaceTab] = useState("resume");
  const [uiResetKey, setUiResetKey] = useState(0);
  const [systemMessage, setSystemMessage] = useState("");
  const [systemMessageIsError, setSystemMessageIsError] = useState(false);
  const [clearingDatabase, setClearingDatabase] = useState(false);
  const [reviewRefreshKey, setReviewRefreshKey] = useState(0);
  const [selectedReviewTaskId, setSelectedReviewTaskId] = useState(null);
  const [humanInterventionState, setHumanInterventionState] = useState(null);

  const resolvePendingReviewTaskId = (nextTenderUpload = tenderUpload, nextResumeUploads = resumeUploads) => {
    if (nextTenderUpload?.review_status === "needs_review" && nextTenderUpload?.review_task_id) {
      return nextTenderUpload.review_task_id;
    }

    const resumeReviewRecord = (nextResumeUploads || []).find(
      (item) => item?.review_status === "needs_review" && item?.review_task_id
    );

    return resumeReviewRecord?.review_task_id ?? null;
  };

  const handleResumeUploadComplete = (documentIds = [], uploadedRecords = []) => {
    setActiveResumeDocumentIds(documentIds);
    setResumeUploads(uploadedRecords);
    setLatestMatchResult(null);
    setHumanInterventionState(null);
    setReviewRefreshKey((value) => value + 1);
    setSelectedReviewTaskId(resolvePendingReviewTaskId(tenderUpload, uploadedRecords));
    setSystemMessage("");
    setSystemMessageIsError(false);
    setActiveWorkspaceTab("resume");
  };

  const handleTenderUploadComplete = (documentId = null, uploadedRecord = null) => {
    setActiveTenderDocumentId(documentId);
    setTenderUpload(uploadedRecord);
    setLatestMatchResult(null);
    setHumanInterventionState(null);
    setReviewRefreshKey((value) => value + 1);
    setSelectedReviewTaskId(resolvePendingReviewTaskId(uploadedRecord, resumeUploads));
    setSystemMessage("");
    setSystemMessageIsError(false);
    setActiveWorkspaceTab("tender");
  };

  const handleAnswerReady = (answerPayload) => {
    setLatestMatchResult(answerPayload);
    const reviewTasks = Array.isArray(answerPayload?.review_tasks) ? answerPayload.review_tasks : [];

    if (Array.isArray(answerPayload?.matches) || answerPayload?.mode === "matching") {
      setActiveWorkspaceTab("profiles");
    }

    if (answerPayload?.human_intervention_required && reviewTasks.length > 0) {
      const initialTaskId = reviewTasks[0].id ?? null;
      setSelectedReviewTaskId(initialTaskId);
      setHumanInterventionState({
        open: true,
        reason:
          answerPayload.human_intervention_reason ||
          "Human review is needed for one or more uploaded documents before relying on this result.",
        reviewTasks,
      });
      setSystemMessage("");
      setSystemMessageIsError(false);
      return;
    }

    setHumanInterventionState(null);
    setSelectedReviewTaskId(resolvePendingReviewTaskId());
    setSystemMessage("");
    setSystemMessageIsError(false);
  };

  const closeHumanInterventionModal = () => {
    setHumanInterventionState((current) => (current ? { ...current, open: false } : null));
  };

  const openReviewQueueFromModal = (taskId = null) => {
    if (taskId) {
      setSelectedReviewTaskId(taskId);
    }
    setHumanInterventionState(null);
    setReviewRefreshKey((value) => value + 1);
    setActiveWorkspaceTab("review");
  };

  const clearDatabase = async () => {
    const confirmed = window.confirm(
      "This will delete all stored tenders, resumes, vectors, and extracted data. Continue?"
    );

    if (!confirmed) {
      return;
    }

    try {
      setClearingDatabase(true);
      setSystemMessage("");
      setSystemMessageIsError(false);

      const res = await API.post("/system/clear-database");

      setActiveResumeDocumentIds([]);
      setActiveTenderDocumentId(null);
      setResumeUploads([]);
      setTenderUpload(null);
      setLatestMatchResult(null);
      setHumanInterventionState(null);
      setActiveWorkspaceTab("resume");
      setSelectedReviewTaskId(null);
      setReviewRefreshKey((value) => value + 1);
      setUiResetKey((value) => value + 1);
      setSystemMessage(res.data?.message || "Application database cleared successfully.");
    } catch (error) {
      console.error(error);
      setSystemMessageIsError(true);
      setSystemMessage("Failed to clear application database.");
      alert("Database clear failed");
    } finally {
      setClearingDatabase(false);
    }
  };

  return (
    <div className="min-h-screen bg-gray-900 text-white">
      <div className="bg-gray-800 border-b border-gray-700 p-6">
        <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
          <div>
            <h1 className="text-3xl font-bold">Tender AI Matching System</h1>
            <p className="text-gray-400 mt-1">
              Upload tender PDF, upload one or many resumes, and find the best candidates.
            </p>
            {systemMessage && (
              <p className={`mt-3 text-sm ${systemMessageIsError ? "text-red-300" : "text-green-300"}`}>
                {systemMessage}
              </p>
            )}
          </div>

          <button
            type="button"
            onClick={clearDatabase}
            disabled={clearingDatabase}
            className="rounded-lg border border-red-400 bg-transparent px-4 py-3 text-red-300 hover:bg-red-500/10 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {clearingDatabase ? "Clearing..." : "Clear Database"}
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-6 p-8 lg:grid-cols-4">
        <div className="space-y-6 lg:col-span-1">
          <div className="bg-gray-800 rounded-xl p-6 shadow-lg">
            <h2 className="text-xl font-semibold mb-4">Upload Resumes</h2>
            <ResumeUpload
              key={`resume-${uiResetKey}`}
              onUploadComplete={handleResumeUploadComplete}
            />
          </div>

          <div className="bg-gray-800 rounded-xl p-6 shadow-lg">
            <h2 className="text-xl font-semibold mb-4">Upload Tender</h2>
            <TenderUpload
              key={`tender-${uiResetKey}`}
              onUploadComplete={handleTenderUploadComplete}
            />
          </div>
        </div>

        <div className="bg-gray-800 rounded-xl p-6 shadow-lg lg:col-span-3">
          <h2 className="text-xl font-semibold mb-4">Ask AI</h2>
          <AskAgent
            key={`ask-${uiResetKey}`}
            activeResumeDocumentIds={activeResumeDocumentIds}
            activeTenderDocumentId={activeTenderDocumentId}
            onAnswerReady={handleAnswerReady}
          />
        </div>
      </div>

      <InsightsPanel
        activeTab={activeWorkspaceTab}
        onTabChange={setActiveWorkspaceTab}
        resumeUploads={resumeUploads}
        tenderUpload={tenderUpload}
        latestMatchResult={latestMatchResult}
        activeTenderDocumentId={activeTenderDocumentId}
        reviewRefreshKey={reviewRefreshKey}
        selectedReviewTaskId={selectedReviewTaskId}
        onSelectReviewTask={setSelectedReviewTaskId}
        onReviewTaskUpdated={() => setReviewRefreshKey((value) => value + 1)}
      />

      <HumanInterventionModal
        open={Boolean(humanInterventionState?.open)}
        reason={humanInterventionState?.reason || ""}
        reviewTasks={humanInterventionState?.reviewTasks || []}
        selectedTaskId={selectedReviewTaskId}
        onSelectTask={setSelectedReviewTaskId}
        onReviewNow={openReviewQueueFromModal}
        onClose={closeHumanInterventionModal}
      />
    </div>
  );
}

export default App;
