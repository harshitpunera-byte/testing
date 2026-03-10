import { useRef, useState } from "react";
import API from "../api/api";

export default function ResumeUpload() {
  const fileInputRef = useRef(null);

  const [files, setFiles] = useState([]);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);

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
  };

  const removeFile = (indexToRemove) => {
    setFiles((prevFiles) =>
      prevFiles.filter((_, index) => index !== indexToRemove)
    );
  };

  const clearAllFiles = () => {
    setFiles([]);
    setResult(null);
  };

  const uploadResumes = async () => {
    if (!files.length) {
      alert("Please select at least one resume PDF");
      return;
    }

    try {
      setLoading(true);

      const formData = new FormData();

      if (files.length === 1) {
        formData.append("file", files[0]);

        const res = await API.post("/resumes/upload", formData, {
          headers: {
            "Content-Type": "multipart/form-data",
          },
        });

        setResult(res.data);
      } else {
        files.forEach((file) => {
          formData.append("files", file);
        });

        const res = await API.post("/resumes/upload-multiple", formData, {
          headers: {
            "Content-Type": "multipart/form-data",
          },
        });

        setResult(res.data);
      }
    } catch (error) {
      console.error(error);
      alert("Resume upload failed");
    } finally {
      setLoading(false);
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
          disabled={!files.length}
          className="w-full rounded-lg border border-red-400 bg-transparent px-4 py-3 text-red-300 hover:bg-red-500/10 disabled:cursor-not-allowed disabled:opacity-40"
        >
          Clear All
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
        className="w-full rounded-lg bg-blue-600 px-4 py-3 text-white hover:bg-blue-700 disabled:opacity-50"
      >
        {loading
          ? "Uploading..."
          : files.length > 1
          ? "Upload Resumes"
          : "Upload Resume"}
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
                        {item.filename} — chunks: {item.chunks}, stored: {item.stored_chunks}
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