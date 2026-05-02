/**
 * historyView.ts — Docs to Code VS Code Extension
 * Dev 4: TreeDataProvider for the SDK Gen History sidebar.
 *
 * NOTE: Full implementation in Phase 4.
 * This stub registers an empty TreeView so the sidebar panel appears.
 */

import * as vscode from 'vscode';
import * as path from 'path';
import * as fs from 'fs';

interface JobEntry {
  jobId: string;
  apiName: string;
  language: string;
  timestamp: string;
  endpointCount: number;
  rerouteCount: number;
  status: string;
}

/**
 * TreeItem representing a single past SDK generation job.
 */
class JobTreeItem extends vscode.TreeItem {
  constructor(public readonly job: JobEntry) {
    super(job.apiName || job.jobId, vscode.TreeItemCollapsibleState.None);

    this.description = `${job.language} · ${job.timestamp}`;
    this.tooltip = [
      `Job ID: ${job.jobId}`,
      `API: ${job.apiName}`,
      `Language: ${job.language}`,
      `Endpoints: ${job.endpointCount}`,
      `Re-routes: ${job.rerouteCount}`,
      `Status: ${job.status}`,
    ].join('\n');

    this.iconPath = new vscode.ThemeIcon(
      job.status === 'success' ? 'check' : 'warning'
    );

    this.contextValue = 'jobEntry';
  }
}

/**
 * Provides the job history TreeView data.
 * Reads from backend/jobs/ checkpoint files.
 */
export class HistoryViewProvider implements vscode.TreeDataProvider<JobTreeItem> {
  private _onDidChangeTreeData = new vscode.EventEmitter<JobTreeItem | undefined | null>();
  readonly onDidChangeTreeData = this._onDidChangeTreeData.event;

  private jobsDir: string | null = null;

  constructor(private readonly context: vscode.ExtensionContext) {
    // Try to locate backend/jobs/ relative to workspace
    this.resolveJobsDir();
  }

  private resolveJobsDir(): void {
    const workspaceFolders = vscode.workspace.workspaceFolders;
    if (!workspaceFolders || workspaceFolders.length === 0) return;

    // Walk up from workspace root looking for backend/jobs/
    const candidates = [
      path.join(workspaceFolders[0].uri.fsPath, 'backend', 'jobs'),
      path.join(workspaceFolders[0].uri.fsPath, '..', 'backend', 'jobs'),
    ];

    for (const candidate of candidates) {
      if (fs.existsSync(candidate)) {
        this.jobsDir = candidate;
        return;
      }
    }
  }

  refresh(): void {
    this._onDidChangeTreeData.fire(null);
  }

  getTreeItem(element: JobTreeItem): vscode.TreeItem {
    return element;
  }

  async getChildren(_element?: JobTreeItem): Promise<JobTreeItem[]> {
    this.resolveJobsDir();

    if (!this.jobsDir || !fs.existsSync(this.jobsDir)) {
      return [];
    }

    try {
      const dirs = fs.readdirSync(this.jobsDir, { withFileTypes: true })
        .filter((d) => d.isDirectory())
        .map((d) => d.name)
        .reverse(); // Most recent first

      const items: JobTreeItem[] = [];

      for (const jobId of dirs) {
        const metaPath = path.join(this.jobsDir, jobId, 'meta.json');
        if (!fs.existsSync(metaPath)) continue;

        try {
          const meta = JSON.parse(fs.readFileSync(metaPath, 'utf-8')) as Record<string, unknown>;
          const entry: JobEntry = {
            jobId,
            apiName: String(meta['api_name'] || meta['url'] || jobId),
            language: String(meta['language'] || 'python'),
            timestamp: new Date(String(meta['created_at'] || Date.now())).toLocaleString(),
            endpointCount: Number(meta['endpoint_count'] || 0),
            rerouteCount: Number(meta['reroute_count'] || 0),
            status: String(meta['status'] || 'unknown'),
          };
          items.push(new JobTreeItem(entry));
        } catch {
          // Malformed meta.json — skip
        }
      }

      if (items.length === 0) {
        // Show placeholder
        const placeholder = new vscode.TreeItem(
          'No past jobs yet. Generate your first SDK!',
          vscode.TreeItemCollapsibleState.None
        );
        placeholder.iconPath = new vscode.ThemeIcon('info');
        return [placeholder as unknown as JobTreeItem];
      }

      return items;
    } catch (err) {
      console.error('[DocsToCode History] Error reading jobs dir:', err);
      return [];
    }
  }
}
