/**
 * popup.js — Docs to Code Chrome Extension
 * Dev 4: Popup controller — terminal renderer, state management.
 *
 * SSE is now managed by the background service worker to survive popup close.
 * This file receives events via chrome.runtime.onMessage and renders them.
 *
 * Flow:
 *   Generate click → GET_PAGE_CONTENT → POST /generate/start → job_id
 *   → background.js opens EventSource → relays events via chrome.runtime
 *   → renderLine() per event
 *   → on narrate → TTS
 *   → on complete → enable action buttons
 */

'use strict';

// ─── Agent colour map ────────────────────────────────────────────────────────
const AGENT_COLOURS = {
  supervisor:             'var(--c-supervisor)',
  reroute:                'var(--c-reroute)',
  researcher:             'var(--c-researcher)',
  researcher_analysing:   'var(--c-researcher)',
  researcher_crawl_plan:  'var(--c-researcher)',
  researcher_scraping:    'var(--c-researcher)',
  researcher_scraped:     'var(--c-researcher)',
  researcher_serper:      'var(--c-researcher)',
  researcher_done:        'var(--c-researcher)',
  architect:              'var(--c-architect)',
  architect_validating:   'var(--c-architect)',
  architect_fix:          'var(--c-architect)',
  architect_done:         'var(--c-architect)',
  architect_error:        'var(--c-qa-fail)',
  engineer:               'var(--c-engineer)',
  engineer_writing:       'var(--c-engineer)',
  engineer_file_done:     'var(--c-engineer)',
  engineer_done:          'var(--c-engineer)',
  engineer_syntax_error:  'var(--c-qa-fail)',
  engineer_error:         'var(--c-qa-fail)',
  qa_test_pass:           'var(--c-qa-pass)',
  qa_test_fail:           'var(--c-qa-fail)',
  qa_done:                'var(--c-qa-pass)',
  qa_error:               'var(--c-qa-fail)',
  packager:               'var(--c-packager)',
  packager_done:          'var(--c-packager)',
  packager_fail:          'var(--c-qa-fail)',
  file_ready:             'var(--c-packager)',
  narrate:                'var(--c-narrate)',
  complete:               'var(--c-complete)',
  agent_warn:             'var(--c-warn)',
  safety_cutoff:          'var(--c-safety)',
  error:                  'var(--c-qa-fail)',
};

// ─── State ───────────────────────────────────────────────────────────────────
let activeJobId = null;
let selectedLanguage = 'python';
let selectedOutput = 'vscode';
let isGenerating = false;

// ─── DOM references ───────────────────────────────────────────────────────────
const urlInput        = document.getElementById('url-input');
const generateBtn     = document.getElementById('generate-btn');
const generateBtnText = document.getElementById('generate-btn-text');
const generateSpinner = document.getElementById('generate-spinner');
const terminalLog     = document.getElementById('terminal-log');
const clearLogBtn     = document.getElementById('clear-log-btn');
const narrateToggle   = document.getElementById('narrate-toggle');
const downloadBtn     = document.getElementById('download-btn');
const openVSCodeBtn   = document.getElementById('open-vscode-btn');
const vsBadge         = document.getElementById('vs-code-badge');
const resumeBanner    = document.getElementById('resume-banner');
const resumeBtn       = document.getElementById('resume-btn');
const resumeDismiss   = document.getElementById('resume-dismiss');
const backendBanner   = document.getElementById('backend-banner');
const backendCmd      = document.getElementById('backend-cmd');
const cmdCopied       = document.getElementById('cmd-copied');
const pasteBtn        = document.getElementById('paste-btn');

const assistantSection= document.getElementById('assistant-section');
const askSdkBtn       = document.getElementById('ask-sdk-btn');
const assistantStatus = document.getElementById('assistant-status');
const askSdkText      = document.getElementById('ask-sdk-text');

let isAssistantActive = false;

if (askSdkBtn) {
  askSdkBtn.addEventListener('click', async () => {
    if (isAssistantActive) {
      await window.convAi.stopConversation();
      isAssistantActive = false;
      askSdkBtn.classList.remove('active');
      askSdkText.textContent = 'Ask about this SDK';
      assistantStatus.textContent = '';
    } else {
      try {
        askSdkBtn.disabled = true;
        assistantStatus.textContent = 'Connecting...';
        await window.convAi.startConversation((mode) => {
          assistantStatus.textContent = mode === 'speaking' ? 'Agent is speaking...' : 'Listening...';
        });
        isAssistantActive = true;
        askSdkBtn.classList.add('active');
        askSdkText.textContent = 'Stop Assistant';
      } catch (err) {
        assistantStatus.textContent = 'Error connecting.';
        console.error(err);
      } finally {
        askSdkBtn.disabled = false;
      }
    }
  });
}

// ─── Initialise ───────────────────────────────────────────────────────────────
async function init() {
  // 1. Auto-fill URL from active tab
  await autoFillUrl();

  // 2. Check VS Code connection
  checkVSCodeStatus();

  // 3. Check backend health
  await checkBackend();

  // 4. Check for in-progress job and replay buffered events
  await checkResumeState();
}

// ─── URL auto-fill ────────────────────────────────────────────────────────────
async function autoFillUrl() {
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (tab && tab.url && !tab.url.startsWith('chrome://')) {
      urlInput.value = tab.url;
    }
  } catch (_) {}
}

// ─── VS Code badge ────────────────────────────────────────────────────────────
async function checkVSCodeStatus() {
  try {
    const response = await chrome.runtime.sendMessage({ type: 'POPUP_OPENED' });
    updateVSCodeBadge(response?.status === 'connected', response?.port);
  } catch (_) {
    updateVSCodeBadge(false);
  }
}

function updateVSCodeBadge(connected, port) {
  const badge = vsBadge;
  const label = badge.querySelector('.badge-label');

  if (connected) {
    badge.className = 'badge badge--connected';
    label.textContent = `VS Code :${port || 47291}`;
  } else {
    // ── Edge case C1: VS Code not detected ──────────────────────────────────
    badge.className = 'badge badge--disconnected';
    label.textContent = 'VS Code';

    // Switch output to ZIP as primary CTA
    selectedOutput = 'zip';
    document.querySelectorAll('#output-toggle .toggle-btn').forEach((b) => {
      b.classList.toggle('toggle-btn--active', b.dataset.value === 'zip');
    });

    // Show install hint in terminal (non-blocking)
    appendLine(
      '○ VS Code extension not detected. Output set to Download ZIP.',
      'var(--text-secondary)'
    );
    appendLine(
      '  Install: Extensions → search "Docs to Code" · or load from vscode-extension/',
      'var(--text-secondary)'
    );
  }
}

// ─── Backend health check ─────────────────────────────────────────────────────
async function checkBackend() {
  const ok = await window.dtcApi.checkBackendHealth();
  if (!ok) {
    backendBanner.classList.remove('hidden');
  }
}

// ─── Resume / replay from background buffer ──────────────────────────────────
async function checkResumeState() {
  try {
    const sseState = await chrome.runtime.sendMessage({ type: 'GET_SSE_STATE' });

    if (sseState && sseState.jobId) {
      activeJobId = sseState.jobId;

      // Replay buffered events
      if (sseState.buffer && sseState.buffer.length > 0) {
        appendLine(`↻ Reconnected to job ${sseState.jobId.slice(0, 8)}… — replaying ${sseState.buffer.length} events`, 'var(--c-supervisor)');

        for (const evt of sseState.buffer) {
          renderLine(evt);
        }
      }

      if (sseState.finished) {
        // Job already finished while popup was closed
        setGenerating(false);
        // Check if the last event was an error
        const lastEvt = sseState.buffer?.[sseState.buffer.length - 1];
        if (lastEvt) {
          const lastType = lastEvt.type || '';
          if (lastType === 'complete') {
            onComplete(activeJobId, lastEvt);
          } else if (lastType === 'error' || lastType === 'safety_cutoff' || lastEvt.status === 'failed') {
            onFailed(lastEvt);
          }
        }
      } else if (sseState.connected) {
        // Job still running — set UI to generating state
        setGenerating(true);
      } else {
        // Not connected but not finished — show resume banner
        const resumeText = document.getElementById('resume-text');
        resumeText.innerHTML = `Job <code>${sseState.jobId.slice(0, 8)}</code> may be in progress — <button id="resume-btn" class="link-btn">resume</button>`;
        resumeBanner.classList.remove('hidden');

        document.getElementById('resume-btn').addEventListener('click', () => {
          resumeBanner.classList.add('hidden');
          setGenerating(true);
          chrome.runtime.sendMessage({ type: 'START_SSE', jobId: sseState.jobId });
        });
      }
    } else {
      // Check session storage as fallback
      const { activeJobId: savedJobId } = await chrome.storage.session.get('activeJobId');
      if (savedJobId) {
        activeJobId = savedJobId;
        const resumeText = document.getElementById('resume-text');
        resumeText.innerHTML = `Job <code>${savedJobId.slice(0, 8)}</code> may be in progress — <button id="resume-btn" class="link-btn">resume</button>`;
        resumeBanner.classList.remove('hidden');

        document.getElementById('resume-btn').addEventListener('click', () => {
          resumeBanner.classList.add('hidden');
          setGenerating(true);
          chrome.runtime.sendMessage({ type: 'START_SSE', jobId: savedJobId });
        });
      }
    }
  } catch (_) {}
}

// ─── Language toggle ──────────────────────────────────────────────────────────
document.getElementById('language-toggle').addEventListener('click', (e) => {
  const btn = e.target.closest('.toggle-btn');
  if (!btn) return;
  selectedLanguage = btn.dataset.value;
  document.querySelectorAll('#language-toggle .toggle-btn').forEach((b) => {
    b.classList.toggle('toggle-btn--active', b === btn);
  });
});

// ─── Output toggle ────────────────────────────────────────────────────────────
document.getElementById('output-toggle').addEventListener('click', (e) => {
  const btn = e.target.closest('.toggle-btn');
  if (!btn) return;
  selectedOutput = btn.dataset.value;
  document.querySelectorAll('#output-toggle .toggle-btn').forEach((b) => {
    b.classList.toggle('toggle-btn--active', b === btn);
  });
});

// ─── Paste button ─────────────────────────────────────────────────────────────
pasteBtn.addEventListener('click', async () => {
  try {
    const text = await navigator.clipboard.readText();
    if (text) urlInput.value = text;
  } catch (_) {}
});

// ─── Narrate toggle ───────────────────────────────────────────────────────────
narrateToggle.addEventListener('change', () => {
  if (!window.tts.available) {
    narrateToggle.checked = false; // Edge case C4 — silent disable
    return;
  }
  if (narrateToggle.checked) {
    window.tts.enable();
  } else {
    window.tts.disable();
  }
});

// ─── Clear log ────────────────────────────────────────────────────────────────
clearLogBtn.addEventListener('click', () => {
  terminalLog.innerHTML = '';
});

// ─── Copy backend command ──────────────────────────────────────────────────────
backendCmd.addEventListener('click', async () => {
  try {
    await navigator.clipboard.writeText(backendCmd.textContent.trim());
    cmdCopied.classList.remove('hidden');
    setTimeout(() => cmdCopied.classList.add('hidden'), 2000);
  } catch (_) {}
});

// ─── Resume dismiss ───────────────────────────────────────────────────────────
resumeDismiss.addEventListener('click', () => {
  resumeBanner.classList.add('hidden');
  chrome.runtime.sendMessage({ type: 'STOP_SSE' });
  activeJobId = null;
});

// ─── Generate button ──────────────────────────────────────────────────────────
generateBtn.addEventListener('click', handleGenerate);

async function handleGenerate() {
  const url = urlInput.value.trim();
  if (!url) {
    urlInput.focus();
    return;
  }

  // Validate URL
  try { new URL(url); } catch {
    appendLine('✕ Invalid URL — please enter a full https:// URL', 'var(--c-qa-fail)');
    return;
  }

  // Hide backend banner if visible (user may have started backend)
  backendBanner.classList.add('hidden');

  setGenerating(true);
  clearTerminal();

  appendLine('⚡ Capturing page content…', 'var(--c-supervisor)');

  // 1. Get page content from content.js
  let pageContent = '';
  let pageLinks = [];

  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (tab?.id) {
      const response = await chrome.tabs.sendMessage(tab.id, { type: 'GET_PAGE_CONTENT' });
      pageContent = response?.content || '';
      pageLinks = response?.links || [];
      appendLine(
        `✓ Captured ${pageContent.length.toLocaleString()} chars · ${pageLinks.length} links`,
        'var(--c-qa-pass)'
      );
    }
  } catch (err) {
    appendLine('⚠ Could not capture page — using URL only', 'var(--c-warn)');
  }

  // 2. POST /generate/start
  appendLine('→ Starting SDK generation…', 'var(--c-supervisor)');

  let jobId;
  try {
    const result = await window.dtcApi.postStart({
      targetUrl: url,
      language: selectedLanguage,
      pageContent,
      pageLinks,
    });
    jobId = result.job_id;
  } catch (err) {
    const isNetworkErr = err.message.includes('Failed to fetch') || err.message.includes('NetworkError');
    if (isNetworkErr) {
      backendBanner.classList.remove('hidden');
      appendLine('✕ Backend not reachable. See banner above.', 'var(--c-qa-fail)');
    } else {
      appendLine(`✕ Error: ${err.message}`, 'var(--c-qa-fail)');
    }
    setGenerating(false);
    return;
  }

  // 3. Store job_id
  activeJobId = jobId;
  await chrome.storage.session.set({ activeJobId: jobId });

  appendLine(`✓ Job started · ID: ${jobId.slice(0, 8)}…`, 'var(--c-qa-pass)');

  // 4. Notify VS Code bridge
  if (selectedOutput === 'vscode') {
    await window.dtcBridge.sendNewJob(jobId, url, selectedLanguage);
  }

  // 5. Inject overlay on docs page
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (tab?.id) {
      chrome.tabs.sendMessage(tab.id, { type: 'SHOW_OVERLAY', jobId });
    }
  } catch (_) {}

  // 6. Tell background to connect SSE (background owns the EventSource)
  chrome.runtime.sendMessage({ type: 'START_SSE', jobId });
}

// ─── Listen for SSE events from background service worker ─────────────────────

chrome.runtime.onMessage.addListener((message, _sender, _sendResponse) => {
  if (message.type !== 'SSE_EVENT') return;

  const data = message.data;
  if (!data) return;

  // Forward to overlay
  forwardToOverlay(data);

  // Render in popup terminal
  renderLine(data);

  // Handle special events
  const evtType = data.type || data.event || '';

  // 'done' is the backend sentinel — job complete
  if (evtType === 'done') {
    setGenerating(false);
    return;
  }

  if (evtType === 'reroute') {
    triggerRerouteFlash();
  }

  if (evtType === 'narrate') {
    window.tts.speak(data.text || '');
  }

    if (type === 'packager_done') {
      if (data.assistant_agent_id) {
        window.convAi.setAgentId(data.assistant_agent_id);
        assistantSection.classList.remove('hidden');
      }
    }

  // Forward file_ready to VS Code bridge for file injection
  if (evtType === 'file_ready' && selectedOutput === 'vscode') {
    window.dtcBridge.onFileWritten(data.filename || '');
  }

  if (evtType === 'complete') {
    onComplete(activeJobId, data);
  }

  if (evtType === 'error') {
    onFailed(data);
  }

  if (evtType === 'safety_cutoff' || data.status === 'failed') {
    onFailed(data);
  }
});

// ─── Terminal rendering ───────────────────────────────────────────────────────

/**
 * Build a formatted terminal line for a given SSE event.
 * @param {Object} data  Parsed SSE event
 */
function renderLine(data) {
  const type = data.type || data.event || '';
  const colour = AGENT_COLOURS[type] || 'var(--text-secondary)';
  let text = '';

  // Skip the 'done' sentinel — handled elsewhere
  if (type === 'done') return;

  switch (type) {
    case 'supervisor':
      text = `🧠 [SUPERVISOR] → ${data.routing_to || '?'} · ${data.reasoning || ''}`;
      break;
    case 'reroute':
      text = `↩ [REROUTE] ${data.from} → ${data.to} · ${data.reason || ''}`;
      break;
    case 'researcher_analysing':
      text = `🔍 [RESEARCHER] Analysing ${data.goal || data.link_count || '?'}…`;
      break;
    case 'researcher_crawl_plan': {
      const selCount = data.selected ? data.selected.length : (data.selected_count || 0);
      text = `📋 [RESEARCHER] Plan: ${selCount} selected · ${data.skipped_count || 0} skipped`;
      break;
    }
    case 'researcher_scraping':
      text = `🌐 [RESEARCHER] Scraping ${data.url || ''}`;
      break;
    case 'researcher_scraped':
      text = `✓ [RESEARCHER] ${data.url || ''} — ${(data.char_count || 0).toLocaleString()} chars`;
      break;
    case 'researcher_serper':
      text = `🔎 [RESEARCHER] Web search: ${data.query || ''}`;
      break;
    case 'researcher_done':
      text = `✓ [RESEARCHER] Done · ${data.page_count || '?'} pages crawled`;
      break;
    case 'architect_validating':
      text = `🔬 [ARCHITECT] Validating schema… (${(data.context_length || 0).toLocaleString()} chars context)`;
      break;
    case 'architect_fix':
      text = `🔧 [ARCHITECT] Fix: ${data.fix || ''}`;
      break;
    case 'architect_done':
      text = `✓ [ARCHITECT] Schema ready · ${data.endpoint_count || '?'} endpoints · ${data.fixes_count || 0} fixes`;
      break;
    case 'architect_error':
      text = `✕ [ARCHITECT] Error: ${data.error || ''}`;
      break;
    case 'engineer_writing':
      text = `✍ [ENGINEER] Writing ${data.filename || ''}…`;
      break;
    case 'engineer_file_done':
      text = `✓ [ENGINEER] ${data.filename || ''} (${data.line_count || '?'} lines)`;
      break;
    case 'engineer_done':
      text = `📦 [ENGINEER] SDK complete · ${data.file_count || '?'} files · ${data.syntax_errors || 0} syntax issues`;
      break;
    case 'engineer_syntax_error':
      text = `✕ [ENGINEER] Syntax error in ${data.filename || ''} — ${data.error || ''}`;
      break;
    case 'engineer_error':
      text = `✕ [ENGINEER] Error: ${data.error || ''}`;
      break;
    case 'qa_test_pass':
      text = `✓ [QA] ${data.endpoint || ''} → ${data.status_code || 200}`;
      break;
    case 'qa_test_fail':
      text = `✕ [QA] ${data.endpoint || ''} → expected ${data.expected || '?'} got ${data.actual || data.status_code || 'err'} ${data.error ? '· ' + data.error : ''}`;
      break;
    case 'qa_done':
      text = `📊 [QA] ${data.passed || 0}/${data.total || 0} passed · ${data.failed || 0} failed`;
      break;
    case 'qa_error':
      text = `✕ [QA] Error: ${data.error || ''}`;
      break;
    case 'file_ready':
      text = `📁 [PACKAGER] ${data.filename || ''} → VS Code`;
      break;
    case 'packager_done':
      text = `📦 [PACKAGER] ${data.file_count || '?'} files packaged`;
      break;
    case 'packager_fail':
      text = `✕ [PACKAGER] Failed: ${data.reason || ''}`;
      break;
    case 'narrate':
      text = `🔊 [NARRATE] ${data.text || ''}`;
      break;
    case 'complete':
      text = `🎉 [COMPLETE] SDK generation successful!`;
      break;
    case 'agent_warn':
      text = `⚠ [WARN] ${data.message || JSON.stringify(data)}`;
      break;
    case 'safety_cutoff':
      text = `⛔ [SAFETY] ${data.message || 'Safety cutoff reached — max iterations hit'}`;
      break;
    case 'error':
      text = `✕ [ERROR] ${data.message || 'An error occurred'}`;
      break;
    default:
      // Generic fallback — still show it
      text = `[${type || 'event'}] ${data.message || JSON.stringify(data).slice(0, 120)}`;
  }

  appendLine(text, colour);
}

/**
 * Append a plain text line to the terminal.
 * @param {string} text
 * @param {string} colour  CSS colour string
 */
function appendLine(text, colour) {
  // Remove placeholder if present
  const placeholder = terminalLog.querySelector('.terminal-placeholder');
  if (placeholder) placeholder.remove();

  const line = document.createElement('div');
  line.className = 'terminal-line';

  const prefix = document.createElement('div');
  prefix.className = 'terminal-prefix';
  prefix.style.background = colour;

  const textEl = document.createElement('div');
  textEl.className = 'terminal-text';
  textEl.style.color = colour;
  textEl.textContent = text;

  const ts = document.createElement('div');
  ts.className = 'terminal-ts';
  ts.textContent = new Date().toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', second: '2-digit' });

  line.appendChild(prefix);
  line.appendChild(textEl);
  line.appendChild(ts);
  terminalLog.appendChild(line);

  // Auto-scroll
  terminalLog.scrollTop = terminalLog.scrollHeight;
}

function clearTerminal() {
  terminalLog.innerHTML = '';
}

// ─── Reroute amber flash ──────────────────────────────────────────────────────
function triggerRerouteFlash() {
  terminalLog.classList.remove('terminal-log--reroute');
  // Force reflow to restart animation
  void terminalLog.offsetWidth;
  terminalLog.classList.add('terminal-log--reroute');
  setTimeout(() => terminalLog.classList.remove('terminal-log--reroute'), 2100);
}

// ─── Completion / failure handlers ────────────────────────────────────────────
function onComplete(jobId, data) {
  setGenerating(false);

  // Enable action buttons
  downloadBtn.disabled = false;
  openVSCodeBtn.disabled = false;

  // Wire download button
  downloadBtn.onclick = () => window.dtcApi.downloadZip(jobId);

  // Wire VS Code button
  openVSCodeBtn.onclick = () => window.dtcBridge.openInVSCode(jobId);

  // Auto-trigger the selected output action
  if (selectedOutput === 'zip') {
    appendLine('⏳ Downloading ZIP automatically...', 'var(--text-secondary)');
    window.dtcApi.downloadZip(jobId);
  } else if (selectedOutput === 'vscode') {
    appendLine('⏳ Opening in VS Code automatically...', 'var(--text-secondary)');
    window.dtcBridge.openInVSCode(jobId);
  }
}

function onFailed(data) {
  setGenerating(false);
  appendLine(`✕ Generation stopped: ${data.message || data.failure_reason || 'unknown reason'}`, 'var(--c-qa-fail)');
}

// ─── Generating state ────────────────────────────────────────────────────────
function setGenerating(state) {
  isGenerating = state;
  generateBtn.disabled = state;
  generateBtnText.textContent = state ? 'Generating…' : 'Generate SDK';
  generateSpinner.classList.toggle('hidden', !state);

  if (!state) {
    downloadBtn.disabled = !activeJobId;
    openVSCodeBtn.disabled = !activeJobId;
  }
}

// ─── Overlay forwarding ───────────────────────────────────────────────────────
async function forwardToOverlay(event) {
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (tab?.id) {
      chrome.tabs.sendMessage(tab.id, { type: 'UPDATE_OVERLAY', event });
    }
  } catch (_) {}
}

// ─── Boot ─────────────────────────────────────────────────────────────────────
init();
