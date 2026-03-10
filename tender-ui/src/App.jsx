import ResumeUpload from "./components/ResumeUpload";
import TenderUpload from "./components/TenderUpload";
import AskAgent from "./components/AskAgent";

function App() {
  return (
    <div className="min-h-screen bg-gray-900 text-white">
      <div className="bg-gray-800 border-b border-gray-700 p-6">
        <h1 className="text-3xl font-bold">Tender AI Matching System</h1>
        <p className="text-gray-400 mt-1">
          Upload tender PDF, upload one or many resumes, and find the best candidates.
        </p>
      </div>

      <div className="p-8 grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="bg-gray-800 rounded-xl p-6 shadow-lg">
          <h2 className="text-xl font-semibold mb-4">Upload Resumes</h2>
          <ResumeUpload />
        </div>

        <div className="bg-gray-800 rounded-xl p-6 shadow-lg">
          <h2 className="text-xl font-semibold mb-4">Upload Tender</h2>
          <TenderUpload />
        </div>

        <div className="bg-gray-800 rounded-xl p-6 shadow-lg">
          <h2 className="text-xl font-semibold mb-4">Ask AI</h2>
          <AskAgent />
        </div>
      </div>
    </div>
  );
}

export default App;