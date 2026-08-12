import { useMutation, useQuery } from "@tanstack/react-query";
import { getAgentStatus, sendChatMessage } from "@/lib/api";
import type { ChatRequest } from "@/types/chat";

// TASK-010: accessToken (tu useAuth(), frontend/src/lib/auth.tsx) duoc
// closure vao mutationFn thay vi truyen qua tham so cua mutate() - useMutation
// chi nhan 1 tham so "variables" khop kieu mutationFn, khong ho tro tham so
// phu per-call.
export function useChatMessage(accessToken?: string | null) {
  return useMutation({
    mutationFn: (payload: ChatRequest) => sendChatMessage(payload, accessToken),
  });
}

export function useAgentStatus() {
  return useQuery({
    queryKey: ["agent-status"],
    queryFn: getAgentStatus,
    retry: false,
  });
}
