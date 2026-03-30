import axios from "axios";

const API = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000",
});

export const uploadResume = (file) => {
  const formData = new FormData();
  formData.append("file", file);
  return API.post("/resumes/upload", formData);
};

export const uploadResumes = (files) => {
  const formData = new FormData();
  files.forEach((file) => {
    formData.append("files", file);
  });
  return API.post("/resumes/upload-multiple", formData);
};

export const uploadTender = (file) => {
  const formData = new FormData();
  formData.append("file", file);
  return API.post("/tenders/upload", formData);
};

export const getDocumentFileUrl = (documentId) => {
  const baseUrl = String(API.defaults.baseURL || "").replace(/\/$/, "");
  return `${baseUrl}/documents/${documentId}/file`;
};

export const matchResumes = (tenderText) =>
  API.post("/match/", { tender_text: tenderText });

export const getReviewTasks = (params = {}) => API.get("/reviews", { params });

export const getReviewTask = (taskId) => API.get(`/reviews/${taskId}`);

export const approveReviewTask = (taskId, payload = {}) =>
  API.post(`/reviews/${taskId}/approve`, payload);

export const correctReviewTask = (taskId, payload = {}) =>
  API.post(`/reviews/${taskId}/correct`, payload);

export const rejectReviewTask = (taskId, payload = {}) =>
  API.post(`/reviews/${taskId}/reject`, payload);

export const approveTenderCriteria = (documentId, payload = {}) =>
  API.post(`/tenders/${documentId}/approve-criteria`, payload);

export const submitMatchFeedback = (payload = {}) =>
  API.post("/match/feedback", payload);

export default API;
