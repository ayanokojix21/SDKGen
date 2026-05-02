/**
 * wsServer.ts — Docs to Code VS Code Extension
 * Dev 4: WebSocket server on port 47291 (fallback: 47292, 47293).
 *
 * Receives `new_job` messages from the Chrome extension.
 * Sends `vscode_ready` and `port_info` back.
 * Forwards `file_written` confirmations to connected Chrome clients.
 */

import * as vscode from 'vscode';
import { WebSocketServer, WebSocket } from 'ws';
import type { IncomingMessage } from 'http';

const PORTS = [47291, 47292, 47293];

export interface NewJobMessage {
  type: 'new_job';
  job_id: string;
  url: string;
  language: string;
}

export type WSServerMessage = NewJobMessage | { type: string; [key: string]: unknown };

/** Callback invoked when Chrome sends a new_job message. */
export type NewJobHandler = (msg: NewJobMessage) => void;

/**
 * WebSocket server that Chrome extension connects to.
 * Handles port fallback and relays file_written confirmations.
 */
export class WSServer {
  private wss: WebSocketServer | null = null;
  private activePort: number | null = null;
  private clients: Set<WebSocket> = new Set();
  private newJobHandlers: NewJobHandler[] = [];

  /** Start the server, trying ports in order. */
  async start(): Promise<void> {
    for (const port of PORTS) {
      try {
        await this.listen(port);
        this.activePort = port;
        console.log(`[DocsToCode WS] Listening on port ${port}`);
        return;
      } catch (err) {
        console.warn(`[DocsToCode WS] Port ${port} unavailable:`, err);
      }
    }

    // All ports failed
    vscode.window.showWarningMessage(
      '[Docs to Code] Could not start WebSocket server (ports 47291–47293 all in use). ' +
      'Chrome extension bridge via URI handler will still work.'
    );
  }

  /** Stop the WebSocket server. */
  stop(): void {
    if (this.wss) {
      this.wss.close();
      this.wss = null;
      this.activePort = null;
      this.clients.clear();
    }
  }

  /** Get the port the server is actually listening on. */
  get port(): number | null {
    return this.activePort;
  }

  /** Register a handler for incoming new_job messages. */
  onNewJob(handler: NewJobHandler): void {
    this.newJobHandlers.push(handler);
  }

  /**
   * Broadcast a message to all connected Chrome clients.
   * Used for file_written confirmations, etc.
   */
  broadcast(data: object): void {
    const payload = JSON.stringify(data);
    for (const client of this.clients) {
      if (client.readyState === WebSocket.OPEN) {
        client.send(payload);
      }
    }
  }

  /** Send file_written confirmation to Chrome extension. */
  confirmFileWritten(filename: string): void {
    this.broadcast({ type: 'file_written', filename });
  }

  // ── Private ──────────────────────────────────────────────────────────────

  private listen(port: number): Promise<void> {
    return new Promise((resolve, reject) => {
      const wss = new WebSocketServer({ port });

      wss.once('error', (err) => {
        wss.close();
        reject(err);
      });

      wss.once('listening', () => {
        this.wss = wss;
        resolve();

        // Send port_info if we're on a fallback port
        if (port !== PORTS[0]) {
          // Clients will connect shortly — we'll send port_info on first connect
        }

        wss.on('connection', (ws: WebSocket, _req: IncomingMessage) => {
          this.clients.add(ws);

          // Greet Chrome
          ws.send(JSON.stringify({ type: 'vscode_ready', port }));

          // If on fallback port, tell Chrome
          if (port !== PORTS[0]) {
            ws.send(JSON.stringify({ type: 'port_info', port }));
          }

          ws.on('message', (raw) => {
            let data: WSServerMessage;
            try {
              data = JSON.parse(raw.toString()) as WSServerMessage;
            } catch {
              console.warn('[DocsToCode WS] Received non-JSON message:', raw.toString());
              return;
            }

            if (data.type === 'new_job') {
              const msg = data as NewJobMessage;
              console.log(`[DocsToCode WS] new_job received: job_id=${msg.job_id}`);
              for (const handler of this.newJobHandlers) {
                handler(msg);
              }
            }
          });

          ws.on('close', () => {
            this.clients.delete(ws);
          });

          ws.on('error', (err) => {
            console.warn('[DocsToCode WS] Client error:', err);
            this.clients.delete(ws);
          });
        });
      });
    });
  }
}
