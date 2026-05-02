/**
 * content.js — Docs to Code Chrome Extension
 * Dev 4: Content script — page capture, link extraction, overlay panel.
 *
 * Injected into every page at document_idle.
 * Listens for messages from popup.js and background.js.
 */

'use strict';

// ─── Overlay state ───────────────────────────────────────────────────────────
let overlayPanel = null;
let overlayLog = null;
let overlayMinimised = false;

// ─── Agent colour map (matches popup CSS variables) ───────────────────────────
const AGENT_COLOURS = {
  supervisor:          '#a78bfa',
  reroute:             '#fbbf24',
  researcher:          '#60a5fa',
  researcher_crawl_plan: '#60a5fa',
  researcher_scraping: '#60a5fa',
  researcher_scraped:  '#60a5fa',
  researcher_serper:   '#60a5fa',
  researcher_done:     '#60a5fa',
  researcher_analysing:'#60a5fa',
  architect:           '#34d399',
  architect_validating:'#34d399',
  architect_fix:       '#34d399',
  architect_done:      '#34d399',
  architect_error:     '#f87171',
  engineer:            '#86efac',
  engineer_writing:    '#86efac',
  engineer_file_done:  '#86efac',
  engineer_done:       '#86efac',
  engineer_syntax_error:'#f87171',
  engineer_error:      '#f87171',
  qa_test_pass:        '#4ade80',
  qa_test_fail:        '#f87171',
  qa_done:             '#4ade80',
  qa_error:            '#f87171',
  packager:            '#94a3b8',
  packager_done:       '#94a3b8',
  packager_fail:       '#f87171',
  file_ready:          '#94a3b8',
  narrate:             '#a78bfa',
  complete:            '#4ade80',
  agent_warn:          '#fbbf24',
  safety_cutoff:       '#f87171',
};

// ─── Main content extraction ──────────────────────────────────────────────────

/**
 * Extracts the main readable content from the current page.
 * Tries multiple semantic selectors in order of specificity.
 * Returns first match with substantive content (>500 chars), max 50000 chars.
 *
 * @returns {string} Extracted text content
 */
function extractMainContent() {
  const SELECTORS = [
    'main',
    'article',
    '[role="main"]',
    '.content',
    '.docs-content',
    '.markdown-body',
    '.documentation',
    '.doc-content',
    '#content',
    '#main-content',
    'body',
  ];

  for (const selector of SELECTORS) {
    const el = document.querySelector(selector);
    if (el) {
      const text = el.innerText ? el.innerText.trim() : '';
      if (text.length > 500) {
        return text.slice(0, 50000);
      }
    }
  }

  // Last resort: entire body
  return document.body.innerText.trim().slice(0, 50000);
}

/**
 * Extracts all doc-relevant links from the page.
 * Deduplicates by href, filters to same-origin and meaningful text.
 * Adds inNav flag if link is inside navigation elements.
 * Caps at 100 links.
 *
 * @returns {Array<{text: string, href: string, inNav: boolean}>}
 */
function extractDocLinks() {
  const NAV_SELECTORS = [
    'nav',
    'aside',
    '[role="navigation"]',
    '.sidebar',
    '.nav',
    '.navigation',
    '.toc',
    '#sidebar',
    '#nav',
  ];

  const navEls = Array.from(document.querySelectorAll(NAV_SELECTORS.join(', ')));

  const isInNav = (el) => navEls.some((nav) => nav.contains(el));

  const seen = new Set();
  const links = [];
  const origin = window.location.origin;

  const anchors = document.querySelectorAll('a[href]');

  for (const anchor of anchors) {
    try {
      const href = new URL(anchor.href, window.location.href).href;
      const text = (anchor.innerText || anchor.textContent || '').trim();

      // Filter: same origin only
      if (!href.startsWith(origin)) continue;

      // Filter: no hash-only links
      const withoutHash = href.split('#')[0];
      if (seen.has(withoutHash)) continue;

      // Filter: meaningful link text (3–80 chars)
      if (text.length < 3 || text.length > 80) continue;

      // Filter: no javascript: or mailto: links
      if (anchor.href.startsWith('javascript:') || anchor.href.startsWith('mailto:')) continue;

      seen.add(withoutHash);
      links.push({
        text,
        href: withoutHash,
        inNav: isInNav(anchor),
      });

      if (links.length >= 100) break;
    } catch (_) {
      // Invalid URL — skip
    }
  }

  return links;
}

// ─── Overlay Panel ────────────────────────────────────────────────────────────

/**
 * Creates and injects the floating overlay panel on the right side of the page.
 * @param {string} jobId
 */
function injectOverlayPanel(jobId) {
  // Remove any existing overlay
  removeOverlayPanel();

  const panel = document.createElement('div');
  panel.id = 'dtc-overlay-panel';
  panel.setAttribute('data-job-id', jobId);
  panel.innerHTML = `
    <div id="dtc-overlay-header">
      <span id="dtc-overlay-title">⚡ docs-to-code</span>
      <div id="dtc-overlay-controls">
        <button id="dtc-overlay-minimise" title="Minimise">─</button>
        <button id="dtc-overlay-close" title="Close">✕</button>
      </div>
    </div>
    <div id="dtc-overlay-body">
      <div id="dtc-overlay-log"></div>
    </div>
  `;

  // Inject styles
  const style = document.createElement('style');
  style.id = 'dtc-overlay-styles';
  style.textContent = `
    #dtc-overlay-panel {
      position: fixed;
      top: 20px;
      right: 16px;
      width: 280px;
      max-height: 420px;
      background: #0d1117;
      border: 1px solid #30363d;
      border-radius: 8px;
      font-family: 'SF Mono', 'Fira Code', 'Cascadia Code', monospace;
      font-size: 11px;
      color: #e6edf3;
      z-index: 2147483647;
      box-shadow: 0 8px 32px rgba(0,0,0,0.6);
      display: flex;
      flex-direction: column;
      overflow: hidden;
      transition: max-height 0.2s ease;
    }
    #dtc-overlay-panel.minimised #dtc-overlay-body {
      display: none;
    }
    #dtc-overlay-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 8px 10px;
      background: #161b22;
      border-bottom: 1px solid #30363d;
      cursor: default;
      user-select: none;
    }
    #dtc-overlay-title {
      font-size: 11px;
      font-weight: 600;
      color: #a78bfa;
      letter-spacing: 0.5px;
    }
    #dtc-overlay-controls {
      display: flex;
      gap: 6px;
    }
    #dtc-overlay-controls button {
      background: none;
      border: none;
      color: #8b949e;
      cursor: pointer;
      font-size: 11px;
      padding: 0 3px;
      line-height: 1;
    }
    #dtc-overlay-controls button:hover {
      color: #e6edf3;
    }
    #dtc-overlay-body {
      flex: 1;
      overflow: hidden;
    }
    #dtc-overlay-log {
      height: 360px;
      overflow-y: auto;
      padding: 8px;
      display: flex;
      flex-direction: column;
      gap: 2px;
    }
    #dtc-overlay-log::-webkit-scrollbar {
      width: 4px;
    }
    #dtc-overlay-log::-webkit-scrollbar-track {
      background: #0d1117;
    }
    #dtc-overlay-log::-webkit-scrollbar-thumb {
      background: #30363d;
      border-radius: 2px;
    }
    .dtc-overlay-line {
      line-height: 1.5;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      padding: 1px 0;
    }
    @keyframes dtc-amber-flash {
      0%, 100% { border-color: #30363d; }
      50% { border-color: #fbbf24; box-shadow: 0 0 12px rgba(251,191,36,0.4); }
    }
    .dtc-reroute-flash {
      animation: dtc-amber-flash 0.5s ease 4;
    }
  `;

  document.head.appendChild(style);
  document.body.appendChild(panel);

  overlayPanel = panel;
  overlayLog = panel.querySelector('#dtc-overlay-log');

  // Event listeners
  panel.querySelector('#dtc-overlay-close').addEventListener('click', removeOverlayPanel);
  panel.querySelector('#dtc-overlay-minimise').addEventListener('click', () => {
    overlayMinimised = !overlayMinimised;
    panel.classList.toggle('minimised', overlayMinimised);
    panel.querySelector('#dtc-overlay-minimise').textContent = overlayMinimised ? '▢' : '─';
  });

  appendOverlayLine('⚡ SDK generation started…', '#a78bfa');
}

/**
 * Appends a single coloured line to the overlay log.
 * @param {string} text
 * @param {string} colour
 */
function appendOverlayLine(text, colour) {
  if (!overlayLog) return;
  const line = document.createElement('div');
  line.className = 'dtc-overlay-line';
  line.style.color = colour || '#e6edf3';
  line.textContent = text;
  overlayLog.appendChild(line);
  overlayLog.scrollTop = overlayLog.scrollHeight;
}

/**
 * Updates the overlay panel with a new SSE event.
 * @param {Object} event  Parsed SSE event object
 */
function updateOverlayPanel(event) {
  if (!overlayPanel) return;

  const type = event.type || event.event || '';
  const colour = AGENT_COLOURS[type] || '#e6edf3';

  // Skip the 'done' sentinel
  if (type === 'done') return;

  let text = '';

  switch (type) {
    case 'supervisor':
      text = `🧠 Supervisor → ${event.routing_to || '?'}`;
      break;
    case 'reroute':
      text = `↩ Reroute: ${event.from} → ${event.to}`;
      overlayPanel.classList.add('dtc-reroute-flash');
      setTimeout(() => overlayPanel.classList.remove('dtc-reroute-flash'), 2000);
      break;
    case 'researcher_analysing':
      text = `🔍 Analysing: ${event.goal || ''}`;
      break;
    case 'researcher_crawl_plan': {
      const selCount = event.selected ? event.selected.length : (event.selected_count || 0);
      text = `📋 Crawl plan: ${selCount} pages selected`;
      break;
    }
    case 'researcher_scraping':
      text = `🌐 Scraping: ${event.url || ''}`;
      break;
    case 'researcher_serper':
      text = `🔎 Web search: ${event.query || ''}`;
      break;
    case 'researcher_done':
      text = `✓ Research done — ${event.page_count || '?'} pages`;
      break;
    case 'architect_validating':
      text = `🔬 Validating schema…`;
      break;
    case 'architect_fix':
      text = `🔧 Fix: ${event.fix || ''}`;
      break;
    case 'architect_done':
      text = `✓ Schema validated — ${event.fixes_count || 0} fixes`;
      break;
    case 'architect_error':
      text = `✕ Architect error: ${event.error || ''}`;
      break;
    case 'engineer_writing':
      text = `✍ Writing ${event.filename || ''}…`;
      break;
    case 'engineer_file_done':
      text = `✓ ${event.filename || 'file'} (${event.line_count || '?'} lines)`;
      break;
    case 'engineer_done':
      text = `📦 SDK: ${event.file_count || '?'} files`;
      break;
    case 'engineer_syntax_error':
      text = `✕ Syntax: ${event.filename || ''} — ${event.error || ''}`;
      break;
    case 'engineer_error':
      text = `✕ Engineer error: ${event.error || ''}`;
      break;
    case 'qa_test_pass':
      text = `✓ ${event.endpoint || ''} → ${event.status_code || 200}`;
      break;
    case 'qa_test_fail':
      text = `✗ ${event.endpoint || ''} → ${event.actual || event.status_code || 'fail'}`;
      break;
    case 'qa_done':
      text = `QA: ${event.passed || 0}/${event.total || 0} passed`;
      break;
    case 'qa_error':
      text = `✕ QA error: ${event.error || ''}`;
      break;
    case 'file_ready':
      text = `📁 ${event.filename || 'file'} → VS Code`;
      break;
    case 'packager_done':
      text = `📦 ${event.file_count || '?'} files packaged`;
      break;
    case 'packager_fail':
      text = `✕ Packager failed: ${event.reason || ''}`;
      break;
    case 'narrate':
      text = `🔊 ${(event.text || '').slice(0, 60)}…`;
      break;
    case 'complete':
      text = `🎉 SDK complete!`;
      break;
    case 'safety_cutoff':
      text = `⚠ ${event.message || 'Safety cutoff reached'}`;
      break;
    default:
      text = `${type}: ${JSON.stringify(event).slice(0, 60)}`;
  }

  appendOverlayLine(text, colour);
}

/**
 * Removes the overlay panel from the DOM.
 */
function removeOverlayPanel() {
  if (overlayPanel) {
    overlayPanel.remove();
    overlayPanel = null;
    overlayLog = null;
  }
  const style = document.getElementById('dtc-overlay-styles');
  if (style) style.remove();
}

// ─── Message listener ─────────────────────────────────────────────────────────

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  switch (message.type) {
    case 'GET_PAGE_CONTENT': {
      sendResponse({
        url: window.location.href,
        title: document.title,
        content: extractMainContent(),
        links: extractDocLinks(),
      });
      break;
    }

    case 'SHOW_OVERLAY': {
      try {
        injectOverlayPanel(message.jobId || 'unknown');
        sendResponse({ ok: true });
      } catch (err) {
        // CSP or other injection error — silently fail
        sendResponse({ ok: false, error: err.message });
      }
      break;
    }

    case 'UPDATE_OVERLAY': {
      try {
        updateOverlayPanel(message.event || {});
        sendResponse({ ok: true });
      } catch (err) {
        sendResponse({ ok: false, error: err.message });
      }
      break;
    }

    case 'HIDE_OVERLAY': {
      removeOverlayPanel();
      sendResponse({ ok: true });
      break;
    }

    default:
      // Unknown message — ignore
      break;
  }

  // Return true to indicate async response (required for Chrome MV3)
  return true;
});
