import { renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { usePolling } from "../use-polling";

describe("usePolling", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("intervalMs마다 refresh를 호출한다", async () => {
    const refresh = vi.fn().mockResolvedValue(undefined);
    renderHook(() => usePolling(refresh, 1000, true));

    await vi.advanceTimersByTimeAsync(1000);
    await vi.advanceTimersByTimeAsync(1000);

    expect(refresh).toHaveBeenCalledTimes(2);
  });

  it("enabled가 false면 아예 호출하지 않는다", async () => {
    const refresh = vi.fn().mockResolvedValue(undefined);
    renderHook(() => usePolling(refresh, 1000, false));

    await vi.advanceTimersByTimeAsync(5000);

    expect(refresh).not.toHaveBeenCalled();
  });

  it("언마운트되면 폴링을 정리한다", async () => {
    const refresh = vi.fn().mockResolvedValue(undefined);
    const { unmount } = renderHook(() => usePolling(refresh, 1000, true));

    await vi.advanceTimersByTimeAsync(1000);
    expect(refresh).toHaveBeenCalledTimes(1);

    unmount();
    await vi.advanceTimersByTimeAsync(5000);

    expect(refresh).toHaveBeenCalledTimes(1);
  });

  it("이전 요청이 아직 진행 중이면 겹쳐서 호출하지 않는다", async () => {
    let resolveFirst: () => void = () => {};
    const refresh = vi.fn().mockImplementation(
      () =>
        new Promise<void>((resolve) => {
          resolveFirst = resolve;
        }),
    );
    renderHook(() => usePolling(refresh, 1000, true));

    await vi.advanceTimersByTimeAsync(1000);
    await vi.advanceTimersByTimeAsync(1000);
    expect(refresh).toHaveBeenCalledTimes(1);

    resolveFirst();
    await vi.advanceTimersByTimeAsync(0);
    await vi.advanceTimersByTimeAsync(1000);
    expect(refresh).toHaveBeenCalledTimes(2);
  });
});
