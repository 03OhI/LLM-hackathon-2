import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { Decision } from "@/lib/workspace-tools-api";
import { DecisionBoard } from "../DecisionBoard";

function makeDecision(overrides: Partial<Decision> = {}): Decision {
  return {
    id: "decision-1",
    title: "서비스명 정하기",
    description: "최종 이름을 정해요.",
    options: [
      { id: "opt-1", label: "TMTI", vote_count: 2 },
      { id: "opt-2", label: "ChemLink", vote_count: 1 },
    ],
    status: "OPEN",
    finalized_option_id: null,
    my_vote_option_id: null,
    created_by: "host",
    created_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

describe("DecisionBoard", () => {
  it("내가 투표한 선택지는 강조되고 '투표함'으로 표시된다", () => {
    render(
      <DecisionBoard
        decisions={[makeDecision({ my_vote_option_id: "opt-1" })]}
        isHost={false}
        pendingAction={null}
        onCreate={vi.fn()}
        onVote={vi.fn()}
        onFinalize={vi.fn()}
      />,
    );

    const votedButton = screen.getByRole("button", { name: "투표함" });
    expect(votedButton).toBeInTheDocument();
    expect(votedButton.closest("li")?.className).toContain("workspace-decision-option-mine");
  });

  it("투표 버튼을 누르면 onVote가 호출된다", () => {
    const onVote = vi.fn();
    render(
      <DecisionBoard
        decisions={[makeDecision()]}
        isHost={false}
        pendingAction={null}
        onCreate={vi.fn()}
        onVote={onVote}
        onFinalize={vi.fn()}
      />,
    );

    fireEvent.click(screen.getAllByRole("button", { name: "투표" })[0]);
    expect(onVote).toHaveBeenCalledWith("decision-1", "opt-1");
  });

  it("방장에게만 확정 버튼이 보인다", () => {
    const { rerender } = render(
      <DecisionBoard
        decisions={[makeDecision()]}
        isHost={false}
        pendingAction={null}
        onCreate={vi.fn()}
        onVote={vi.fn()}
        onFinalize={vi.fn()}
      />,
    );
    expect(screen.queryByRole("button", { name: "이 선택지로 확정" })).not.toBeInTheDocument();

    rerender(
      <DecisionBoard
        decisions={[makeDecision()]}
        isHost
        pendingAction={null}
        onCreate={vi.fn()}
        onVote={vi.fn()}
        onFinalize={vi.fn()}
      />,
    );
    expect(screen.getAllByRole("button", { name: "이 선택지로 확정" }).length).toBeGreaterThan(0);
  });

  it("확정된 안건은 최종 결과 배지를 보여주고 투표 버튼이 비활성화된다", () => {
    render(
      <DecisionBoard
        decisions={[makeDecision({ status: "FINALIZED", finalized_option_id: "opt-1" })]}
        isHost
        pendingAction={null}
        onCreate={vi.fn()}
        onVote={vi.fn()}
        onFinalize={vi.fn()}
      />,
    );

    expect(screen.getByText("최종 결정: TMTI")).toBeInTheDocument();
    for (const button of screen.getAllByRole("button", { name: /^투표/ })) {
      expect(button).toBeDisabled();
    }
    expect(screen.queryByRole("button", { name: "이 선택지로 확정" })).not.toBeInTheDocument();
  });

  it("안건을 만들 때 선택지는 2~5개로 제한된다", () => {
    render(
      <DecisionBoard
        decisions={[]}
        isHost
        pendingAction={null}
        onCreate={vi.fn()}
        onVote={vi.fn()}
        onFinalize={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "새 안건 만들기" }));
    expect(screen.getByRole("button", { name: "선택지 제거" })).toBeDisabled();

    const addButton = screen.getByRole("button", { name: "선택지 추가" });
    fireEvent.click(addButton);
    fireEvent.click(addButton);
    fireEvent.click(addButton);
    expect(addButton).toBeDisabled();
    expect(screen.getAllByPlaceholderText(/선택지 \d/)).toHaveLength(5);
  });
});
