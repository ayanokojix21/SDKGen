/**
 * uriHandler.ts — Docs to Code VS Code Extension
 * Dev 4: Handles vscode://docs-to-code.extension/generate?job_id=XXX URIs.
 *
 * NOTE: Full implementation in Phase 3.
 * This stub routes the job_id to the AgentPanel and SSE stream.
 */

import * as vscode from 'vscode';

/**
 * Handles an incoming URI from the Chrome extension or command palette.
 * Extracts job_id, opens AgentPanel, connects SSE stream.
 *
 * @param uri     The VS Code URI (vscode://docs-to-code.extension/generate?job_id=...)
 * @param context Extension context for disposables and storage
 */
export function handleUri(uri: vscode.Uri, context: vscode.ExtensionContext): void {
  const params = new URLSearchParams(uri.query);
  const jobId = params.get('job_id');

  if (!jobId) {
    vscode.window.showErrorMessage('[Docs to Code] No job_id provided in URI.');
    return;
  }

  console.log(`[DocsToCode URI] Handling job_id: ${jobId}`);

  // TODO (Phase 3): AgentPanel.createOrShow(context.extensionUri, jobId)
  // TODO (Phase 3): Open SSE stream → route events to AgentPanel, FileWriter, etc.

  // Stub: notify the user
  vscode.window.showInformationMessage(
    `⚡ Docs to Code: Job ${jobId} received. Agent Panel coming in Phase 3.`
  );
}
