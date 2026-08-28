"use client";

import { useEffect, useRef } from "react";

// enabled가 true인 동안 intervalMs마다 refresh를 호출한다. 요청이 겹치면 건너뛰고,
// 언마운트되거나 enabled가 false가 되면 반드시 정리한다.
export function usePolling(refresh: () => Promise<void>, intervalMs: number, enabled: boolean) {
  const inFlight = useRef(false);
  const latestRefresh = useRef(refresh);

  useEffect(() => {
    latestRefresh.current = refresh;
  }, [refresh]);

  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;

    const tick = async () => {
      if (cancelled || inFlight.current) return;
      inFlight.current = true;
      try {
        await latestRefresh.current();
      } finally {
        inFlight.current = false;
      }
    };

    const id = window.setInterval(tick, intervalMs);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [enabled, intervalMs]);
}
