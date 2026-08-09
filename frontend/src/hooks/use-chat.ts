import { useMutation, useQuery } from "@tanstack/react-query";
import { getAgentStatus, sendChatMessage } from "@/lib/api";

export function useChatMessage() {
  return useMutation({
    mutationFn: sendChatMessage,
  });
}

export function useAgentStatus() {
  return useQuery({
    queryKey: ["agent-status"],
    queryFn: getAgentStatus,
    retry: false,
  });
}
