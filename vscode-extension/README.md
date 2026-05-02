# ⚡ Docs to Code — VS Code Extension

Receives SDK generation jobs from the Chrome extension and streams live agent logs into a dedicated panel.

## Quick Start

### Development (Load Unpacked)

```bash
cd vscode-extension
npm install
npx tsc          # compile to out/
```

Then in VS Code: **F5** → "Run Extension" (uses `.vscode/launch.json`).

### Install from VSIX

```bash
npx vsce package
code --install-extension docs-to-code-*.vsix
```

## Commands

| Command | Description |
|---|---|
| `Docs to Code: Generate SDK` | Start a new job via URL input box |
| `Docs to Code: Resume Job` | Re-attach to an existing job by ID |
| `Docs to Code: History` | Focus the SDK Gen History sidebar |

## Architecture

```
extension.ts          ← Activation: starts WS server, registers URI handler + commands
├── bridge/
│   ├── wsServer.ts   ← WebSocket server (ports 47291–47293) — Chrome Layer 1
│   └── uriHandler.ts ← Full SSE router: AgentPanel + FileWriter + Installer + Opener
├── panels/
│   └── AgentPanel.ts ← Webview: dark terminal, agent colours, TTS toggle
├── injector/
│   ├── fileWriter.ts ← Writes files to {workspace}/src/sdk/
│   ├── installer.ts  ← Runs pip/npm install in integrated terminal
│   └── opener.ts     ← Opens client.py/ts in editor on complete
├── tts/
│   └── narrator.ts   ← Relays narrate events → AgentPanel webview → Web Speech API
└── memory/
    └── historyView.ts ← TreeView: reads backend/jobs/*/meta.json
```

## Bridge Protocol

Three-layer fallback — Chrome tries each in order:

```
Chrome Extension
  └─ Layer 1: WebSocket ws://localhost:47291  (instant, preferred)
  └─ Layer 2: vscode://docs-to-code.extension/generate?job_id=XXX
  └─ Layer 3: Clipboard (job_id copied) + banner shown
```

## Edge Cases Handled

| Case | Behaviour |
|---|---|
| V1 — No workspace open | Error message + "Open Folder" button |
| V2 — `src/sdk/` exists | Overwrite dialog shown once per session |
| V3 — All WS ports in use | Warning message, URI fallback still works |
| V6 — Webview CSP | `media-src *` allows Web Speech API in panel |

## Output Location

Generated SDK files are written to:
```
{workspace}/src/sdk/
├── client.py          (or client.ts)
├── models.py          (or models.ts)
├── tests/
│   └── test_client.py
└── README.md
```

## Dev Testing

Start the mock backend instead of the real FastAPI server:

```bash
node dev/mock_sse.js
```

Fires a full OpenWeatherMap SSE sequence into the panel (~25s).

## Files

```
vscode-extension/
├── package.json
├── tsconfig.json
└── src/
    ├── extension.ts
    ├── bridge/
    │   ├── wsServer.ts
    │   └── uriHandler.ts
    ├── panels/
    │   └── AgentPanel.ts
    ├── injector/
    │   ├── fileWriter.ts
    │   ├── installer.ts
    │   └── opener.ts
    ├── tts/
    │   └── narrator.ts
    └── memory/
        └── historyView.ts
```
