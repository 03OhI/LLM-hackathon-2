import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { FocusTimer } from "../FocusTimer";

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
});

afterEach(() => {
  vi.useRealTimers();
});

describe("FocusTimer", () => {
  it("기본값은 25:00 집중 모드로 시작한다", () => {
    render(<FocusTimer />);
    expect(screen.getByText("25:00")).toBeInTheDocument();
    expect(screen.getByText("집중 25분 진행 중")).toBeInTheDocument();
  });

  it("모드를 바꾸면 프리셋 시간으로 즉시 바뀐다", () => {
    render(<FocusTimer />);
    fireEvent.click(screen.getByRole("button", { name: "회의 10분" }));
    expect(screen.getByText("10:00")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "휴식 5분" }));
    expect(screen.getByText("05:00")).toBeInTheDocument();
  });

  it("시작하면 1초마다 카운트다운되고, 일시정지하면 멈춘다", async () => {
    render(<FocusTimer />);
    fireEvent.click(screen.getByRole("button", { name: "시작" }));

    await vi.advanceTimersByTimeAsync(3000);
    expect(screen.getByText("24:57")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "일시정지" }));
    await vi.advanceTimersByTimeAsync(3000);
    expect(screen.getByText("24:57")).toBeInTheDocument();
  });

  it("초기화하면 현재 모드의 프리셋 시간으로 되돌아간다", async () => {
    render(<FocusTimer />);
    fireEvent.click(screen.getByRole("button", { name: "시작" }));
    await vi.advanceTimersByTimeAsync(5000);

    fireEvent.click(screen.getByRole("button", { name: "초기화" }));
    expect(screen.getByText("25:00")).toBeInTheDocument();
  });

  it("시간이 0에 도달하면 완료 메시지를 보여준다", async () => {
    render(<FocusTimer />);
    fireEvent.click(screen.getByRole("button", { name: "휴식 5분" }));
    fireEvent.click(screen.getByRole("button", { name: "시작" }));

    await vi.advanceTimersByTimeAsync(5 * 60 * 1000);

    expect(screen.getByText("00:00")).toBeInTheDocument();
    expect(screen.getByText("휴식 5분이 끝났어요!")).toBeInTheDocument();
  });
});
