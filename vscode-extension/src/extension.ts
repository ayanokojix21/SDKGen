/**
 * extension.ts — Docs to Code VS Code Extension
 * Dev 4: Main activation entry point.
 *
 * Registers commands, starts WebSocket server, registers URI handler.
 */

import * as vscode from 'vscode';
import { WSServer } from './bridge/wsServer';
import { handleUri } from './bridge/uriHandler';
import { HistoryViewProvider } from './memory/historyView';

// Singleton WS server — shared across all handlers
let wsServer: WSServer | null = null;
let historyProvider: import('./memory/historyView').HistoryViewProvider | null = null;

/** Called by uriHandler after job completion to refresh the history sidebar. */
export function refreshHistory(): void {
  historyProvider?.refresh();
}

/**
 * Called by VS Code when the extension activates.
 */
export async function activate(context: vscode.ExtensionContext): Promise<void> {
  console.log('[DocsToCode] Extension activating...');

  // ── 1. Start WebSocket server ──────────────────────────────────────────────
  wsServer = new WSServer();
  await wsServer.start();
  context.subscriptions.push({
    dispose: () => wsServer?.stop(),
  });

  // Wire WS new_job → URI handler (Chrome bridge Layer 1)
  wsServer.onNewJob((msg) => {
    const uri = vscode.Uri.parse(
      `vscode://docs-to-code.extension/generate?job_id=${encodeURIComponent(msg.job_id)}&language=${encodeURIComponent(msg.language ?? 'python')}`
    );
    handleUri(uri, context);
  });

  // ── 2. Register URI handler ────────────────────────────────────────────────
  // Handles: vscode://docs-to-code.extension/generate?job_id=XXX
  const uriHandlerDisposable = vscode.window.registerUriHandler({
    handleUri(uri: vscode.Uri) {
      handleUri(uri, context);
    },
  });
  context.subscriptions.push(uriHandlerDisposable);

  // ── 3. Register commands ───────────────────────────────────────────────────

  // Generate — open a quick-input to start a new job manually
  context.subscriptions.push(
    vscode.commands.registerCommand('docs-to-code.generate', async () => {
      const url = await vscode.window.showInputBox({
        prompt: 'Enter API documentation URL',
        placeHolder: 'https://jsonplaceholder.typicode.com/guide',
        validateInput: (v) => {
          try {
            new URL(v);
            return null;
          } catch {
            return 'Please enter a valid URL';
          }
        },
      });
      if (!url) return;

      const language = await vscode.window.showQuickPick(['Python', 'TypeScript'], {
        placeHolder: 'Select SDK language',
      });
      if (!language) return;

      // Start job via backend
      vscode.window.showInformationMessage(
        `[Docs to Code] Starting ${language} SDK generation for ${url}…`
      );

      // POST to backend
      try {
        const resp = await fetch('http://localhost:8000/generate/start', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            target_url: url,
            language: language.toLowerCase(),
            page_content: '',
            page_links: [],
          }),
        });
        const { job_id } = (await resp.json()) as { job_id: string };
        // Open the Agent Panel via URI handler
        const uri = vscode.Uri.parse(
          `vscode://docs-to-code.extension/generate?job_id=${job_id}`
        );
        handleUri(uri, context);
      } catch (err) {
        vscode.window.showErrorMessage(
          '[Docs to Code] Backend not running. Start it with: uvicorn main:app --reload'
        );
      }
    })
  );

  // Resume — re-attach to an existing job
  context.subscriptions.push(
    vscode.commands.registerCommand('docs-to-code.resume', async () => {
      const jobId = await vscode.window.showInputBox({
        prompt: 'Enter Job ID to resume',
        placeHolder: 'e.g. a1b2c3d4',
      });
      if (!jobId) return;

      const uri = vscode.Uri.parse(
        `vscode://docs-to-code.extension/generate?job_id=${jobId.trim()}`
      );
      handleUri(uri, context);
    })
  );

  // History — reveal the history TreeView
  context.subscriptions.push(
    vscode.commands.registerCommand('docs-to-code.history', () => {
      vscode.commands.executeCommand('workbench.view.explorer');
      vscode.commands.executeCommand('docs-to-code.historyView.focus');
    })
  );

  // ── 4. Register History TreeView ───────────────────────────────────────────
  historyProvider = new HistoryViewProvider(context);
  context.subscriptions.push(
    vscode.window.registerTreeDataProvider('docs-to-code.historyView', historyProvider)
  );

  console.log('[DocsToCode] Extension activated successfully.');
  vscode.window.setStatusBarMessage('⚡ Docs to Code ready', 3000);
}

/**
 * Called by VS Code when the extension deactivates.
 */
export function deactivate(): void {
  console.log('[DocsToCode] Extension deactivating...');
  wsServer?.stop();
}
