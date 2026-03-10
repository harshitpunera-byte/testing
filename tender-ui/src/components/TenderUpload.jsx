import { useRef, useState } from "react";
import API from "../api/api";

export default function TenderUpload() {
  const fileInputRef = useRef(null);

  const [file, setFile] = useState(null);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);

  const handlePickFile = () => {
    fileInputRef.current?.click();
  };

  const uploadTender = async () => {
    if (!file) {
      alert("Please select a tender PDF");
      return;
    }

    try {
      setLoading(true);

      const formData = new FormData();
      formData.append("file", file);

      const res = await API.post("/tenders/upload", formData, {
        headers: {
          "Content-Type": "multipart/form-data",
        },
      });

      setResult(res.data);
    } catch (error) {
      console.error(error);
      alert("Tender upload failed");
    } finally {
      setLoading(false);
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
        }}
        className="hidden"
      />

      <button
        type="button"
        onClick={handlePickFile}
        className="w-full rounded-lg border border-gray-500 bg-gray-700 px-4 py-3 text-white hover:bg-gray-600"
      >
        {file ? "Change Tender File" : "Choose Tender File"}
      </button>

      {file && (
        <div className="rounded-lg bg-gray-700 p-3 text-sm">
          <p><strong>Selected:</strong> {file.name}</p>
        </div>
      )}

      <button
        onClick={uploadTender}
        disabled={loading}
        className="w-full rounded-lg bg-green-600 px-4 py-3 text-white hover:bg-green-700 disabled:opacity-50"
      >
        {loading ? "Uploading..." : "Upload Tender"}
      </button>

      {result && (
        <div className="rounded-lg bg-gray-700 p-3 text-sm">
          <p><strong>Message:</strong> {result.message}</p>
          <p><strong>Chunks:</strong> {result.chunks}</p>
          <p><strong>Stored Chunks:</strong> {result.stored_chunks}</p>
        </div>
      )}
    </div>
  );
}