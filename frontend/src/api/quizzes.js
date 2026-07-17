import { request } from "./request";

export function createQuizSession(payload) {
  return request.post("/quizzes/sessions", payload, { timeout: 30000 });
}

export function getQuizSession(sessionId) {
  return request.get(`/quizzes/sessions/${sessionId}`);
}

export function submitQuizSession(sessionId, payload) {
  return request.post(`/quizzes/sessions/${sessionId}/submit`, payload, {
    timeout: 30000,
  });
}

export function abandonQuizSession(sessionId) {
  return request.delete(`/quizzes/sessions/${sessionId}`);
}
