# ITALIX.ai frontend

The authenticated Next.js command center for ITALIX.ai.

```bash
npm ci
npm run dev
```

The development server binds to `http://127.0.0.1:3000` and reads server-only
configuration from the repository root `.env`. See the root
[`README.md`](../README.md) for complete setup, security boundaries, and the
backend workflow.

Useful checks:

```bash
npm run typecheck
npm run lint
npm run build
npm run test:security
```

FastAPI bearer tokens and dashboard session secrets must never use a
`NEXT_PUBLIC_` prefix. Browser requests use short-lived, signed HttpOnly
operator sessions; backend credentials remain server-side.
