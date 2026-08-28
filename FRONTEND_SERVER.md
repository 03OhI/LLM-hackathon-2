# Frontend server workspace

## Paths

- Frontend: `/home/ubuntu/LLM-hackathon-2/frontend`
- Frontend branch: `feat/frontend` (local branch; not pushed)
- Backend worktree: `/home/ubuntu/LLM-hackathon-worktrees/backend` (`feat/backend`)
- RAG worktree: `/home/ubuntu/LLM-hackathon-worktrees/rag` (`RAG`)

## Commands

```bash
cd /home/ubuntu/LLM-hackathon-2/frontend
npm run dev -- --hostname 127.0.0.1 --port 3000
npm run lint
NODE_OPTIONS=--max-old-space-size=720 npm run build -- --webpack
```

Use Webpack for production builds on this EC2 instance. Its memory is too small
for a reliable Turbopack production build.

The production service runs on `127.0.0.1:3000`:

```bash
sudo systemctl status hackathon-frontend
sudo systemctl restart hackathon-frontend
journalctl -u hackathon-frontend -f
```

Connect from Windows without exposing port 3000 publicly:

```powershell
ssh -L 3000:127.0.0.1:3000 hackathon-ec2
```

Then open `http://localhost:3000`.

## Environment variables

Keep secrets in `frontend/.env.local`; it is ignored by Git. Variables prefixed
with `NEXT_PUBLIC_` are embedded into browser JavaScript during the build and
must never contain secrets. The backend API URL is intentionally unset until an
HTTP API contract exists.
