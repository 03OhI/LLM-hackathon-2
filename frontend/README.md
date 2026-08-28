This is a [Next.js](https://nextjs.org) project bootstrapped with [`create-next-app`](https://nextjs.org/docs/app/api-reference/cli/create-next-app).

## Getting Started

First, run the development server:

```bash
npm run dev
# or
yarn dev
# or
pnpm dev
# or
bun dev
```

Open [http://localhost:3000](http://localhost:3000) with your browser to see the result.

You can start editing the page by modifying `app/page.tsx`. The page auto-updates as you edit the file.

This project uses [`next/font`](https://nextjs.org/docs/app/building-your-application/optimizing/fonts) to automatically optimize and load [Geist](https://vercel.com/font), a new font family for Vercel.

## 백엔드 API 연결 (환경변수)

`lib/api.ts`가 모든 API 호출의 base URL과 쿠키 전송 방식을 결정한다.

- **base URL**: `NEXT_PUBLIC_API_BASE_URL`(우선) → `NEXT_PUBLIC_API_BASE`(기존 관례) →
  없으면 기본값 `/backend/api`(같은 origin 상대 경로, 리버스 프록시로 백엔드에 연결하는
  배포를 가정).
- **쿠키 전송(credentials)**: base URL을 현재 페이지의 origin과 비교해 자동으로 결정한다.
  같은 origin(상대 경로 포함)이면 `credentials: "same-origin"`, 다른 origin(예:
  `https://api.example.com`)이면 `credentials: "include"`를 쓴다. 별도 설정 없이 두
  배포 형태(같은 origin 리버스 프록시 / 분리된 API 서버) 모두 동작한다.
- 다른 origin으로 배포할 경우 백엔드 CORS 설정(`allow_credentials=True` +
  `allow_origins`에 프론트 origin 명시)이 함께 맞춰져 있어야 `host_secret`/
  `participant_secret` HttpOnly 쿠키가 실제로 오간다. 아직 배포 구조가 확정되지
  않아 이 값은 프론트에서 강제하지 않는다.
- 네트워크 실패, 인증 실패 등 기술적인 원인은 화면에 그대로 노출하지 않는다
  (`lib/api.ts`의 `friendlyErrorMessage`가 항상 중립적인 안내 문구로 변환한다).

## 가정한 백엔드 계약 (미구현, 프론트가 먼저 작성됨)

아래 두 엔드포인트는 이 프론트 작업 시점에 백엔드에 아직 없다. 실제 구현 시
`lib/participants-api.ts` / `lib/workspace-api.ts`의 타입에 맞춰 주면 프론트 수정
없이 연결된다.

- `GET {API_BASE}/rooms/{room_id}/participants` → `{ participants: [{ participant_id, nickname }] }`
- `GET {API_BASE}/rooms/{room_id}/workspace` → `{ status: "LOCKED" | "ACTIVE", workspace_id: string | null }`

퀘스트 조회 응답(`GET /rooms/{room_id}/quests/current`)에도 `completion_requirements.member_checks`/
`completion_requirements.team_checks` 필드가 추가로 필요하다 (각 체크 항목:
`type`, `min_count`, `current_count`, `satisfied`, `my_submitted`). 프론트는 이 값을
그대로 표시만 하고 scope(팀원/공동)를 스스로 추론하지 않는다 — `lib/quest-api.ts` 참고.

## Learn More

To learn more about Next.js, take a look at the following resources:

- [Next.js Documentation](https://nextjs.org/docs) - learn about Next.js features and API.
- [Learn Next.js](https://nextjs.org/learn) - an interactive Next.js tutorial.

You can check out [the Next.js GitHub repository](https://github.com/vercel/next.js) - your feedback and contributions are welcome!

## Deploy on Vercel

The easiest way to deploy your Next.js app is to use the [Vercel Platform](https://vercel.com/new?utm_medium=default-template&filter=next.js&utm_source=create-next-app&utm_campaign=create-next-app-readme) from the creators of Next.js.

Check out our [Next.js deployment documentation](https://nextjs.org/docs/app/building-your-application/deploying) for more details.
