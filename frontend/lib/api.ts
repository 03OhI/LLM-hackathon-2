// 백엔드 공통 fetch 헬퍼 — survey/results 페이지의 apiBase 관례를 그대로 따르되,
// API가 다른 origin에 있을 수 있는 배포 형태도 함께 지원한다 (README 참고).
//
// - NEXT_PUBLIC_API_BASE(기존 관례) 또는 NEXT_PUBLIC_API_BASE_URL(신규, 배포 구조가
//   origin이 분리된 경우를 위해 추가) 중 있는 값을 쓴다. 둘 다 없으면 기존 기본값
//   "/backend/api"(같은 origin 상대 경로, 리버스 프록시 가정).
// - apiBase가 상대 경로(같은 origin)이면 credentials: "same-origin".
// - apiBase가 절대 URL이고 현재 페이지와 origin이 다르면 credentials: "include"로
//   전환해 host_secret/participant_secret 쿠키가 실제로 전달되게 한다.
//   (백엔드는 CORS에서 allow_credentials=True + 정확한 allow_origins가 필요하다 —
//   그 설정 자체는 배포 구성이라 여기서 강제하지 않는다.)

export const apiBase =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? process.env.NEXT_PUBLIC_API_BASE ?? "/backend/api";

function resolveCredentials(): RequestCredentials {
  if (typeof window === "undefined") return "same-origin";
  try {
    const target = new URL(apiBase, window.location.origin);
    return target.origin === window.location.origin ? "same-origin" : "include";
  } catch {
    return "same-origin";
  }
}

export type ApiErrorPayload = { code: string; message: string };

// 백엔드는 {"error": {"code", "message"}} 형태로 에러를 반환한다 (app/errors.py 전역 핸들러).
export class ApiError extends Error {
  code: string;
  status: number;

  constructor(code: string, message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
  }
}

async function toApiError(response: Response): Promise<ApiError> {
  try {
    const body = (await response.json()) as { error?: ApiErrorPayload };
    if (body?.error?.code) {
      return new ApiError(body.error.code, body.error.message ?? "요청을 처리하지 못했어요.", response.status);
    }
  } catch {
    /* 응답 본문이 JSON이 아니면 아래 기본 에러로 대체 */
  }
  return new ApiError("UNKNOWN_ERROR", "요청을 처리하지 못했어요.", response.status);
}

export async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${apiBase}${path}`, {
      credentials: resolveCredentials(),
      ...init,
      headers: { "content-type": "application/json", ...(init?.headers ?? {}) },
    });
  } catch {
    // 네트워크 자체가 실패한 경우(오프라인, CORS 차단 등)도 기술적 원인을 그대로
    // 노출하지 않고 동일한 ApiError 경로로 흘려보낸다.
    throw new ApiError("NETWORK_ERROR", "네트워크 요청에 실패했어요.", 0);
  }
  if (!response.ok) throw await toApiError(response);
  return (await response.json()) as T;
}

// 사용자에게 보여줄 안내 문구로 변환한다. Bedrock 실패 여부 같은 기술적 원인은
// 절대 노출하지 않고, 상황에 맞는 중립적인 메시지만 보여준다.
export function friendlyErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    switch (error.code) {
      case "UNAUTHORIZED":
        return "인증 정보를 확인하지 못했어요. 초대 링크로 다시 들어와 주세요.";
      case "FORBIDDEN":
        return "이 작업을 할 수 있는 권한이 없어요.";
      case "SESSION_NOT_FOUND":
      case "QUEST_ASSIGNMENT_NOT_FOUND":
      case "WORKSPACE_NOT_FOUND":
      case "TASK_NOT_FOUND":
      case "RESOURCE_NOT_FOUND":
      case "NO_ACTIVE_QUEST":
        return "정보를 찾지 못했어요. 새로고침한 뒤 다시 시도해 주세요.";
      case "QUEST_CATALOG_UNAVAILABLE":
        return "지금은 배정할 수 있는 퀘스트가 없어요. 잠시 후 다시 시도해 주세요.";
      case "QUEST_ALREADY_FINALIZED":
        return "이미 완료되었거나 건너뛴 퀘스트예요.";
      case "QUEST_NOT_STARTED":
        return "아직 시작되지 않은 퀘스트예요.";
      case "COMPLETION_CONDITION_NOT_MET":
        return "아직 완료 조건을 채우지 못했어요. 팀원 응답을 조금 더 모아 주세요.";
      case "WORKSPACE_NOT_READY":
        return "퀘스트가 끝난 뒤에 협업 공간을 시작할 수 있어요.";
      case "NETWORK_ERROR":
        return "네트워크 연결을 확인해 주세요.";
      default:
        return "잠시 문제가 있었어요. 다시 시도해 주세요.";
    }
  }
  return "잠시 문제가 있었어요. 다시 시도해 주세요.";
}
