/**
 * opener.ts — Docs to Code VS Code Extension
 * Dev 4: Opens client.py or client.ts in the editor on complete event.
 */

import * as vscode from 'vscode';

export class Opener {
  /**
   * Open the main SDK client file in the editor after generation completes.
   * Tries client.py first, then client.ts.
   *
   * @param language  'python' | 'typescript'
   */
  async openMainFile(language: string): Promise<void> {
    const folders = vscode.workspace.workspaceFolders;
    if (!folders || folders.length === 0) return;

    const root = folders[0].uri;
    const filename = language === 'typescript' ? 'client.ts' : 'client.py';
    const fileUri = vscode.Uri.joinPath(root, 'src', 'sdk', filename);

    try {
      await vscode.workspace.fs.stat(fileUri); // throws if not found
      const doc = await vscode.workspace.openTextDocument(fileUri);
      await vscode.window.showTextDocument(doc, {
        viewColumn: vscode.ViewColumn.One,
        preview: false,
      });
    } catch {
      // File not present yet — silently skip
      console.warn(`[DocsToCode Opener] ${filename} not found at ${fileUri.fsPath}`);
    }
  }
}
