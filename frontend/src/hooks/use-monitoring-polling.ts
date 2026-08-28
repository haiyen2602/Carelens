"use client";

import { useEffect, useRef, useState, useCallback } from "react";

export type PollingIntervalOption = 0 | 5000 | 10000 | 30000 | 60000;

export const POLLING_OPTIONS: { label: string; value: PollingIntervalOption }[] = [
  { label: "Tự động: Tắt", value: 0 },
  { label: "5 giây", value: 5000 },
  { label: "10 giây (Mặc định)", value: 10000 },
  { label: "30 giây", value: 30000 },
  { label: "1 phút", value: 60000 },
];

interface UseMonitoringPollingOptions {
  defaultIntervalMs?: PollingIntervalOption;
  onUpdate?: () => void;
}

export function useMonitoringPolling({
  defaultIntervalMs = 10000,
  onUpdate,
}: UseMonitoringPollingOptions = {}) {
  const [intervalMs, setIntervalMs] = useState<PollingIntervalOption>(defaultIntervalMs);
  const [lastRefreshedAt, setLastRefreshedAt] = useState<Date>(() => new Date());

  const onUpdateRef = useRef(onUpdate);
  onUpdateRef.current = onUpdate;

  const triggerUpdate = useCallback(() => {
    onUpdateRef.current?.();
    setLastRefreshedAt(new Date());
  }, []);

  useEffect(() => {
    if (intervalMs <= 0) return;

    const timer = setInterval(() => {
      // Don't poll if document is hidden (user switched to another tab)
      if (typeof document !== "undefined" && document.hidden) {
        return;
      }
      triggerUpdate();
    }, intervalMs);

    // Refresh immediately when user returns to this tab if interval is active
    const handleVisibilityChange = () => {
      if (typeof document !== "undefined" && !document.hidden) {
        triggerUpdate();
      }
    };

    document.addEventListener("visibilitychange", handleVisibilityChange);

    return () => {
      clearInterval(timer);
      document.removeEventListener("visibilitychange", handleVisibilityChange);
    };
  }, [intervalMs, triggerUpdate]);

  return {
    intervalMs,
    setIntervalMs,
    lastRefreshedAt,
    isPollingActive: intervalMs > 0,
    triggerUpdate,
  };
}
