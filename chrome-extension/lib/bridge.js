/**
 * bridge.js — Docs to Code Chrome Extension
 * Dev 4: Chrome → VS Code bridge (Phase 4 full implementation).
 *
 * STUB for Phase 2: exposes window.dtcBridge with no-op methods
 * so popup.js can call them without errors. Full WS + URI + clipboard
 * logic is implemented in Phase 4.
 */

'use strict';

window.dtcBridge = {
  /**
   * Send a new_job message to VS Code.
   * Phase 2 stub — full implementation in Phase 4.
   * @param {string} jobId
   * @param {string} url
   * @param {string} language
   */
  async sendNewJob(jobId, url, language) {
    // Phase 4 will implement: WS → URI → clipboard chain
    console.log(`[Bridge stub] sendNewJob: job_id=${jobId}, url=${url}, lang=${language}`);
  },

  /**
   * Open VS Code panel for an existing job.
   * @param {string} jobId
   */
  openInVSCode(jobId) {
    // Phase 4: try WS, fall back to vscode:// URI
    const uri = `vscode://docs-to-code.extension/generate?job_id=${encodeURIComponent(jobId)}`;
    window.open(uri);
  },
};
