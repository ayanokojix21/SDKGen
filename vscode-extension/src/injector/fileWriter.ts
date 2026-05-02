/**
 * fileWriter.ts — Docs to Code VS Code Extension
 * Dev 4: Writes file_ready SSE events to {workspace}/src/sdk/
 *
 * Handles V1 (no workspace) and V2 (sdk/ exists) edge cases.
 */

import * as vscode from 'vscode';
import * as path from 'path';

export class FileWriter {
  private _overwriteAll = false;

  /**
   * Write a single file from a file_ready SSE event.
   *
   * @param filename   Relative filename, e.g. 'client.py' or 'tests/test_client.py'
   * @param content    File content string
   * @returns          Absolute path written, or null if skipped/failed
   */
  async write(filename: string, content: string): Promise<string | null> {
    // ── V1: No workspace open ────────────────────────────────────────────────
    const folders = vscode.workspace.workspaceFolders;
    if (!folders || folders.length === 0) {
      const choice = await vscode.window.showErrorMessage(
        '[Docs to Code] No folder open. Open a workspace folder first.',
        'Open Folder'
      );
      if (choice === 'Open Folder') {
        await vscode.commands.executeCommand('workbench.action.files.openFolder');
      }
      return null;
    }

    const workspaceRoot = folders[0].uri;
    const sdkDir = vscode.Uri.joinPath(workspaceRoot, 'src', 'sdk');
    const targetUri = vscode.Uri.joinPath(sdkDir, ...filename.split('/'));

    // ── V2: sdk/ already exists — ask once per session ───────────────────────
    if (!this._overwriteAll) {
      const sdkExists = await this._exists(sdkDir);
      if (sdkExists) {
        const choice = await vscode.window.showInformationMessage(
          '[Docs to Code] src/sdk/ already exists. Overwrite existing SDK files?',
          { modal: true },
          'Yes, overwrite',
          'No, keep existing'
        );
        if (choice !== 'Yes, overwrite') {
          return null;
        }
        this._overwriteAll = true;
      }
    }

    // ── Create parent directories recursively ─────────────────────────────────
    const parentDir = vscode.Uri.joinPath(targetUri, '..');
    await vscode.workspace.fs.createDirectory(parentDir);

    // ── Write file ────────────────────────────────────────────────────────────
    const encoder = new TextEncoder();
    await vscode.workspace.fs.writeFile(targetUri, encoder.encode(content));

    // ── Reveal in Explorer ────────────────────────────────────────────────────
    await vscode.commands.executeCommand('revealInExplorer', targetUri);

    return targetUri.fsPath;
  }

  /**
   * Reset the overwrite-all session flag (call between jobs).
   */
  reset(): void {
    this._overwriteAll = false;
  }

  private async _exists(uri: vscode.Uri): Promise<boolean> {
    try {
      await vscode.workspace.fs.stat(uri);
      return true;
    } catch {
      return false;
    }
  }
}
