/**
 * installer.ts — Docs to Code VS Code Extension
 * Dev 4: Runs pip install / npm install in the integrated terminal on install_cmd event.
 */

import * as vscode from 'vscode';

export class Installer {
  private _terminal: vscode.Terminal | null = null;

  /**
   * Run an install command in the integrated terminal.
   * Reuses an existing "Docs to Code" terminal if open.
   *
   * @param command  The shell command, e.g. 'pip install -e .' or 'npm install'
   * @param cwd      Working directory (defaults to workspace root)
   */
  run(command: string, cwd?: string): void {
    const resolvedCwd = cwd ?? this._getWorkspaceRoot();

    if (!this._terminal || this._isTerminalClosed()) {
      this._terminal = vscode.window.createTerminal({
        name: '⚡ Docs to Code',
        cwd: resolvedCwd,
      });
    }

    this._terminal.show(true); // true = don't steal focus
    this._terminal.sendText(command);
  }

  dispose(): void {
    this._terminal?.dispose();
    this._terminal = null;
  }

  private _isTerminalClosed(): boolean {
    return !vscode.window.terminals.includes(this._terminal!);
  }

  private _getWorkspaceRoot(): string | undefined {
    const folders = vscode.workspace.workspaceFolders;
    return folders && folders.length > 0 ? folders[0].uri.fsPath : undefined;
  }
}
