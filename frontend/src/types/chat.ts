// Mirrors src/models/schemas.py (ChatRequest / ChatResponse) on the backend.
export type ChatRequest = {
  message: string;
};

export type ChatResponse = {
  response: string;
  analysis: string;
};

export type AgentStatus = {
  status: string;
  agent: string;
};

export type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
};
