/**
 * tts.js — Docs to Code Chrome Extension
 * Dev 4: Text-to-speech controller using Web Speech API.
 *
 * Voice priority: en-GB Google > Daniel > Alex > voices[0]
 * Silent fallback if speechSynthesis unavailable (Edge case C4).
 */

'use strict';

class TTSController {
  constructor() {
    this.available = 'speechSynthesis' in window;
    this.enabled = false;
    this.speaking = false;
    this._voices = [];

    if (this.available) {
      // Voices load async in Chrome — cache them
      speechSynthesis.addEventListener('voiceschanged', () => {
        this._voices = speechSynthesis.getVoices();
      });
      this._voices = speechSynthesis.getVoices();
    }
  }

  /**
   * Pick the best available voice.
   * Priority: en-GB Google > Daniel > Alex > any en > voices[0]
   * @returns {SpeechSynthesisVoice|null}
   */
  _pickVoice() {
    if (!this._voices.length) {
      this._voices = speechSynthesis.getVoices();
    }

    const priorities = [
      (v) => v.lang === 'en-GB' && v.name.includes('Google'),
      (v) => v.name.includes('Daniel'),
      (v) => v.name.includes('Alex'),
      (v) => v.lang.startsWith('en'),
    ];

    for (const test of priorities) {
      const match = this._voices.find(test);
      if (match) return match;
    }

    return this._voices[0] || null;
  }

  /**
   * Speak the given text if TTS is available and enabled.
   * Cancels any current utterance first.
   * @param {string} text
   */
  speak(text) {
    if (!this.available || !this.enabled || !text) return;

    speechSynthesis.cancel();

    const utterance = new SpeechSynthesisUtterance(text);
    utterance.rate = 1.05;
    utterance.pitch = 0.95;

    const voice = this._pickVoice();
    if (voice) utterance.voice = voice;

    utterance.addEventListener('start', () => { this.speaking = true; });
    utterance.addEventListener('end', () => { this.speaking = false; });
    utterance.addEventListener('error', () => { this.speaking = false; });

    speechSynthesis.speak(utterance);
  }

  /**
   * Toggle TTS on/off.
   * @returns {boolean} New enabled state
   */
  toggle() {
    if (!this.available) return false;
    this.enabled = !this.enabled;
    if (!this.enabled) this.stop();
    return this.enabled;
  }

  /**
   * Enable TTS.
   */
  enable() {
    if (this.available) this.enabled = true;
  }

  /**
   * Disable TTS and cancel any current speech.
   */
  disable() {
    this.enabled = false;
    this.stop();
  }

  /**
   * Stop any current utterance.
   */
  stop() {
    if (this.available) speechSynthesis.cancel();
    this.speaking = false;
  }
}

// Export singleton
window.tts = new TTSController();
