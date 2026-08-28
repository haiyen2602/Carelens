"use client";

import { useEffect, useRef, useState, useCallback } from "react";

export type RealtimeStatus = "connected" | "connecting" | "disconnected" | "disabled";

interface UseMonitoringRealtimeOptions {
  accessToken?: string | null;
  enabled?: boolean;
  debounceMs?: number;
  onUpdate?: () => void;
}

export function useMonitoringRealtime({
  accessToken,
  enabled = true,
  debounceMs = 1500,
  onUpdate,
}: UseMonitoringRealtimeOptions) {
  const [isLive, setIsLive] = useState(enabled);
  const [status, setStatus] = useState<RealtimeStatus>(enabled ? "connecting" : "disabled");
  const [lastEventAt, setLastEventAt] = useState<Date | null>(null);

  const debounceTimerRef = useRef<NodeJS.Timeout | null>(null);
  const onUpdateRef = useRef(onUpdate);
  onUpdateRef.current = onUpdate;

  const triggerUpdate = useCallback(() => {
    if (debounceTimerRef.current) {
      clearTimeout(debounceTimerRef.current);
    }
    debounceTimerRef.current = setTimeout(() => {
      onUpdateRef.current?.();
    }, debounceMs);
  }, [debounceMs]);

  useEffect(() => {
    if (!isLive || !accessToken) {
      setStatus(isLive ? "disconnected" : "disabled");
      return;
    }

    let isAborted = false;
    let abortController = new AbortController();
    let retryTimeout: NodeJS.Timeout | null = null;
    let retryDelay = 2000;

    const connect = async () => {
      if (isAborted) return;
      setStatus("connecting");
      abortController = new AbortController();

      const apiBase = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
      const url = `${apiBase}/api/v1/admin/monitoring/stream`;

      try {
        const response = await fetch(url, {
          headers: {
            Authorization: `Bearer ${accessToken}`,
            Accept: "text/event-stream",
          },
          signal: abortController.signal,
        });

        if (!response.ok || !response.body) {
          throw new Error(`SSE stream connection failed (${response.status})`);
        }

        setStatus("connected");
        retryDelay = 2000; // reset retry delay on successful connection

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        while (!isAborted) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const parts = buffer.split("\n\n");
          buffer = parts.pop() ?? "";

          for (const block of parts) {
            if (!block.trim()) continue;

            const lines = block.split("\n");
            let eventName = "message";
            let dataStr = "";

            for (const line of lines) {
              if (line.startsWith("event:")) {
                eventName = line.slice(6).trim();
              } else if (line.startsWith("data:")) {
                dataStr = line.slice(5).trim();
              }
            }

            if (eventName === "ping") {
              // Heartbeat keep-alive
              continue;
            }

            if (eventName === "agent_run_completed" || eventName === "metrics_updated" || eventName === "connected") {
              if (eventName !== "connected") {
                setLastEventAt(new Date());
                triggerUpdate();
              }
            }
          }
        }
      } catch (err: unknown) {
        if (!isAborted) {
          const isAbortError = err instanceof Error && err.name === "AbortError";
          if (!isAbortError) {
            setStatus("connecting");
            retryTimeout = setTimeout(() => {
              retryDelay = Math.min(retryDelay * 1.5, 15000);
              connect();
            }, retryDelay);
          }
        }
      }
    };

    connect();

    return () => {
      isAborted = true;
      abortController.abort();
      if (retryTimeout) clearTimeout(retryTimeout);
      if (debounceTimerRef.current) clearTimeout(debounceTimerRef.current);
    };
  }, [isLive, accessToken, triggerUpdate]);

  const toggleLive = useCallback(() => {
    setIsLive((prev) => !prev);
  }, []);

  return {
    isLive,
    setIsLive,
    toggleLive,
    status,
    lastEventAt,
  };
}
