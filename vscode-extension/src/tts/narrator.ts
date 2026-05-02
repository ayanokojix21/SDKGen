/**
 * narrator.ts — Docs to Code VS Code Extension
 * Dev 4: Posts speak messages to the AgentPanel Webview for TTS narration.
 */

import { AgentPanel } from '../panels/AgentPanel';

export class Narrator {
  /**
   * Send a narrate event to the Agent Panel webview for TTS playback.
   * The webview handles the actual Web Speech API call.
   *
   * @param jobId  Active job ID (used to find the right panel)
   * @param text   Text to speak
   */
  speak(jobId: string, text: string): void {
    const panel = AgentPanel.get(jobId);
    if (panel) {
      panel.speak(text);
    }
  }
}
