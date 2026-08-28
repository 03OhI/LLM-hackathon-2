import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, friendlyErrorMessage, requestJson } from "../api";

describe("requestJson", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("apiBase가 상대 경로(같은 origin)이면 credentials: same-origin으로 요청한다", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ hello: "world" }),
    });
    vi.stubGlobal("fetch", fetchMock);

    const result = await requestJson<{ hello: string }>("/rooms/abc/quests/current");

    expect(result).toEqual({ hello: "world" });
    const [, init] = fetchMock.mock.calls[0];
    expect(init.credentials).toBe("same-origin");
  });

  it("에러 응답을 ApiError(code/message/status)로 변환한다", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 409,
      json: async () => ({ error: { code: "COMPLETION_CONDITION_NOT_MET", message: "아직입니다" } }),
    });
    vi.stubGlobal("fetch", fetchMock);

    await expect(requestJson("/quest-assignments/1/complete")).rejects.toMatchObject({
      code: "COMPLETION_CONDITION_NOT_MET",
      status: 409,
    });
  });

  it("본문이 JSON이 아니어도 안전한 기본 ApiError를 만든다", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
      json: async () => {
        throw new Error("not json");
      },
    });
    vi.stubGlobal("fetch", fetchMock);

    await expect(requestJson("/x")).rejects.toBeInstanceOf(ApiError);
  });

  it("네트워크 자체가 실패해도 기술적 원인을 감춘 ApiError로 변환한다", async () => {
    const fetchMock = vi.fn().mockRejectedValue(new TypeError("Failed to fetch: CORS blocked"));
    vi.stubGlobal("fetch", fetchMock);

    await expect(requestJson("/x")).rejects.toMatchObject({ code: "NETWORK_ERROR" });
  });
});

describe("friendlyErrorMessage", () => {
  it("Bedrock/기술적 원인을 절대 노출하지 않는다", () => {
    const message = friendlyErrorMessage(new ApiError("UNKNOWN_ERROR", "LLM_ERROR: TimeoutError", 500));
    expect(message).not.toMatch(/bedrock/i);
    expect(message).not.toMatch(/timeout/i);
    expect(message).not.toMatch(/llm/i);
  });

  it("409 완료 조건 미충족을 사람이 읽을 문구로 바꾼다", () => {
    const message = friendlyErrorMessage(new ApiError("COMPLETION_CONDITION_NOT_MET", "", 409));
    expect(message).toContain("완료 조건");
  });

  it("403을 권한 문구로 바꾼다", () => {
    const message = friendlyErrorMessage(new ApiError("FORBIDDEN", "", 403));
    expect(message).toContain("권한");
  });

  it("알 수 없는 에러도 항상 문자열을 반환한다", () => {
    expect(typeof friendlyErrorMessage(new Error("boom"))).toBe("string");
    expect(typeof friendlyErrorMessage("plain string")).toBe("string");
  });
});
