/**
 * uriHandler.ts — Docs to Code VS Code Extension
 * Dev 4: Handles vscode://docs-to-code-team.docs-to-code/generate?job_id=XXX URIs.
 *
 * Phase 3 full implementation:
 *   - Opens AgentPanel
 *   - Connects SSE stream to backend
 *   - Routes each event: AgentPanel, FileWriter, Installer, Opener, Narrator
 */

import * as vscode from 'vscode';
import { AgentPanel } from '../panels/AgentPanel';
import { FileWriter } from '../injector/fileWriter';
import { Installer } from '../injector/installer';
import { Opener } from '../injector/opener';
import { Narrator } from '../tts/narrator';
import { refreshHistory } from '../extension';

const EventSource = require('eventsource');
const BACKEND_BASE = 'http://localhost:8000';

// Per-job singletons (cleaned up on complete/error)
const fileWriters = new Map<string, FileWriter>();
const installers = new Map<string, Installer>();
const openers = new Map<string, Opener>();
const narrators = new Map<string, Narrator>();
const eventSources = new Map<string, EventSource>();

/**
 * Main URI handler — called from extension.ts and WS server new_job.
 */
export function handleUri(uri: vscode.Uri, context: vscode.ExtensionContext): void {
  const params = new URLSearchParams(uri.query);
  const jobId = params.get('job_id');
  const language = params.get('language') ?? 'python';

  if (!jobId) {
    vscode.window.showErrorMessage('[Docs to Code] No job_id in URI.');
    return;
  }

  console.log(`[DocsToCode URI] job_id=${jobId} language=${language}`);

  // ── 1. Open Agent Panel ───────────────────────────────────────────────────
  const panel = AgentPanel.createOrShow(context.extensionUri, jobId);

  // ── 2. Create per-job helpers ─────────────────────────────────────────────
  fileWriters.set(jobId, new FileWriter());
  installers.set(jobId, new Installer());
  openers.set(jobId, new Opener());
  narrators.set(jobId, new Narrator());

  // ── 3. Try to restore a completed job first, then fall back to SSE ────────
  tryRestoreCompletedJob(jobId, language, context).then((restored) => {
    if (!restored) {
      // Job is still running — connect to live SSE stream
      panel.postEvent({ type: 'supervisor', routing_to: 'researcher', reasoning: 'Starting…' });
      connectSSE(jobId, language, context);
    }
  });
}

/**
 * Checks if the job already has files on the backend (completed job).
 * If so, writes them directly to the workspace without SSE.
 * Returns true if the job was restored, false if SSE should be used.
 */
async function tryRestoreCompletedJob(
  jobId: string,
  language: string,
  _context: vscode.ExtensionContext
): Promise<boolean> {
  // Try to fetch files directly. 200 = ready, 202 = still running, 404 = not found.
  let files: Record<string, string>;
  try {
    const resp = await fetch(`${BACKEND_BASE}/job/${encodeURIComponent(jobId)}/files`);
    if (resp.status !== 200) {
      return false; // Still running or not found — fall back to SSE
    }
    files = await resp.json() as Record<string, string>;
  } catch {
    return false;
  }

  // Files are ready — restore state
  const panel = AgentPanel.get(jobId);
  panel?.postEvent({ type: 'supervisor', routing_to: 'packager', reasoning: 'Restoring completed job…' });

  const fw = fileWriters.get(jobId);
  const opener = openers.get(jobId);

    for (const [filename, content] of Object.entries(files)) {
      panel?.postEvent({ type: 'file_ready', filename });
      if (fw) {
        const written = await fw.write(filename, content);
        if (written) panel?.confirmFileWritten(filename);
      }
    }

    panel?.postEvent({ type: 'complete' });
    if (opener) await opener.openMainFile(language);
    refreshHistory();
    cleanup(jobId);
    return true;
}

/**
 * Connect an EventSource to the backend SSE stream and route events.
 */
function connectSSE(jobId: string, language: string, _context: vscode.ExtensionContext): void {
  // Close any existing stream for this job
  const existing = eventSources.get(jobId);
  if (existing) {
    existing.close();
    eventSources.delete(jobId);
  }

  const url = `${BACKEND_BASE}/generate/stream?job_id=${encodeURIComponent(jobId)}`;

  // We use the eventsource polyfill since Node.js 18 doesn't have native EventSource
  const es = new EventSource(url);

  eventSources.set(jobId, es);

  es.addEventListener('message', async (e: MessageEvent) => {
    let data: Record<string, unknown>;
    try {
      data = JSON.parse(e.data as string) as Record<string, unknown>;
    } catch {
      return;
    }

    await routeEvent(jobId, language, data);
  });

  es.addEventListener('error', () => {
    if (es.readyState === EventSource.CLOSED) {
      console.warn(`[DocsToCode SSE] Stream closed for job ${jobId}`);
      cleanup(jobId);
    }
  });
}

/**
 * Route a single SSE event to the correct handler(s).
 */
async function routeEvent(
  jobId: string,
  language: string,
  event: Record<string, unknown>
): Promise<void> {
  const type = String(event.type ?? event.event ?? '');

  // ── Always: forward to Agent Panel ────────────────────────────────────────
  const panel = AgentPanel.get(jobId);
  if (panel) panel.postEvent(event);

  const fw = fileWriters.get(jobId);
  const inst = installers.get(jobId);
  const opener = openers.get(jobId);
  const narrator = narrators.get(jobId);

  // ── file_ready → write to workspace ───────────────────────────────────────
  if (type === 'file_ready' && fw) {
    const filename = String(event.filename ?? '');
    const content = String(event.content ?? '');
    if (filename && content) {
      const writtenPath = await fw.write(filename, content);
      if (writtenPath && panel) {
        panel.confirmFileWritten(filename);
      }
    }
  }

  // ── install_cmd → run in terminal ─────────────────────────────────────────
  if (type === 'install_cmd' && inst) {
    const cmd = String(event.command ?? '');
    if (cmd) inst.run(cmd);
  }

  // ── narrate → TTS via webview ──────────────────────────────────────────────
  if (type === 'narrate' && narrator) {
    narrator.speak(jobId, String(event.text ?? ''));
  }

  // ── complete → open main file ──────────────────────────────────────────────────────
  if (type === 'complete' && opener) {
    await opener.openMainFile(language);
    refreshHistory(); // update History sidebar
    cleanup(jobId);
  }

  // ── failed / safety_cutoff → cleanup ──────────────────────────────────────
  if (type === 'safety_cutoff' || event['status'] === 'failed') {
    cleanup(jobId);
  }
}

/**
 * Clean up per-job resources on completion or failure.
 */
function cleanup(jobId: string): void {
  eventSources.get(jobId)?.close();
  eventSources.delete(jobId);
  installers.get(jobId)?.dispose();
  installers.delete(jobId);
  fileWriters.get(jobId)?.reset();
  fileWriters.delete(jobId);
  openers.delete(jobId);
  narrators.delete(jobId);
}
