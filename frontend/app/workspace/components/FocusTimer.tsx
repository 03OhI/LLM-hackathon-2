"use client";

// 집중·회의 타이머 — 백엔드 API를 쓰지 않는 순수 브라우저 상태.
// 페이지를 이동(언마운트)하면 그대로 초기화된다 — 의도된 동작이라 저장하지 않는다.
// 알림 권한/소리는 구현하지 않는다(요구사항).

import { useEffect, useRef, useState } from "react";

type TimerMode = "FOCUS" | "MEETING" | "BREAK";

const MODE_SECONDS: Record<TimerMode, number> = {
  FOCUS: 25 * 60,
  MEETING: 10 * 60,
  BREAK: 5 * 60,
};

const MODE_LABEL: Record<TimerMode, string> = {
  FOCUS: "집중 25분",
  MEETING: "회의 10분",
  BREAK: "휴식 5분",
};

function formatClock(totalSeconds: number): string {
  const clamped = Math.max(0, totalSeconds);
  const minutes = Math.floor(clamped / 60);
  const seconds = clamped % 60;
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}

export function FocusTimer() {
  const [mode, setMode] = useState<TimerMode>("FOCUS");
  const [remainingSeconds, setRemainingSeconds] = useState(MODE_SECONDS.FOCUS);
  const [running, setRunning] = useState(false);
  const [finished, setFinished] = useState(false);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (!running) return;
    intervalRef.current = setInterval(() => {
      setRemainingSeconds((current) => {
        if (current <= 1) {
          setRunning(false);
          setFinished(true);
          return 0;
        }
        return current - 1;
      });
    }, 1000);
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [running]);

  const selectMode = (nextMode: TimerMode) => {
    setMode(nextMode);
    setRunning(false);
    setFinished(false);
    setRemainingSeconds(MODE_SECONDS[nextMode]);
  };

  const start = () => {
    if (remainingSeconds <= 0) return;
    setFinished(false);
    setRunning(true);
  };

  const pause = () => setRunning(false);

  const reset = () => {
    setRunning(false);
    setFinished(false);
    setRemainingSeconds(MODE_SECONDS[mode]);
  };

  return (
    <section className="workspace-timer workspace-span-2" aria-label="집중·회의 타이머">
      <div className="workspace-timer-modes" role="group" aria-label="타이머 모드">
        {(Object.keys(MODE_SECONDS) as TimerMode[]).map((item) => (
          <button
            key={item}
            type="button"
            className={mode === item ? "workspace-timer-mode-active" : "workspace-timer-mode"}
            onClick={() => selectMode(item)}
          >
            {MODE_LABEL[item]}
          </button>
        ))}
      </div>
      <div className="workspace-timer-display">
        <span className="workspace-timer-clock">{formatClock(remainingSeconds)}</span>
        <span className="workspace-timer-current-mode">{MODE_LABEL[mode]} 진행 중</span>
      </div>
      <div className="workspace-timer-controls">
        {running ? (
          <button type="button" className="button-muted" onClick={pause}>
            일시정지
          </button>
        ) : (
          <button type="button" className="button-next" onClick={start} disabled={remainingSeconds <= 0}>
            시작
          </button>
        )}
        <button type="button" className="button-muted" onClick={reset}>
          초기화
        </button>
      </div>
      {finished && <p className="workspace-timer-done">{MODE_LABEL[mode]}이 끝났어요!</p>}
    </section>
  );
}
