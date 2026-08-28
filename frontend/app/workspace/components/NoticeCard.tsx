"use client";

// 고정 공지 카드 — 상단 전체 너비. 방장에게만 편집 버튼을 보여준다.

import { useEffect, useState } from "react";

import type { WorkspaceNotice } from "@/lib/workspace-tools-api";

function formatDeadline(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return `${date.getMonth() + 1}/${date.getDate()} ${String(date.getHours()).padStart(2, "0")}:${String(
    date.getMinutes(),
  ).padStart(2, "0")}`;
}

function formatRemaining(deadlineIso: string, now: number): string {
  const deadline = new Date(deadlineIso).getTime();
  if (Number.isNaN(deadline)) return "";
  const diffMs = deadline - now;
  if (diffMs <= 0) return "마감이 지났어요.";
  const totalMinutes = Math.floor(diffMs / 60000);
  const hours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;
  if (hours <= 0) return `${minutes}분 남았어요.`;
  return `${hours}시간 ${minutes}분 남았어요.`;
}

// 로컬 datetime-local input <-> ISO 문자열 변환 헬퍼.
function toDatetimeLocalValue(iso: string | null): string {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(
    date.getMinutes(),
  )}`;
}

export function NoticeCard({
  notice,
  isHost,
  pending,
  onSave,
}: {
  notice: WorkspaceNotice;
  isHost: boolean;
  pending: boolean;
  onSave: (input: { content: string; deadline_at: string | null; presentation_order: number | null }) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [content, setContent] = useState(notice.content);
  const [deadline, setDeadline] = useState(toDatetimeLocalValue(notice.deadline_at));
  const [order, setOrder] = useState(notice.presentation_order != null ? String(notice.presentation_order) : "");
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 30000);
    return () => clearInterval(timer);
  }, []);

  useEffect(() => {
    // 편집 중이 아닐 때만 폴링으로 들어온 최신 notice 값을 폼 상태에 반영한다
    // (편집 중에 덮어써서 입력 중인 내용이 날아가지 않게).
    if (editing) return;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setContent(notice.content);
    setDeadline(toDatetimeLocalValue(notice.deadline_at));
    setOrder(notice.presentation_order != null ? String(notice.presentation_order) : "");
  }, [notice, editing]);

  return (
    <section className="workspace-notice workspace-span-2" aria-label="고정 공지">
      {editing ? (
        <form
          className="workspace-notice-form"
          onSubmit={(event) => {
            event.preventDefault();
            onSave({
              content: content.trim(),
              deadline_at: deadline ? new Date(deadline).toISOString() : null,
              presentation_order: order.trim() ? Number(order) : null,
            });
            setEditing(false);
          }}
        >
          <textarea
            value={content}
            onChange={(event) => setContent(event.target.value)}
            aria-label="공지 내용"
            rows={2}
          />
          <div className="workspace-notice-form-row">
            <label>
              마감 일시
              <input
                type="datetime-local"
                value={deadline}
                onChange={(event) => setDeadline(event.target.value)}
                aria-label="마감 일시"
              />
            </label>
            <label>
              발표 순서
              <input
                type="number"
                min={1}
                value={order}
                onChange={(event) => setOrder(event.target.value)}
                aria-label="발표 순서"
              />
            </label>
          </div>
          <div className="workspace-notice-form-actions">
            <button type="submit" className="button-next" disabled={pending}>
              {pending ? "저장하는 중…" : "저장"}
            </button>
            <button type="button" className="button-muted" onClick={() => setEditing(false)}>
              취소
            </button>
          </div>
        </form>
      ) : (
        <>
          <div className="workspace-notice-body">
            <p className="workspace-notice-content">{notice.content || "등록된 공지가 없어요."}</p>
            <div className="workspace-notice-meta">
              {notice.deadline_at && <span>마감 {formatDeadline(notice.deadline_at)}</span>}
              {notice.presentation_order != null && <span>발표 순서 {notice.presentation_order}번째</span>}
              {notice.deadline_at && (
                <span className="workspace-notice-countdown">{formatRemaining(notice.deadline_at, now)}</span>
              )}
            </div>
          </div>
          {isHost && (
            <button type="button" className="workspace-notice-edit" onClick={() => setEditing(true)}>
              공지 수정
            </button>
          )}
        </>
      )}
    </section>
  );
}
