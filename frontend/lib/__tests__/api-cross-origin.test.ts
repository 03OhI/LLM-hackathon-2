import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// apiBase는 모듈 로드 시점에 process.env를 읽으므로, origin이 다른 케이스는
// 모듈을 리셋하고 env를 미리 설정한 뒤 다시 import해서 검증한다.
describe("requestJson — 다른 origin 배포", () => {
  const originalEnv = process.env.NEXT_PUBLIC_API_BASE_URL;

  beforeEach(() => {
    vi.resetModules();
  });

  afterEach(() => {
    process.env.NEXT_PUBLIC_API_BASE_URL = originalEnv;
    vi.unstubAllGlobals();
    vi.resetModules();
  });

  it("NEXT_PUBLIC_API_BASE_URL이 다른 origin이면 credentials: include를 쓴다", async () => {
    process.env.NEXT_PUBLIC_API_BASE_URL = "https://api.example.com/api";
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({}) });
    vi.stubGlobal("fetch", fetchMock);

    const { requestJson } = await import("../api");
    await requestJson("/rooms/abc/quests/current");

    const [, init] = fetchMock.mock.calls[0];
    expect(init.credentials).toBe("include");
  });
});
