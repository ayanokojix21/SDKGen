/**
 * uriHandler.ts — Docs to Code VS Code Extension
 * Dev 4: Handles vscode://docs-to-code.extension/generate?job_id=XXX URIs.
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
  panel.postEvent({ type: 'supervisor', routing_to: 'researcher', reasoning: 'Starting…' });

  // ── 2. Create per-job helpers ─────────────────────────────────────────────
  fileWriters.set(jobId, new FileWriter());
  installers.set(jobId, new Installer());
  openers.set(jobId, new Opener());
  narrators.set(jobId, new Narrator());

  // ── 3. Connect SSE stream ─────────────────────────────────────────────────
  connectSSE(jobId, language, context);
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

  // EventSource is available in VS Code extension host (Node 18+)
  let es: EventSource;
  try {
    es = new EventSource(url);
  } catch {
    // Node may not have native EventSource — use polyfill approach
    vscode.window.showWarningMessage(
      '[Docs to Code] Could not connect to SSE stream. Is the backend running?'
    );
    return;
  }

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

  // ── complete → open main file ──────────────────────────────────────────────
  if (type === 'complete' && opener) {
    await opener.openMainFile(language);
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
