"use client";

// 빠른 의사결정 보드 — 안건 생성, 투표, 방장 확정.

import { useState } from "react";

import type { Decision } from "@/lib/workspace-tools-api";

const MIN_OPTIONS = 2;
const MAX_OPTIONS = 5;

export function DecisionBoard({
  decisions,
  isHost,
  pendingAction,
  onCreate,
  onVote,
  onFinalize,
}: {
  decisions: Decision[];
  isHost: boolean;
  pendingAction: string | null;
  onCreate: (input: { title: string; description: string; options: string[] }) => void;
  onVote: (decisionId: string, optionId: string) => void;
  onFinalize: (decisionId: string, optionId: string) => void;
}) {
  const [creating, setCreating] = useState(false);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [options, setOptions] = useState(["", ""]);

  const resetForm = () => {
    setTitle("");
    setDescription("");
    setOptions(["", ""]);
    setCreating(false);
  };

  return (
    <div className="workspace-panel" aria-label="빠른 의사결정 보드">
      <h2>빠른 의사결정 보드</h2>

      {decisions.length === 0 ? (
        <p className="workspace-empty">아직 등록된 안건이 없어요.</p>
      ) : (
        <ul className="workspace-decision-list">
          {decisions.map((decision) => {
            const maxVotes = Math.max(1, ...decision.options.map((o) => o.vote_count));
            const finalized = decision.status === "FINALIZED";
            return (
              <li key={decision.id} className="workspace-decision-card">
                {finalized && (
                  <span className="workspace-decision-final-badge">
                    최종 결정: {decision.options.find((o) => o.id === decision.finalized_option_id)?.label ?? "-"}
                  </span>
                )}
                <b className="workspace-decision-title">{decision.title}</b>
                {decision.description && <p className="workspace-decision-description">{decision.description}</p>}
                <ul className="workspace-decision-options">
                  {decision.options.map((option) => {
                    const isMine = decision.my_vote_option_id === option.id;
                    const barWidth = Math.round((option.vote_count / maxVotes) * 100);
                    return (
                      <li
                        key={option.id}
                        className={isMine ? "workspace-decision-option workspace-decision-option-mine" : "workspace-decision-option"}
                      >
                        <div className="workspace-decision-option-row">
                          <span className="workspace-decision-option-label">{option.label}</span>
                          <span className="workspace-decision-option-count">{option.vote_count}표</span>
                        </div>
                        <div className="workspace-progress-bar" aria-hidden="true">
                          <div className="workspace-progress-fill" style={{ width: `${barWidth}%` }} />
                        </div>
                        <div className="workspace-decision-option-actions">
                          <button
                            type="button"
                            className={isMine ? "task-status-active" : "task-status-button"}
                            disabled={finalized || pendingAction === `vote-${decision.id}`}
                            onClick={() => onVote(decision.id, option.id)}
                          >
                            {isMine ? "투표함" : "투표"}
                          </button>
                          {isHost && !finalized && (
                            <button
                              type="button"
                              className="button-muted"
                              disabled={pendingAction === `finalize-${decision.id}`}
                              onClick={() => onFinalize(decision.id, option.id)}
                            >
                              이 선택지로 확정
                            </button>
                          )}
                        </div>
                      </li>
                    );
                  })}
                </ul>
              </li>
            );
          })}
        </ul>
      )}

      {creating ? (
        <form
          className="workspace-decision-create-form"
          onSubmit={(event) => {
            event.preventDefault();
            const trimmedOptions = options.map((o) => o.trim()).filter(Boolean);
            if (!title.trim() || trimmedOptions.length < MIN_OPTIONS) return;
            onCreate({ title: title.trim(), description: description.trim(), options: trimmedOptions });
            resetForm();
          }}
        >
          <input value={title} onChange={(event) => setTitle(event.target.value)} placeholder="안건 제목" aria-label="안건 제목" />
          <textarea
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            placeholder="안건 설명"
            aria-label="안건 설명"
            rows={2}
          />
          {options.map((option, index) => (
            <input
              key={index}
              value={option}
              onChange={(event) =>
                setOptions((current) => current.map((o, i) => (i === index ? event.target.value : o)))
              }
              placeholder={`선택지 ${index + 1}`}
              aria-label={`선택지 ${index + 1}`}
            />
          ))}
          <div className="workspace-decision-option-buttons">
            <button
              type="button"
              className="button-muted"
              disabled={options.length >= MAX_OPTIONS}
              onClick={() => setOptions((current) => [...current, ""])}
            >
              선택지 추가
            </button>
            <button
              type="button"
              className="button-muted"
              disabled={options.length <= MIN_OPTIONS}
              onClick={() => setOptions((current) => current.slice(0, -1))}
            >
              선택지 제거
            </button>
          </div>
          <div className="workspace-notice-form-actions">
            <button
              type="submit"
              className="button-next"
              disabled={pendingAction === "create-decision" || !title.trim() || options.filter((o) => o.trim()).length < MIN_OPTIONS}
            >
              안건 생성
            </button>
            <button type="button" className="button-muted" onClick={resetForm}>
              취소
            </button>
          </div>
        </form>
      ) : (
        <button type="button" className="button-muted" onClick={() => setCreating(true)}>
          새 안건 만들기
        </button>
      )}
    </div>
  );
}
