import { useRef, useState } from "react";
import API from "../api/api";

export default function ResumeUpload({ onUploadComplete }) {
  const fileInputRef = useRef(null);

  const [files, setFiles] = useState([]);
  const [loading, setLoading] = useState(false);
  const [progress, setProgress] = useState(0); // overall percentage
  const [currentFileIndex, setCurrentFileIndex] = useState(0); // which file is being processed
  const [result, setResult] = useState(null);

  const collectUploadedRecords = (payload) => {
    if (Array.isArray(payload?.processed)) {
      return payload.processed;
    }

    if (payload?.document_id) {
      return [payload];
    }

    return [];
  };

  const handlePickFiles = () => {
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
      fileInputRef.current.click();
    }
  };

  const handleFileChange = (e) => {
    const pickedFiles = Array.from(e.target.files || []);

    setFiles((prevFiles) => {
      const existingKeys = new Set(
        prevFiles.map((file) => `${file.name}-${file.size}`)
      );

      const uniqueNewFiles = pickedFiles.filter(
        (file) => !existingKeys.has(`${file.name}-${file.size}`)
      );

      return [...prevFiles, ...uniqueNewFiles];
    });

    setResult(null);
    onUploadComplete?.([], []);
  };

  const removeFile = (indexToRemove) => {
    setFiles((prevFiles) =>
      prevFiles.filter((_, index) => index !== indexToRemove)
    );
    setResult(null);
    onUploadComplete?.([], []);
  };

  const clearAllFiles = () => {
    setFiles([]);
    setResult(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
    setProgress(0);
    setCurrentFileIndex(0);
    onUploadComplete?.([], []);
  };

  const uploadResumes = async () => {
    if (!files.length) {
      alert("Please select at least one resume PDF");
      return;
    }
  
    try {
      setLoading(true);
      setResult(null);
      setProgress(0);
      setCurrentFileIndex(0);
  
      const allProcessed = [];
      const allFailed = [];
      const allDocumentIds = [];
  
      for (let i = 0; i < files.length; i++) {
        setCurrentFileIndex(i + 1);
        const file = files[i];
        const formData = new FormData();
        formData.append("file", file);
  
        try {
          // Individual file upload with its own progress handling
          // We don't bother showing byte progress for each file if there are many,
          // rather we show that the file is "uploading/processing" as a state.
          const res = await API.post("/resumes/upload", formData, {
            headers: {
              "Content-Type": "multipart/form-data",
            },
          });
  
          allProcessed.push({ ...res.data, filename: file.name, status: "stored" });
          if (res.data?.document_id) allDocumentIds.push(res.data.document_id);
        } catch (err) {
          allFailed.push({ filename: file.name, error: err.response?.data?.message || err.message });
        }
  
        // Calculate and update overall progress based on file count
        const overallProgress = Math.round(((i + 1) * 100) / files.length);
        setProgress(overallProgress);
      }
  
      const combinedResult = {
        message: "Bulk upload finished",
        total_files: files.length,
        processed_files: allProcessed.length,
        failed_files: allFailed.length,
        processed: allProcessed,
        failed: allFailed,
      };
  
      setResult(combinedResult);
      onUploadComplete?.(allDocumentIds, allProcessed);
    } catch (error) {
      console.error(error);
      alert("Resume upload process failed unexpectedly");
    } finally {
      setLoading(false);
      // Wait a moment then reset the index, but keep progress at 100 for visual finish
      setTimeout(() => setProgress(0), 2000);
    }
  };

  return (
    <div className="space-y-4">
      <input
        ref={fileInputRef}
        type="file"
        multiple
        accept=".pdf"
        onChange={handleFileChange}
        className="hidden"
      />

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <button
          type="button"
          onClick={handlePickFiles}
          className="w-full rounded-lg border border-gray-500 bg-gray-700 px-4 py-3 text-white hover:bg-gray-600"
        >
          {files.length > 0 ? "Add More" : "Choose Resume Files"}
        </button>

        <button
          type="button"
          onClick={clearAllFiles}
          disabled={!files.length && !result}
          className="w-full rounded-lg border border-red-400 bg-transparent px-4 py-3 text-red-300 hover:bg-red-500/10 disabled:cursor-not-allowed disabled:opacity-40"
        >
          Clear
        </button>
      </div>

      {files.length > 0 && (
        <div className="rounded-lg bg-gray-700 p-3 text-sm">
          <p className="mb-2 font-medium text-green-300">
            {files.length} resume(s) selected
          </p>

          <ul className="max-h-48 space-y-2 overflow-auto text-gray-300">
            {files.map((file, index) => (
              <li
                key={`${file.name}-${file.size}-${index}`}
                className="flex items-center justify-between rounded bg-gray-800 px-3 py-2"
              >
                <span className="mr-3 truncate">{file.name}</span>

                <button
                  type="button"
                  onClick={() => removeFile(index)}
                  className="rounded bg-red-500 px-2 py-1 text-xs text-white hover:bg-red-600"
                >
                  Remove
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}

      <button
        onClick={uploadResumes}
        disabled={loading || !files.length}
        className="w-full relative overflow-hidden rounded-lg bg-blue-600 px-4 py-3 text-white hover:bg-blue-700 disabled:opacity-50"
      >
        {loading && (
          <div 
            className="absolute left-0 top-0 h-full bg-blue-400/50 transition-all duration-300"
            style={{ width: `${progress}%` }}
          ></div>
        )}
        <span className="relative z-10 flex items-center justify-center gap-2">
          {loading ? (
            <>
              <span className="animate-spin text-lg">⏳</span>
              <span>{`Processing: ${currentFileIndex}/${files.length} (${progress}%)`}</span>
            </>
          ) : (
            files.length > 1 ? "Upload All Resumes" : "Upload Resume"
          )}
        </span>
      </button>

      {result && (
        <div className="rounded-lg bg-gray-700 p-3 text-sm space-y-2">
          <p className="font-semibold">Upload Result</p>

          {result.message && <p>{result.message}</p>}

          {result.filename && (
            <div>
              <p><strong>File:</strong> {result.filename}</p>
              <p><strong>Chunks:</strong> {result.chunks}</p>
              <p><strong>Stored Chunks:</strong> {result.stored_chunks}</p>
              {result.review_status && <p><strong>Review Status:</strong> {result.review_status}</p>}
              {result.extraction_confidence !== undefined && (
                <p><strong>Extraction Confidence:</strong> {result.extraction_confidence}</p>
              )}
              {result.review_task_id && <p><strong>Review Task:</strong> #{result.review_task_id}</p>}
            </div>
          )}

          {result.total_files !== undefined && (
            <div className="space-y-2">
              <p><strong>Total Files:</strong> {result.total_files}</p>
              <p><strong>Processed:</strong> {result.processed_files}</p>
              <p><strong>Failed:</strong> {result.failed_files}</p>

              {result.processed?.length > 0 && (
                <div>
                  <p className="mb-1 font-medium">Processed Files</p>
                  <ul className="max-h-40 space-y-1 overflow-auto">
                    {result.processed.map((item, index) => (
                      <li key={index}>
                        {item.filename} — status: {item.status}, chunks: {item.chunks}, stored: {item.stored_chunks}, review: {item.review_status || "n/a"}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {result.failed?.length > 0 && (
                <div>
                  <p className="mb-1 font-medium text-red-300">Failed Files</p>
                  <ul className="max-h-40 space-y-1 overflow-auto">
                    {result.failed.map((item, index) => (
                      <li key={index}>
                        {item.filename} — error: {item.error}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
