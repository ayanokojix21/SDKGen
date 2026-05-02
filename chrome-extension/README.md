# ⚡ Docs to Code — Chrome Extension

Turns API documentation pages into fully-typed SDKs in under 60 seconds.

## Quick Start

1. Go to `chrome://extensions` → Enable **Developer mode**
2. Click **Load unpacked** → Select this `chrome-extension/` folder
3. The ⚡ icon appears in your toolbar

## Usage

1. Open any API docs page (e.g. `openweathermap.org/api`)
2. Click the ⚡ icon
3. URL is auto-filled — select **Language** and **Output**
4. Hit **Generate SDK**

The terminal log streams live agent activity as the SDK is built.

## Output Options

| Mode | Behaviour |
|---|---|
| **VS Code** | Files appear in `src/sdk/` in your open workspace |
| **Download ZIP** | Browser downloads the zipped SDK |

> VS Code mode requires the [Docs to Code VS Code Extension](../vscode-extension/) to be running.

## Architecture

```
popup.js          ← UI controller, SSE consumer
├── lib/api.js    ← POST /generate/start, EventSource /generate/stream
├── lib/bridge.js ← WS → vscode:// URI → Clipboard fallback chain
└── lib/tts.js    ← Web Speech API TTS controller

content.js        ← Page capture, link extraction, overlay panel
background.js     ← Service worker: WS probe, port management
```

## Edge Cases Handled

| Case | Behaviour |
|---|---|
| C1 — VS Code not detected | Output switches to ZIP, install hint shown |
| C2 — Backend not running | Banner with `uvicorn main:app --reload` (click to copy) |
| C4 — No speechSynthesis | Narrate toggle silently disabled |
| C5 — Popup closed mid-run | "Job in progress — resume" banner on reopen |

## Dev Testing (no backend required)

```bash
node dev/mock_sse.js
```

Streams a full OpenWeatherMap demo: crawl → schema → SDK → QA failure → reroute → fix → 11/11 pass → complete (~25s).

## Files

```
chrome-extension/
├── manifest.json
├── popup/
│   ├── popup.html
│   ├── popup.css
│   └── popup.js
├── content/
│   └── content.js
├── background/
│   └── background.js
├── lib/
│   ├── api.js
│   ├── bridge.js
│   └── tts.js
└── icons/
    ├── icon16.png
    ├── icon32.png
    ├── icon48.png
    └── icon128.png
```
