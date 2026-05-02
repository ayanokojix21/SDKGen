/**
 * api.js — Docs to Code Chrome Extension
 * Dev 4: HTTP helpers for backend communication.
 *
 * Covers: POST /generate/start, GET /generate/stream (SSE), GET /download/{job_id}
 */

'use strict';

const API_BASE = 'http://localhost:8000';

/**
 * Start a new SDK generation job.
 *
 * @param {Object} params
 * @param {string} params.targetUrl      - The documentation URL
 * @param {string} params.language       - 'python' | 'typescript'
 * @param {string} params.pageContent    - Extracted main page text
 * @param {Array}  params.pageLinks      - Extracted links [{text, href, inNav}]
 * @returns {Promise<{job_id: string}>}
 * @throws {Error} If backend is unreachable or returns non-200
 */
async function postStart({ targetUrl, language, pageContent, pageLinks }) {
  const resp = await fetch(`${API_BASE}/generate/start`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      target_url: targetUrl,
      language,
      page_content: pageContent,
      page_links: pageLinks,
    }),
  });

  if (!resp.ok) {
    const body = await resp.text().catch(() => '');
    throw new Error(`Backend error ${resp.status}: ${body}`);
  }

  return resp.json();
}

/**
 * Open an EventSource SSE connection to the generation stream.
 *
 * @param {string} jobId
 * @returns {EventSource}
 */
function streamSSE(jobId) {
  return new EventSource(`${API_BASE}/generate/stream?job_id=${encodeURIComponent(jobId)}`);
}

/**
 * Trigger a ZIP download of the generated SDK.
 * Opens the download URL in a new tab.
 *
 * @param {string} jobId
 */
function downloadZip(jobId) {
  const url = `${API_BASE}/download/${encodeURIComponent(jobId)}`;
  chrome.tabs.create({ url });
}

/**
 * Resume a previously started job by reconnecting the SSE stream.
 * (The backend handles resuming from checkpoint automatically.)
 *
 * @param {string} jobId
 * @returns {EventSource}
 */
function resumeStream(jobId) {
  return streamSSE(jobId);
}

/**
 * Health check — verifies the backend is reachable.
 * @returns {Promise<boolean>}
 */
async function checkBackendHealth() {
  try {
    const resp = await fetch(`${API_BASE}/health`, {
      signal: AbortSignal.timeout(2000),
    });
    return resp.ok;
  } catch {
    return false;
  }
}

// Expose on window for popup.js
window.dtcApi = { postStart, streamSSE, downloadZip, resumeStream, checkBackendHealth };
