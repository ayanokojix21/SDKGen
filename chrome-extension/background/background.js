/**
 * background.js — Docs to Code Chrome Extension
 * Dev 4: Service worker — VS Code WebSocket probe, port management, bridge coordination.
 *
 * Runs as a Manifest v3 service worker.
 */

'use strict';

// ─── Constants ────────────────────────────────────────────────────────────────
const WS_PORTS = [47291, 47292, 47293];
const WS_PROBE_TIMEOUT_MS = 100;

// ─── State (in-memory, resets on service worker restart) ─────────────────────
let wsConnection = null;
let activePort = null;
let connectionStatus = 'disconnected'; // 'connected' | 'disconnected'

// ─── WebSocket probe ──────────────────────────────────────────────────────────

/**
 * Probes the given port for a VS Code extension WS server.
 * Resolves with the WebSocket if connected, rejects on timeout/error.
 *
 * @param {number} port
 * @returns {Promise<WebSocket>}
 */
function probePort(port) {
  return new Promise((resolve, reject) => {
    const ws = new WebSocket(`ws://localhost:${port}`);
    const timeout = setTimeout(() => {
      ws.close();
      reject(new Error(`Timeout on port ${port}`));
    }, WS_PROBE_TIMEOUT_MS);

    ws.addEventListener('open', () => {
      clearTimeout(timeout);
      resolve(ws);
    });

    ws.addEventListener('error', () => {
      clearTimeout(timeout);
      reject(new Error(`Error on port ${port}`));
    });
  });
}

/**
 * Attempts to connect to VS Code WS server by trying ports in order.
 * Updates connection status in chrome.storage.session.
 */
async function probeVSCode() {
  for (const port of WS_PORTS) {
    try {
      const ws = await probePort(port);
      wsConnection = ws;
      activePort = port;
      connectionStatus = 'connected';

      // Save status so popup can read it
      await chrome.storage.session.set({
        vsCodeStatus: 'connected',
        vsCodePort: port,
      });

      ws.addEventListener('message', handleWSMessage);
      ws.addEventListener('close', handleWSClose);
      ws.addEventListener('error', handleWSError);

      console.log(`[DocsToCode BG] VS Code connected on port ${port}`);
      return;
    } catch (_) {
      // Try next port
    }
  }

  // All ports failed
  wsConnection = null;
  activePort = null;
  connectionStatus = 'disconnected';
  await chrome.storage.session.set({ vsCodeStatus: 'disconnected', vsCodePort: null });
  console.log('[DocsToCode BG] VS Code not detected on any port.');
}

// ─── WebSocket event handlers ─────────────────────────────────────────────────

/**
 * Handles incoming WS messages from VS Code extension.
 * @param {MessageEvent} event
 */
async function handleWSMessage(event) {
  let data;
  try {
    data = JSON.parse(event.data);
  } catch (_) {
    return;
  }

  switch (data.type) {
    case 'vscode_ready':
      console.log('[DocsToCode BG] VS Code extension ready.');
      break;

    case 'port_info':
      // VS Code tells us it switched to a fallback port
      if (data.port && data.port !== activePort) {
        activePort = data.port;
        await chrome.storage.session.set({ vsCodePort: data.port });
        console.log(`[DocsToCode BG] VS Code using port ${data.port}`);
      }
      break;

    case 'file_written':
      // VS Code confirms a file was written — broadcast to popup
      broadcastToPopup({ type: 'file_written', filename: data.filename });
      break;

    default:
      // Forward unknown messages to popup
      broadcastToPopup(data);
      break;
  }
}

function handleWSClose() {
  wsConnection = null;
  activePort = null;
  connectionStatus = 'disconnected';
  chrome.storage.session.set({ vsCodeStatus: 'disconnected', vsCodePort: null });
  console.log('[DocsToCode BG] WS connection closed.');
}

function handleWSError(err) {
  console.warn('[DocsToCode BG] WS error:', err);
}

// ─── Message broadcasting ─────────────────────────────────────────────────────

/**
 * Sends a message to all open popup windows (if any).
 * @param {Object} msg
 */
async function broadcastToPopup(msg) {
  try {
    const views = chrome.extension.getViews({ type: 'popup' });
    for (const view of views) {
      view.postMessage(msg, '*');
    }
  } catch (_) {
    // Popup may not be open — ignore
  }
}

// ─── Message listener (from popup / content scripts) ─────────────────────────

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  switch (message.type) {

    // Popup opened — probe VS Code
    case 'POPUP_OPENED': {
      probeVSCode().then(() => {
        sendResponse({ status: connectionStatus, port: activePort });
      });
      return true; // async
    }

    // Popup wants to send new_job via WS
    case 'SEND_NEW_JOB': {
      const { jobId, url, language } = message;
      if (wsConnection && wsConnection.readyState === WebSocket.OPEN) {
        wsConnection.send(JSON.stringify({ type: 'new_job', job_id: jobId, url, language }));
        sendResponse({ sent: true, method: 'websocket' });
      } else {
        sendResponse({ sent: false, method: 'none', status: connectionStatus });
      }
      return true;
    }

    // Get current WS status
    case 'GET_VS_CODE_STATUS': {
      sendResponse({ status: connectionStatus, port: activePort });
      return false;
    }

    default:
      break;
  }
  return false;
});

// ─── On install / startup ─────────────────────────────────────────────────────
chrome.runtime.onInstalled.addListener(() => {
  console.log('[DocsToCode BG] Extension installed.');
  chrome.storage.session.set({ vsCodeStatus: 'disconnected', vsCodePort: null, activeJobId: null });
});
