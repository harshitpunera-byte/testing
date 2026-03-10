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

export const matchResumes = (tenderText) =>
  API.post("/match/", { tender_text: tenderText });

export default API;
