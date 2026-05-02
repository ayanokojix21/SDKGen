/**
 * background.js — Docs to Code Chrome Extension
 * Dev 4: Service worker — VS Code WebSocket probe, port management, bridge coordination.
 *        NOW ALSO: owns the SSE EventSource so it survives popup close/reopen.
 *
 * Runs as a Manifest v3 service worker.
 */

'use strict';

// ─── Constants ────────────────────────────────────────────────────────────────
const WS_PORTS = [47291, 47292, 47293];
const WS_PROBE_TIMEOUT_MS = 100;
const API_BASE = 'http://localhost:8000';

// ─── State (in-memory, resets on service worker restart) ─────────────────────
let wsConnection = null;
let activePort = null;
let connectionStatus = 'disconnected'; // 'connected' | 'disconnected'

// ─── SSE state ────────────────────────────────────────────────────────────────
let activeEventSource = null;
let activeJobId = null;
let sseEventBuffer = [];          // Buffer events so popup can replay on open
const MAX_BUFFER_SIZE = 500;      // Cap buffer to prevent memory issues
let jobFinished = false;          // True when 'done' sentinel received

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

// ─── SSE management (lives in background, survives popup close) ──────────────

/**
 * Opens an EventSource to the backend SSE stream.
 * Called by the popup via message passing.
 * The background worker keeps listening even if the popup closes.
 */
function connectSSE(jobId) {
  // Close any existing stream
  if (activeEventSource) {
    activeEventSource.close();
    activeEventSource = null;
  }

  activeJobId = jobId;
  jobFinished = false;
  sseEventBuffer = [];

  console.log(`[DocsToCode BG] Opening SSE for job=${jobId}`);

  const es = new EventSource(`${API_BASE}/generate/stream?job_id=${encodeURIComponent(jobId)}`);
  activeEventSource = es;

  es.addEventListener('message', (e) => {
    let data;
    try {
      data = JSON.parse(e.data);
    } catch {
      return;
    }

    // Buffer the event for popup replay
    if (sseEventBuffer.length < MAX_BUFFER_SIZE) {
      sseEventBuffer.push(data);
    }

    // Forward to popup immediately (if open)
    broadcastSSEToPopup(data);

    const type = data.type || '';

    // Handle terminal events
    if (type === 'done') {
      jobFinished = true;
      es.close();
      activeEventSource = null;
      console.log(`[DocsToCode BG] SSE done for job=${jobId}`);
      // Persist completion
      chrome.storage.session.set({ activeJobId: null });
      return;
    }

    if (type === 'error' || type === 'safety_cutoff' || data.status === 'failed') {
      jobFinished = true;
      es.close();
      activeEventSource = null;
      console.log(`[DocsToCode BG] SSE error/failed for job=${jobId}: ${data.message || ''}`);
      chrome.storage.session.set({ activeJobId: null });
      return;
    }
  });

  es.addEventListener('error', () => {
    if (es.readyState === EventSource.CLOSED) {
      console.log(`[DocsToCode BG] SSE connection closed for job=${jobId}`);
      // If the job wasn't finished, try to reconnect after a delay
      if (!jobFinished && activeJobId === jobId) {
        console.log(`[DocsToCode BG] Attempting SSE reconnect in 3s for job=${jobId}`);
        setTimeout(() => {
          if (!jobFinished && activeJobId === jobId) {
            connectSSE(jobId);
          }
        }, 3000);
      }
    }
  });

  // Persist active job
  chrome.storage.session.set({ activeJobId: jobId });
}

/**
 * Broadcast an SSE event to the popup via chrome.runtime messaging.
 */
function broadcastSSEToPopup(data) {
  chrome.runtime.sendMessage({
    type: 'SSE_EVENT',
    data: data,
    jobId: activeJobId,
  }).catch(() => {
    // Popup not open — that's fine, events are buffered
  });
}

// ─── Message broadcasting ─────────────────────────────────────────────────────

/**
 * Sends a message to all open popup windows (if any).
 * @param {Object} msg
 */
async function broadcastToPopup(msg) {
  try {
    await chrome.runtime.sendMessage(msg);
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

    // Popup requests SSE connection for a new job
    case 'START_SSE': {
      const { jobId } = message;
      connectSSE(jobId);
      sendResponse({ ok: true });
      return false;
    }

    // Popup opened and wants to catch up on buffered events
    case 'GET_SSE_STATE': {
      sendResponse({
        jobId: activeJobId,
        finished: jobFinished,
        buffer: sseEventBuffer,
        connected: activeEventSource !== null && activeEventSource.readyState === EventSource.OPEN,
      });
      return false;
    }

    // Popup wants to stop the SSE stream
    case 'STOP_SSE': {
      if (activeEventSource) {
        activeEventSource.close();
        activeEventSource = null;
      }
      activeJobId = null;
      jobFinished = false;
      sseEventBuffer = [];
      chrome.storage.session.set({ activeJobId: null });
      sendResponse({ ok: true });
      return false;
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
