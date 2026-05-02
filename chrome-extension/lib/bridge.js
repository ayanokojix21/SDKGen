/**
 * bridge.js — Docs to Code Chrome Extension
 * Dev 4: Chrome → VS Code bridge — full implementation (Phase 4).
 *
 * Three-layer fallback chain:
 *   1. WebSocket  (ws://localhost:47291) — preferred, instant
 *   2. vscode:// URI handler             — fallback if WS not connected
 *   3. Clipboard                          — last resort (Edge case V4)
 *
 * Also handles:
 *   - port_info relay from background.js (WS port changed to 47292/47293)
 *   - file_written confirmation log in popup
 *   - VS Code badge update on connection state change
 */

'use strict';

const dtcBridge = {

  // ─── Send new_job to VS Code ──────────────────────────────────────────────

  /**
   * Notify VS Code of a new generation job.
   * Tries WS first, then URI, then clipboard.
   *
   * @param {string} jobId
   * @param {string} url       Documentation URL
   * @param {string} language  'python' | 'typescript'
   */
  async sendNewJob(jobId, url, language) {
    // Layer 1: WebSocket via background service worker
    const wsResult = await this._trySendViaWS(jobId, url, language);
    if (wsResult) {
      this._logToPopup(`✓ VS Code notified via WebSocket`, 'var(--c-qa-pass)');
      return;
    }

    // Layer 2: vscode:// URI handler
    const uriResult = this._trySendViaURI(jobId, language);
    if (uriResult) {
      this._logToPopup(`↗ Opening VS Code via URI handler…`, 'var(--c-architect)');
      return;
    }

    // Layer 3: Clipboard fallback (Edge case V4)
    await this._fallbackClipboard(jobId);
  },

  /**
   * Open (or focus) the VS Code Agent Panel for an existing job.
   * @param {string} jobId
   */
  openInVSCode(jobId) {
    const uri = `vscode://docs-to-code-team.docs-to-code/generate?job_id=${encodeURIComponent(jobId)}`;
    window.open(uri);
  },

  // ─── Layer 1: WebSocket ───────────────────────────────────────────────────

  async _trySendViaWS(jobId, url, language) {
    try {
      const response = await chrome.runtime.sendMessage({
        type: 'SEND_NEW_JOB',
        jobId,
        url,
        language,
      });
      return response?.sent === true;
    } catch {
      return false;
    }
  },

  // ─── Layer 2: vscode:// URI ───────────────────────────────────────────────

  _trySendViaURI(jobId, language) {
    try {
      const uri = `vscode://docs-to-code-team.docs-to-code/generate?job_id=${encodeURIComponent(jobId)}&language=${encodeURIComponent(language)}`;
      window.open(uri);
      return true;
    } catch {
      return false;
    }
  },

  // ─── Layer 3: Clipboard fallback ──────────────────────────────────────────

  async _fallbackClipboard(jobId) {
    try {
      await navigator.clipboard.writeText(jobId);
      this._logToPopup(
        `⎘ Job ID copied to clipboard. Open VS Code → "Docs to Code: Resume Job"`,
        'var(--c-warn)'
      );
      this._showClipboardBanner(jobId);
    } catch {
      this._logToPopup(`⚠ Could not reach VS Code. Job ID: ${jobId}`, 'var(--c-warn)');
    }
  },

  // ─── Banner helpers ───────────────────────────────────────────────────────

  _showClipboardBanner(jobId) {
    // Inject a banner into the popup DOM if it exists
    const banner = document.getElementById('resume-banner');
    if (!banner) return;
    const text = document.getElementById('resume-text');
    if (text) {
      text.innerHTML = `Job ID <code>${jobId.slice(0, 8)}</code> copied. Open VS Code → <em>Resume Job</em>.`;
    }
    banner.classList.remove('hidden');
  },

  _logToPopup(text, colour) {
    // Call into popup.js appendLine if available (same window context)
    if (typeof appendLine === 'function') {
      appendLine(text, colour || 'var(--text-secondary)');
    }
  },

  // ─── file_written confirmation ────────────────────────────────────────────

  /**
   * Log a file_written confirmation from VS Code into the popup terminal.
   * Called by background.js via window.postMessage.
   * @param {string} filename
   */
  onFileWritten(filename) {
    this._logToPopup(`✓ ${filename} → VS Code`, 'var(--c-packager)');
  },
};

// ─── Listen for messages from background.js ───────────────────────────────────
window.addEventListener('message', (e) => {
  if (!e.data || typeof e.data !== 'object') return;

  switch (e.data.type) {
    case 'file_written':
      dtcBridge.onFileWritten(e.data.filename || '');
      break;
    case 'vs_code_status':
      _updateBadge(e.data.connected, e.data.port);
      break;
    default:
      break;
  }
});

// ─── Badge update helper ──────────────────────────────────────────────────────
function _updateBadge(connected, port) {
  const badge = document.getElementById('vs-code-badge');
  if (!badge) return;
  const label = badge.querySelector('.badge-label');
  if (connected) {
    badge.className = 'badge badge--connected';
    if (label) label.textContent = `VS Code :${port || 47291}`;
  } else {
    badge.className = 'badge badge--disconnected';
    if (label) label.textContent = 'VS Code';
  }
}

// Expose on window
window.dtcBridge = dtcBridge;
