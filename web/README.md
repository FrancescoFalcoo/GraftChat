# web/

GraftChat frontend: Vite + React 18 + TypeScript, plain CSS. It talks to the backend
through the HTTP contract in [docs/API.md](../docs/API.md).

## Run

```bash
cd web
npm install
npm run dev      # http://localhost:5173, proxies /api to http://127.0.0.1:8000
```

Start the backend (`api/`) on port 8000 first.

## Build and test

```bash
npm run build    # type-check (tsc --noEmit), then production build into web/dist
npm test         # Vitest + jsdom
```

On Windows, run the tests from PowerShell or cmd: from Git Bash every file can fail with
"Vitest failed to find the current suite" even though the tests are fine.

The backend serves `web/dist` at `/` in production; all requests go to `/api/...`.

## Layout

- `src/markdown.ts`, `src/components/MessageContent.tsx`: character-preserving message
  rendering (the element's `textContent` is exactly the raw message).
- `src/selection.ts`: DOM selection to code point offsets and back (branch anchors).
- `src/api.ts`, `src/types.ts`: typed API client and the shapes from `docs/API.md`.
- `src/hooks/useGraft.ts`: application state and actions.
- `src/images.ts`, `src/components/Composer.tsx`: images on a message (pick, paste, drop;
  the same limits as the server).
- `src/components/`: sidebar, main chat, branch panel, merge dialog, settings.
- `src/test/`: unit and component tests.
