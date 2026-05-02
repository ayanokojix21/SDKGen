#!/usr/bin/env node
/**
 * mock_sse.js — Docs to Code Dev Tool
 * Dev 4: Local mock SSE server for testing the Chrome popup and VS Code panel
 *        without a running backend.
 *
 * Usage:
 *   node dev/mock_sse.js
 *
 * Endpoints:
 *   POST http://localhost:8000/generate/start  → returns { job_id: "mock-job-001" }
 *   GET  http://localhost:8000/generate/stream → streams mock SSE events
 *   GET  http://localhost:8000/health          → { status: "ok", model: "mock" }
 *   GET  http://localhost:8000/download/:id    → 200 OK (no file)
 *
 * The SSE stream simulates the full OpenWeatherMap demo:
 *   Supervisor → Researcher → Architect → Engineer → QA fail (401) →
 *   Reroute → Engineer fix → QA pass (11/11) → Packager → files → narrate → complete
 */

'use strict';

const http = require('http');
const { URL } = require('url');

const PORT = 8000;
const MOCK_JOB_ID = 'mock-job-001';

// ─── Mock event sequence (OpenWeatherMap demo scenario) ───────────────────────
const EVENTS = [
  // Supervisor kick-off
  { delay: 200,  data: { type: 'supervisor', routing_to: 'researcher', reasoning: 'Starting research phase for OpenWeatherMap API.' } },

  // Researcher Phase 1 — LLM crawl plan
  { delay: 600,  data: { type: 'researcher_analysing', link_count: 34 } },
  { delay: 1200, data: { type: 'researcher_crawl_plan', selected_count: 4, skipped_count: 30,
    selected: ['/api/one-call-3', '/api/current', '/appid', '/api/geocoding'],
    skipped: ['pricing', 'blog', 'changelog', 'migration'] } },

  // Researcher Phase 2 — scraping
  { delay: 1800, data: { type: 'researcher_scraping', url: 'https://openweathermap.org/appid' } },
  { delay: 2400, data: { type: 'researcher_scraped',  url: 'https://openweathermap.org/appid', char_count: 8240 } },
  { delay: 2800, data: { type: 'researcher_scraping', url: 'https://openweathermap.org/api/one-call-3' } },
  { delay: 3400, data: { type: 'researcher_scraped',  url: 'https://openweathermap.org/api/one-call-3', char_count: 12500 } },
  { delay: 3800, data: { type: 'researcher_scraping', url: 'https://openweathermap.org/api/current' } },
  { delay: 4400, data: { type: 'researcher_scraped',  url: 'https://openweathermap.org/api/current', char_count: 9100 } },
  { delay: 4800, data: { type: 'researcher_scraping', url: 'https://openweathermap.org/api/geocoding' } },
  { delay: 5400, data: { type: 'researcher_scraped',  url: 'https://openweathermap.org/api/geocoding', char_count: 5600 } },

  // Researcher Phase 3 — knowledge base
  { delay: 6200, data: { type: 'researcher_done', endpoint_count: 11, page_count: 4 } },

  // Back to Supervisor
  { delay: 6600, data: { type: 'supervisor', routing_to: 'architect', reasoning: 'Research complete. Proceeding to schema validation.' } },

  // Architect
  { delay: 7000, data: { type: 'architect_validating' } },
  { delay: 7600, data: { type: 'architect_fix', fix: 'Removed request_body from GET /weather endpoint' } },
  { delay: 7900, data: { type: 'architect_fix', fix: 'Added missing path param {city_id} to /city endpoint' } },
  { delay: 8400, data: { type: 'architect_done', endpoint_count: 11, fixes_count: 2 } },

  // Back to Supervisor
  { delay: 8700, data: { type: 'supervisor', routing_to: 'engineer', reasoning: 'Schema ready. Generating Python SDK.' } },

  // Engineer
  { delay: 9000, data: { type: 'engineer_writing', filename: 'models.py' } },
  { delay: 9800, data: { type: 'engineer_file_done', filename: 'models.py', line_count: 84 } },
  { delay: 9900, data: { type: 'engineer_writing', filename: 'client.py' } },
  { delay: 11000, data: { type: 'engineer_file_done', filename: 'client.py', line_count: 210 } },
  { delay: 11100, data: { type: 'engineer_writing', filename: 'tests/test_client.py' } },
  { delay: 12000, data: { type: 'engineer_file_done', filename: 'tests/test_client.py', line_count: 156 } },
  { delay: 12100, data: { type: 'engineer_writing', filename: 'README.md' } },
  { delay: 12600, data: { type: 'engineer_file_done', filename: 'README.md', line_count: 48 } },

  // Back to Supervisor
  { delay: 12900, data: { type: 'supervisor', routing_to: 'qa_tester', reasoning: 'SDK generated. Running QA tests.' } },

  // QA — first run (401 failure on missing appid)
  { delay: 13400, data: { type: 'qa_test_pass', endpoint: 'list_cities',   url: 'http://api.openweathermap.org/geo/1.0/direct', status_code: 200, latency_ms: 312 } },
  { delay: 14000, data: { type: 'qa_test_pass', endpoint: 'get_weather',   url: 'http://api.openweathermap.org/data/2.5/weather', status_code: 200, latency_ms: 287 } },
  { delay: 14600, data: { type: 'qa_test_fail', endpoint: 'get_forecast',  url: 'http://api.openweathermap.org/data/2.5/forecast', expected: 200, actual: 401, error: 'Unauthorized — missing ?appid= param' } },
  { delay: 14800, data: { type: 'qa_done', passed: 2, failed: 1, total: 3, failure_summary: 'Missing appid query parameter on /forecast' } },

  // *** THE BIG MOMENT — reroute ***
  { delay: 15300, data: { type: 'supervisor', routing_to: 'engineer', reasoning: 'QA failure on /forecast: 401 Unauthorized. Missing API key injection. This is a code bug, not a docs problem. Re-routing to Engineer.' } },
  { delay: 15600, data: { type: 'reroute', from: 'qa_tester', to: 'engineer', reason: 'Missing appid param in forecast endpoint call' } },

  // Engineer fix
  { delay: 16000, data: { type: 'engineer_writing', filename: 'client.py' } },
  { delay: 17200, data: { type: 'engineer_file_done', filename: 'client.py', line_count: 218 } },

  // QA — second run (all pass)
  { delay: 17600, data: { type: 'supervisor', routing_to: 'qa_tester', reasoning: 'Engineer applied fix. Re-running QA.' } },
  { delay: 18000, data: { type: 'qa_test_pass', endpoint: 'list_cities',    url: 'http://api.openweathermap.org/geo/1.0/direct',          status_code: 200, latency_ms: 298 } },
  { delay: 18400, data: { type: 'qa_test_pass', endpoint: 'get_weather',    url: 'http://api.openweathermap.org/data/2.5/weather',         status_code: 200, latency_ms: 271 } },
  { delay: 18800, data: { type: 'qa_test_pass', endpoint: 'get_forecast',   url: 'http://api.openweathermap.org/data/2.5/forecast',        status_code: 200, latency_ms: 304 } },
  { delay: 19200, data: { type: 'qa_test_pass', endpoint: 'get_onecall',    url: 'http://api.openweathermap.org/data/3.0/onecall',         status_code: 200, latency_ms: 315 } },
  { delay: 19600, data: { type: 'qa_test_pass', endpoint: 'get_air',        url: 'http://api.openweathermap.org/data/2.5/air_pollution',   status_code: 200, latency_ms: 289 } },
  { delay: 20000, data: { type: 'qa_test_pass', endpoint: 'geocode_direct', url: 'http://api.openweathermap.org/geo/1.0/direct',           status_code: 200, latency_ms: 276 } },
  { delay: 20400, data: { type: 'qa_test_pass', endpoint: 'geocode_reverse',url: 'http://api.openweathermap.org/geo/1.0/reverse',          status_code: 200, latency_ms: 301 } },
  { delay: 20800, data: { type: 'qa_test_pass', endpoint: 'get_history',    url: 'http://api.openweathermap.org/data/2.5/onecall/timemachine', status_code: 200, latency_ms: 344 } },
  { delay: 21200, data: { type: 'qa_test_pass', endpoint: 'get_statistics', url: 'http://api.openweathermap.org/data/2.5/aggregation',     status_code: 200, latency_ms: 318 } },
  { delay: 21600, data: { type: 'qa_test_pass', endpoint: 'get_overview',   url: 'http://api.openweathermap.org/data/4.0/overview',        status_code: 200, latency_ms: 292 } },
  { delay: 22000, data: { type: 'qa_test_pass', endpoint: 'get_bulk',       url: 'http://bulk.openweathermap.org/sample/current.json.gz',  status_code: 200, latency_ms: 267 } },
  { delay: 22200, data: { type: 'qa_done', passed: 11, failed: 0, total: 11 } },

  // Packager
  { delay: 22600, data: { type: 'supervisor', routing_to: 'packager', reasoning: 'All 11 QA tests passed. Packaging SDK.' } },
  { delay: 23000, data: { type: 'file_ready', filename: 'client.py',              content: '# OpenWeatherMap Python SDK\n# Auto-generated by Docs to Code\n' } },
  { delay: 23300, data: { type: 'file_ready', filename: 'models.py',              content: '# Models\n' } },
  { delay: 23600, data: { type: 'file_ready', filename: 'tests/test_client.py',   content: '# Tests\n' } },
  { delay: 23900, data: { type: 'file_ready', filename: 'README.md',              content: '# OpenWeatherMap SDK\n' } },

  // Narration
  { delay: 24400, data: { type: 'narrate', text: 'We built an 11-method Python SDK for the OpenWeatherMap API. The QA agent caught a missing API key parameter, the Supervisor re-routed directly to the Engineer, and all 11 endpoints verified green on the second pass.' } },

  // Complete
  { delay: 25000, data: { type: 'complete', zip_url: '/download/mock-job-001', endpoint_count: 11, file_count: 4, qa_rerouts: 1 } },
];

// ─── HTTP Server ──────────────────────────────────────────────────────────────
const server = http.createServer((req, res) => {
  const url = new URL(req.url, `http://localhost:${PORT}`);

  // CORS — allow Chrome extension origin
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

  if (req.method === 'OPTIONS') {
    res.writeHead(204);
    res.end();
    return;
  }

  // ── GET /health ────────────────────────────────────────────────────────────
  if (req.method === 'GET' && url.pathname === '/health') {
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ status: 'ok', model: 'mock', server: 'mock_sse.js' }));
    return;
  }

  // ── POST /generate/start ───────────────────────────────────────────────────
  if (req.method === 'POST' && url.pathname === '/generate/start') {
    let body = '';
    req.on('data', (chunk) => { body += chunk; });
    req.on('end', () => {
      console.log(`[Mock] /generate/start received: ${body.slice(0, 120)}`);
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ job_id: MOCK_JOB_ID, stream_url: `/generate/stream?job_id=${MOCK_JOB_ID}` }));
    });
    return;
  }

  // ── GET /generate/stream ───────────────────────────────────────────────────
  if (req.method === 'GET' && url.pathname === '/generate/stream') {
    const jobId = url.searchParams.get('job_id');
    console.log(`[Mock] SSE stream opened for job_id=${jobId}`);

    res.writeHead(200, {
      'Content-Type':  'text/event-stream',
      'Cache-Control': 'no-cache',
      'Connection':    'keep-alive',
      'X-Accel-Buffering': 'no',
    });

    // Heartbeat every 15s to keep connection alive
    const heartbeat = setInterval(() => {
      res.write(': heartbeat\n\n');
    }, 15000);

    // Stream events in sequence
    let cancelled = false;
    req.on('close', () => {
      cancelled = true;
      clearInterval(heartbeat);
      console.log(`[Mock] Client disconnected for job_id=${jobId}`);
    });

    EVENTS.forEach(({ delay, data }) => {
      setTimeout(() => {
        if (cancelled) return;
        const payload = `data: ${JSON.stringify(data)}\n\n`;
        res.write(payload);
        console.log(`[Mock] → ${data.type}`);

        // End stream after complete event
        if (data.type === 'complete') {
          clearInterval(heartbeat);
          setTimeout(() => { try { res.end(); } catch (_) {} }, 500);
        }
      }, delay);
    });

    return;
  }

  // ── GET /download/:id ──────────────────────────────────────────────────────
  if (req.method === 'GET' && url.pathname.startsWith('/download/')) {
    res.writeHead(200, {
      'Content-Type': 'application/zip',
      'Content-Disposition': 'attachment; filename="mock_sdk.zip"',
    });
    res.end('MOCK_ZIP_CONTENT');
    return;
  }

  // ── 404 ────────────────────────────────────────────────────────────────────
  res.writeHead(404, { 'Content-Type': 'application/json' });
  res.end(JSON.stringify({ error: 'Not found', path: url.pathname }));
});

server.listen(PORT, () => {
  console.log('');
  console.log('  ⚡ Docs to Code — Mock SSE Server');
  console.log(`  Listening on http://localhost:${PORT}`);
  console.log('');
  console.log('  Endpoints:');
  console.log(`    GET  /health`);
  console.log(`    POST /generate/start  → { job_id: "${MOCK_JOB_ID}" }`);
  console.log(`    GET  /generate/stream → full OWM demo sequence (~25s)`);
  console.log(`    GET  /download/:id`);
  console.log('');
  console.log('  Load chrome-extension/ in Chrome, open OWM docs, hit Generate.');
  console.log('  Ctrl+C to stop.');
  console.log('');
});
