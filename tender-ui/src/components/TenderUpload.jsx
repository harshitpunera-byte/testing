import { useRef, useState } from "react";
import API from "../api/api";

export default function TenderUpload({ onUploadComplete }) {
  const fileInputRef = useRef(null);

  const [file, setFile] = useState(null);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [progress, setProgress] = useState(0);

  const handlePickFile = () => {
    fileInputRef.current?.click();
  };

  const clearTender = () => {
    setFile(null);
    setResult(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
    setProgress(0);
    onUploadComplete?.(null, null);
  };

  const uploadTender = async () => {
    if (!file) {
      alert("Please select a tender PDF");
      return;
    }

    try {
      setLoading(true);

      setProgress(0);

      const formData = new FormData();
      formData.append("file", file);

      const res = await API.post("/tenders/upload", formData, {
        headers: {
          "Content-Type": "multipart/form-data",
        },
        onUploadProgress: (progressEvent) => {
          if (progressEvent.total) {
            const percentCompleted = Math.round((progressEvent.loaded * 100) / progressEvent.total);
            setProgress(percentCompleted);
          }
        },
      });

      setResult(res.data);
      onUploadComplete?.(res.data?.document_id ?? null, res.data);
    } catch (error) {
      console.error(error);
      alert("Tender upload failed");
    } finally {
      setLoading(false);
      setProgress(0);
    }
  };

  return (
    <div className="space-y-4">
      <input
        ref={fileInputRef}
        type="file"
        accept=".pdf"
        onChange={(e) => {
          setFile(e.target.files?.[0] || null);
          setResult(null);
          onUploadComplete?.(null, null);
        }}
        className="hidden"
      />

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <button
          type="button"
          onClick={handlePickFile}
          className="w-full rounded-lg border border-gray-500 bg-gray-700 px-4 py-3 text-white hover:bg-gray-600"
        >
          {file ? "Change Tender File" : "Choose Tender File"}
        </button>

        <button
          type="button"
          onClick={clearTender}
          disabled={!file && !result}
          className="w-full rounded-lg border border-red-400 bg-transparent px-4 py-3 text-red-300 hover:bg-red-500/10 disabled:cursor-not-allowed disabled:opacity-40"
        >
          Clear
        </button>
      </div>

      {file && (
        <div className="rounded-lg bg-gray-700 p-3 text-sm">
          <p><strong>Selected:</strong> {file.name}</p>
        </div>
      )}

      <button
        onClick={uploadTender}
        disabled={loading}
        className="w-full relative overflow-hidden rounded-lg bg-green-600 px-4 py-3 text-white hover:bg-green-700 disabled:opacity-50"
      >
        {loading && (
          <div 
            className="absolute left-0 top-0 h-full bg-green-500/50 transition-all duration-300"
            style={{ width: `${progress === 0 ? 10 : progress}%` }}
          ></div>
        )}
        <span className="relative z-10 flex items-center justify-center gap-2">
          {loading ? (
            <>
              <span className="animate-spin text-lg">⏳</span>
              <span>{progress < 100 ? `Uploading... ${progress}%` : "AI Processing..."}</span>
            </>
          ) : (
            file ? "Upload Tender" : "Choose Tender"
          )}
        </span>
      </button>

      {result && (
        <div className="rounded-lg bg-gray-700 p-3 text-sm">
          <p><strong>Message:</strong> {result.message}</p>
          <p><strong>Status:</strong> {result.status}</p>
          <p><strong>Chunks:</strong> {result.chunks}</p>
          <p><strong>Stored Chunks:</strong> {result.stored_chunks}</p>
          {result.review_status && <p><strong>Review Status:</strong> {result.review_status}</p>}
          {result.extraction_confidence !== undefined && (
            <p><strong>Extraction Confidence:</strong> {result.extraction_confidence}</p>
          )}
          {result.review_task_id && <p><strong>Review Task:</strong> #{result.review_task_id}</p>}
          {result.pages !== undefined && <p><strong>Pages:</strong> {result.pages}</p>}
          {result.extraction_backend && (
            <p><strong>Extraction Backend:</strong> {result.extraction_backend}</p>
          )}
        </div>
      )}
    </div>
  );
}
