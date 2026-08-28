// 방 참여자 목록 API 클라이언트.
//
// 실제 백엔드 계약 (backend/app/api/participants.py list_room_participants):
//   GET /api/rooms/{room_id}/participants
//   -> [{ participant_id, nickname }, ...]   (배열을 그대로 반환, 래핑 없음)

import { requestJson } from "./api";

export type RoomParticipant = {
  participant_id: string;
  nickname: string;
};

export function getRoomParticipants(roomId: string): Promise<RoomParticipant[]> {
  return requestJson<RoomParticipant[]>(`/rooms/${encodeURIComponent(roomId)}/participants`);
}
