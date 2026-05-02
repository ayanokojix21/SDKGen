# ⚡ DOCS-TO-CODE — Hackathon Team Task Division
### LangGraph Multi-Agent · LLM-Guided Crawling · Chrome + VS Code Extensions · Live QA
### 4 Developers · 24-Hour Hackathon · Complete Implementation Blueprint

---

## 1. Project Overview & Architecture

Docs-to-Code is a multi-agent AI system that turns any API documentation URL into a fully typed, live-verified SDK — delivered directly into VS Code. It uses a LangGraph Supervisor graph with 6 agents, LLM-guided selective crawling, real HTTP endpoint verification, and a dual Chrome+VS Code extension frontend.

### System Architecture — Agent Flow

```
Chrome Extension  →  FastAPI Backend  →  LangGraph Graph
                                               ↓
         Supervisor (LLM Routing) → Researcher → Architect → Engineer → QA Tester → Packager
                      ↑_____________________|___________________________|
                             (Feedback loops — QA failures route back)
```

### Three Core Innovations

1. **LLM-Guided Selective Crawling** — Researcher asks Gemini which of 30–80 doc pages are worth reading. Skips pricing, blog, FAQs. Only scrapes 3–6 relevant pages.
2. **Non-Linear Agentic Routing** — QA Tester makes real HTTP calls. On failure, Supervisor decides whether to re-route to Researcher (docs gap) or Engineer (code bug). No hardcoded order.
3. **Direct VS Code Workspace Delivery** — No ZIP download. Files arrive via SSE events and are written into the active workspace file tree in real time.

### Team Summary

| Member | Role | Primary Stack | Core Deliverables |
|--------|------|---------------|-------------------|
| **Dev 1** | Backend Lead | Python / FastAPI / LangGraph | FastAPI server, LangGraph graph, Supervisor agent, SSE streaming, job checkpoint system |
| **Dev 2** | Researcher + QA | Python / Playwright / httpx | Researcher agent (3 phases), LLM crawl planner, QA Tester agent, live HTTP tool |
| **Dev 3** | LLM / Prompts | Python / Gemini / Black / tsc | All 8 prompts, Architect agent, Engineer agent, Packager node, narration LLM call |
| **Dev 4** | Frontend / Extensions | JS / TypeScript / Chrome / VS Code API | Chrome extension, VS Code extension, bridge protocol, TTS, file injector, overlay UI |

---

## 2. 🔧 DEV 1 — Backend Lead

### Primary Responsibility

Dev 1 owns the entire Python backend infrastructure — the FastAPI server, the LangGraph state machine and graph wiring, the Supervisor agent (the brain of the system), the SSE streaming pipeline, and the job checkpoint/resume system. Everything else depends on Dev 1's foundation being solid by Hour 6.

### Stack & Tools

| | |
|---|---|
| **Language** | Python 3.11+ |
| **Frameworks** | FastAPI 0.111, LangGraph 0.1.14, LangChain 0.2.5 |
| **LLM** | Gemini 1.5 Pro (via langchain-google-genai) for Supervisor routing |
| **Key Libs** | uvicorn, pydantic, asyncio, websockets, python-dotenv |

### Deliverables — File by File

| File / Module | Responsibility |
|---------------|----------------|
| `backend/main.py` | FastAPI app: CORS, /generate/start, /generate/stream (SSE), /download/{job_id} |
| `backend/job_manager.py` | Job lifecycle: create, load, save checkpoints, SSE queue management, per-job folder I/O |
| `backend/graph/state.py` | SDKJobState TypedDict — single source of truth for entire system |
| `backend/graph/graph.py` | LangGraph StateGraph: 6 nodes wired, edges defined, graph.compile() |
| `backend/graph/router.py` | route_next(): safety overrides (iteration ≥ 15, qa_iteration ≥ 4) + reads state.next_agent |
| `backend/graph/runner.py` | Async graph runner: pipes state.sse_events to the SSE stream endpoint |
| `backend/agents/supervisor.py` | Supervisor LLM node: reads state summary, calls Gemini, parses JSON, emits SSE, returns routing decision |

### Detailed Task Breakdown

#### Task 1.1 — Project Scaffolding (Hour 0–1)

- Run setup.sh: create Python venv, install requirements.txt, install Playwright chromium, test GOOGLE_API_KEY
- Initialise monorepo structure: `backend/`, `chrome-extension/`, `vscode-extension/`, `examples/`
- Confirm `.env` is loaded and Gemini API responds to a test ping
- Stub all FastAPI routes so the server starts clean: `POST /generate/start`, `GET /generate/stream`

#### Task 1.2 — SDKJobState Design (Hour 1–2)

This is the single most important file in the project. Every agent reads from and writes to this TypedDict. Get it right first.

- Define `SDKJobState` in `backend/graph/state.py` with all fields:
  - `messages` (Annotated with operator.add for append-only LangChain messages)
  - `job_id`, `target_url`, `language`, `page_content`, `page_links`
  - `crawl_plan`, `crawled_pages`, `knowledge_base` (Researcher outputs)
  - `api_schema`, `schema_fixes` (Architect outputs)
  - `sdk_files`, `syntax_errors` (Engineer outputs)
  - `test_results`, `qa_iteration` (QA outputs)
  - `final_files`, `narration_text` (Packager outputs)
  - `next_agent`, `iteration_count`, `status`, `failure_reason` (Control fields)
  - `sse_events` (Annotated with operator.add — consumed by SSE stream)
- Write utility: `build_state_summary(state)` → compact JSON for Supervisor prompt injection
- Write `emit_sse(state, event_type, **kwargs)` → appends to sse_events in the correct schema

#### Task 1.3 — LangGraph Graph Build (Hour 2–4)

- Create `backend/graph/graph.py` — build and compile the StateGraph:
  - `graph.add_node()` for all 6 agents: supervisor, researcher, architect, engineer, qa_tester, packager
  - `graph.set_entry_point('supervisor')`
  - `graph.add_edge()` for all non-supervisor agents to loop back to supervisor
  - `graph.add_edge('packager', END)`
  - `graph.add_conditional_edges('supervisor', route_next, routing_map)`
  - `app = graph.compile()`
- Create `backend/graph/router.py` — `route_next()` function:
  - Check `state['status'] == 'failed'` → return `'end'`
  - Check `state['iteration_count'] >= 15` → return `'end'`
  - Check `state['qa_iteration'] >= 4` → return `'end'`
  - Otherwise return `state['next_agent']`
- Test with stub nodes: supervisor stub sets `next_agent='researcher'`, verify graph routes correctly

#### Task 1.4 — Supervisor Agent (Hour 2–5)

The Supervisor is the most critical agent — it reads all state and decides everything. It must produce strict JSON output every time.

- Create `backend/agents/supervisor.py`:
  - Call Gemini 1.5 Pro with `SUPERVISOR_PROMPT` + current state summary
  - Parse JSON response: `{ next_agent, instruction, reasoning }`
  - Handle JSON parse failure: retry once with stricter prompt → fail gracefully
  - Emit SSE event: `{ type: 'supervisor', routing_to, reasoning, instruction }`
  - Emit SSE event: `{ type: 'reroute', from, to, reason }` when routing back after QA failure
  - Increment `iteration_count`
  - Return updated state with `next_agent` and appended `AIMessage`
- Implement exponential backoff for Gemini rate limits: 2s, 4s, 8s, then fail gracefully
- Hardcode the routing message format so Dev 3 can write the SUPERVISOR_PROMPT against it

#### Task 1.5 — FastAPI & SSE Streaming (Hour 3–5)

- `POST /generate/start` — accepts `{ target_url, language, page_content, page_links }` from Chrome extension
  - Creates `job_id` (UUID), initialises `SDKJobState`, saves checkpoint
  - Launches graph runner as background asyncio task
  - Returns `{ job_id }` immediately
- `GET /generate/stream?job_id=X` — Server-Sent Events endpoint
  - Polls `state.sse_events` queue (async generator)
  - Streams each event as `text/event-stream` formatted JSON
  - Keeps connection alive with heartbeat pings
- `GET /download/{job_id}` — returns ZIP of `final_files`
- `WebSocket /ws` — bridge server for Chrome ↔ VS Code (Dev 4 will connect to this)

#### Task 1.6 — Job Manager & Checkpointing (Hour 4–6)

- Create `backend/job_manager.py`:
  - `create_job(url, language, page_content, page_links)` → job_id + initial state
  - `save_checkpoint(job_id, state)` → writes state JSON to `backend/jobs/{job_id}/state.json`
  - `load_checkpoint(job_id)` → reads state back for resume
  - `get_sse_queue(job_id)` → async queue for SSE consumption
  - `build_zip(files_dict)` → in-memory ZIP bytes for download endpoint
- Implement resume flow: if job_id exists in `/jobs/`, reload state and re-run graph from last known state

#### Task 1.7 — Integration & Safety Testing (Hour 8–13)

- Wire Researcher, Architect, Engineer, QA Tester nodes into the live graph (coordinating with Dev 2 & Dev 3)
- Force-test Supervisor rerouting: inject a manually broken `sdk_files`, verify Supervisor routes to Engineer not Researcher
- Test `iteration_count` safety: mock a loop that hits 15 iterations, verify clean END with `safety_cutoff` SSE event
- Test `qa_iteration` safety: mock 4 QA failures, verify graceful failure
- Test checkpoint resume: kill server mid-run, restart, verify job continues from last state

### Hour-by-Hour Schedule

| Time | Task |
|------|------|
| 00:00–01:30 | SETUP: Monorepo init, .env confirmed, Gemini API key tested, FastAPI server starts, stub routes respond |
| 01:30–02:00 | Design SDKJobState TypedDict completely — all fields, all types, emit_sse helper, build_state_summary helper |
| 02:00–04:00 | Build LangGraph graph (6 stub nodes, all edges, compile). Build router.py with all safety checks |
| 04:00–06:00 | Supervisor agent: Gemini call, JSON parse, SSE emit, state return. FastAPI: /start, /stream, /download routes |
| 06:00–08:00 | CHECKPOINT 1: Wire Researcher (Dev 2) into graph. Verify supervisor→researcher→supervisor routing via SSE |
| 08:00–10:00 | Wire Architect + Engineer (Dev 3). Test full path to sdk_files in state |
| 10:00–13:00 | Wire QA Tester (Dev 2). Test Supervisor re-routing after QA failure. Test all safety cutoffs |
| 13:00–14:00 | CHECKPOINT 2: Full end-to-end run. Verify reroute SSE event. Verify real latencies in QA events |
| 14:00–18:00 | Checkpoint resume. Fix integration bugs. Stress test with multiple APIs |
| 18:00–21:00 | Stress test all 4 demo APIs × 2 languages. Fix every failure. Document all edge case behaviours |
| 21:00–23:00 | Demo prep: pre-generate /examples, write README.md, record backup demo video |
| 23:00–24:00 | Submission buffer — only bug fixes, no new features |

---

## 3. 🕵️ DEV 2 — Researcher + QA Engineer

### Primary Responsibility

Dev 2 owns the two most demo-critical agents: the Researcher (which determines the quality of all downstream output via LLM-guided selective crawling) and the QA Tester (the centrepiece of the demo — making real HTTP calls to live APIs). Dev 2 also owns Playwright scraping and the execute_http safety layer.

### Stack & Tools

| | |
|---|---|
| **Language** | Python 3.11+ |
| **Key Libs** | Playwright (async), BeautifulSoup4, httpx (async), LangChain tools |
| **LLM** | Gemini 1.5 Flash for crawl planning (fast, cheap), Gemini 1.5 Pro for knowledge base synthesis |
| **Test APIs** | JSONPlaceholder, OpenWeatherMap, REST Countries, GitHub REST |

### Deliverables — File by File

| File / Module | Responsibility |
|---------------|----------------|
| `backend/tools/scrape_web.py` | Playwright async scraper: uses Chrome-injected content for landing page, Playwright for sub-pages, cleans HTML noise |
| `backend/tools/select_pages.py` | LLM crawl planner tool: sends links + goal to Gemini Flash, returns `{ crawl_plan, skipped, notes }` |
| `backend/tools/execute_http.py` | Live HTTP request tool: safety rules enforced (private IP block, GET/POST only, timeout, 15 req cap) |
| `backend/agents/researcher.py` | Researcher agent: detects first-crawl vs re-crawl, runs Phase 1+2+3, builds/merges knowledge base |
| `backend/agents/qa_tester.py` | QA Tester agent: reads api_schema + sdk_files, constructs test cases, calls execute_http, reports to Supervisor |
| `backend/prompts/select_pages.txt` | Prompt for LLM crawl planner — selection criteria, skip criteria, auth-first prioritisation |
| `backend/prompts/researcher.txt` | Prompt for Researcher agent — knowledge base schema, merge rules, source tracking |
| `backend/prompts/qa_tester.txt` | Prompt for QA Tester — test case construction, safe POST values, failure report format |

### Detailed Task Breakdown

#### Task 2.1 — Playwright Scraper Tool (Hour 1–3)

This tool is the foundation of all research. It must handle real-world docs sites reliably.

- Create `backend/tools/scrape_web.py` as a LangChain `@tool`:
  - Input: `url (str)`
  - Output: `{ url, content (str, max 15000 chars), source ('chrome_injection' | 'playwright'), char_count }`
- **Landing page fast path**: if `url == state.target_url` AND `page_content` length > 300 chars → return Chrome-injected content directly (no Playwright needed)
- **Playwright path** for sub-pages:
  - Launch headless Chromium via `async_playwright()`
  - `goto(url, timeout=15000)`, `wait_for_load_state('networkidle')`
  - Remove noise elements via `page.evaluate()`: nav, header, footer, script, style, .sidebar, `[role='banner']`, `[role='navigation']`
  - Return `document.body.innerText[:15000]`
- Error handling: 404 → `{ error: 'not_found' }`; redirect to /login → `{ error: 'login_required' }`; timeout → `{ error: 'timeout' }`
- Test on 5 real API doc sites: jsonplaceholder.typicode.com, openweathermap.org/api, restcountries.com, docs.github.com

#### Task 2.2 — LLM Crawl Planner Tool (Hour 1–3)

This is the key innovation. The LLM reads link text and decides which pages are worth crawling — no heuristics, no keyword matching.

- Create `backend/tools/select_pages.py` as a LangChain `@tool`:
  - Inputs: `links` (list of `{text, href, inNav}`), `landing_content (str)`, `goal (str)`
  - Output: `{ crawl_plan: [{url, reason, priority}], skipped: [{url, reason}], notes: str }`
- Call Gemini 1.5 Flash with `SELECT_PAGES_PROMPT` + goal + `landing_content[:3000]` + links JSON
- Parse and validate JSON response — if malformed, fall back to returning all navigation-level links (depth 1, max 5)
- Test on hardcoded JSONPlaceholder link list — verify LLM correctly identifies `/posts`, `/users` endpoints and skips `/about`, `/changelog`
- Test on OpenWeatherMap link list — verify `/appid` (auth) is selected with priority 1

#### Task 2.3 — Researcher Agent: Three-Phase Crawl (Hour 2–6)

The Researcher is the most complex agent because it handles three distinct scenarios: first crawl, targeted re-crawl after QA failure, and merging new findings into an existing knowledge base.

- Create `backend/agents/researcher.py` — `researcher_node(state)` function:
  - Detect mode: `is_recrawl = state['knowledge_base'] is not None`
- **PHASE 1 — LLM Page Selection:**
  - Call `select_pages_to_crawl(links=state['page_links'], landing_content=state['page_content'], goal)`
  - For re-crawl: inject `supervisor_instruction` as goal, pass `already_crawled` to avoid duplicates
  - Emit SSE: `researcher_analysing` (link_count), `researcher_crawl_plan` (selected list, skipped_count)
- **PHASE 2 — Targeted Scraping:**
  - Iterate `crawl_plan` sorted by priority
  - For each page: emit `researcher_scraping`, call `scrape_web(url)`, emit `researcher_scraped` (char_count)
  - Edge cases: skip pages already in `crawled_pages`; skip errors (404, login, timeout)
- **PHASE 3 — Knowledge Base Build / Merge:**
  - First crawl: call Gemini with `researcher.txt` prompt + all scraped content → build structured `knowledge_base`
  - Re-crawl: call Gemini to merge new page content into existing `knowledge_base`
  - Knowledge base schema: `api_name`, `base_url`, `auth` (type/location/key_name/example), `endpoints_raw[]`, `notes`, `pages_crawled`
  - Emit `researcher_done` (endpoint_count, page_count)
- Edge case R1: LLM selects 0 pages → fall back to all navigation-level links (max 5)
- Edge case R8: `page_links` empty → find links in `page_content` via regex as fallback

#### Task 2.4 — Execute HTTP Request Tool (Hour 3–5)

This tool powers the live demo. Safety rules are hardcoded — not overridable by any LLM prompt.

- Create `backend/tools/execute_http.py` as a LangChain `@tool`:
  - Inputs: `method`, `url`, `headers`, `params`, `body`, `expected_status`, `endpoint_name`
  - Output: `{ endpoint_name, method, url, status_code, response_body (500 char cap), passed, error, latency_ms }`
- **SAFETY RULES — enforce all, no exceptions:**
  - Allowed methods: GET and POST only (no DELETE, PUT, PATCH)
  - Block private IPs: 127.x, 192.168.x, 10.x via `is_private_ip(urlparse(url).hostname)`
  - Timeout: 10 seconds hard limit
  - Max 15 requests per job (tracked in state via qa_iteration guard in router)
  - User-Agent header: `'docs-to-code-qa/1.0'`
- Use `httpx.AsyncClient` for async HTTP
- Test on JSONPlaceholder: `GET /posts/1` → expect 200; `GET /posts/999999` → expect 404
- Test auth failure: `GET openweathermap.org/data/2.5/weather?q=London` without appid → expect 401

#### Task 2.5 — QA Tester Agent (Hour 4–6)

The QA Tester is the demo centrepiece. It must produce clear, specific failure reports so the Supervisor can make smart re-routing decisions.

- Create `backend/agents/qa_tester.py` — `qa_tester_node(state)` function:
  - Read `api_schema` from state → extract all endpoint definitions
  - Call Gemini with `QA_TESTER_PROMPT` + `api_schema` JSON + `sdk_files` content
  - LLM constructs test cases: URL construction, headers (auth injected), safe test params
  - For each test case: call `execute_http_request` tool, collect result
  - Emit SSE per test: `qa_test_pass` (`{ endpoint, url, status, latency_ms }`) or `qa_test_fail` (`{ endpoint, url, expected, actual, error }`)
- On completion emit `qa_done`: `{ passed, failed, total, failure_summary }`
- Increment `state['qa_iteration']` by 1
- Return `test_results` list to state for Supervisor analysis
- Edge case A7: auth-gated endpoints → mark as `'untestable_auth_required'`, count as skip not failure
- Edge case A8: timeout → mark as failed with `error = 'Request timed out (10s)'`

#### Task 2.6 — Demo API Testing (Hour 14–18)

- Run full pipeline on all 4 demo APIs in both Python and TypeScript:
  - **OpenWeatherMap** — should trigger 401 re-route (missing `?appid=` param)
  - **JSONPlaceholder** — should trigger 404 re-route (`/post` vs `/posts` path)
  - **REST Countries** — good for TypeScript demo (field casing in schema)
  - **GitHub REST** — verify pagination headers and Accept header handling
- Document which exact error each API triggers and which agent the Supervisor re-routes to
- Save re-route logs — needed for demo prep and backup video

### Hour-by-Hour Schedule

| Time | Task |
|------|------|
| 00:00–01:30 | SETUP: Playwright install, Gemini Flash test, confirm `scrape_web` returns clean text from jsonplaceholder.typicode.com |
| 01:30–03:00 | Build `scrape_web` tool + `select_pages` tool. Test: `select_pages` returns valid JSON for hardcoded JSONPlaceholder links |
| 03:00–06:00 | Build Researcher agent: Phase 1 (LLM selection) + Phase 2 (scraping) working end-to-end on JSONPlaceholder |
| 04:00–06:00 | (Parallel) Build `execute_http` tool with all safety rules. Test 3 real APIs: GET success, auth failure, timeout |
| 06:00–08:00 | CHECKPOINT 1: Wire Researcher into graph with Dev 1. Researcher Phase 3 (re-crawl) working |
| 08:00–10:00 | Build QA Tester agent. Wire into graph. Live HTTP tests firing for JSONPlaceholder (9 endpoints) |
| 10:00–13:00 | Test QA rerouting: force appid missing in OpenWeatherMap → verify 401 fires → Supervisor re-routes to Engineer |
| 13:00–14:00 | CHECKPOINT 2: Full Scenario B visible. Real status codes and latencies in SSE stream |
| 14:00–18:00 | Test all 4 demo APIs × 2 languages. Document natural re-route triggers for each API |
| 18:00–21:00 | Stress test: 8 full runs. Fix every QA or scraping failure found |
| 21:00–23:00 | Pre-generate `examples/openweathermap_python` and `examples/jsonplaceholder_typescript` with real output |

---

## 4. 🧠 DEV 3 — LLM Engineer & Prompt Architect

### Primary Responsibility

Dev 3 owns the LLM reasoning layer: all 8 system prompts (the quality of the whole system depends on these), the Architect agent that validates and fixes API schemas, the Engineer agent that writes the actual SDK code, the Packager node that delivers files and narrates the result, and the TypeScript SDK generation path.

### Stack & Tools

| | |
|---|---|
| **Language** | Python 3.11+ |
| **Key Libs** | LangChain, langchain-google-genai, Black (Python formatter), `ast` (syntax check), subprocess/tsc (TypeScript check) |
| **LLM** | Gemini 1.5 Pro for all major generation tasks (Architect, Engineer, Narration). Gemini 1.5 Flash for QA prompt construction |
| **Output** | `client.py` / `client.ts`, `models.py` / `models.ts`, `tests/test_client.py` / `test_client.ts`, `README.md` |

### Deliverables — File by File

| File / Module | Responsibility |
|---------------|----------------|
| `backend/agents/architect.py` | Architect agent: calls Gemini to structure `knowledge_base` into `api_schema`, calls `validate_schema` tool, emits fixes |
| `backend/agents/engineer.py` | Engineer agent: calls Gemini to generate all SDK files, calls `syntax_check` on each file, internal fix-retry before escalating |
| `backend/agents/packager.py` | Packager node: Black linting, emit `file_ready` SSE events, build ZIP fallback, call narration LLM, emit `narrate` event |
| `backend/tools/validate_schema.py` | Schema validator tool: 6 logical checks, auto-fixes GET/DELETE body, path param mismatches, returns `fixed_schema` |
| `backend/tools/syntax_check.py` | Syntax checker tool: `ast.parse` for Python, `tsc --noEmit --strict` for TypeScript, returns `{valid, error, line}` |
| `backend/prompts/supervisor.txt` | Supervisor routing prompt: 8 routing rules in order, JSON-only output constraint |
| `backend/prompts/select_pages.txt` | Crawl planner prompt: include/exclude criteria, auth-first prioritisation |
| `backend/prompts/researcher.txt` | Researcher prompt: knowledge base schema definition, merge rules |
| `backend/prompts/architect.txt` | Architect prompt: api_schema output schema, validation instructions |
| `backend/prompts/engineer_python.txt` | Python SDK generation prompt: class structure, type hints, docstrings, httpx usage |
| `backend/prompts/engineer_typescript.txt` | TypeScript SDK prompt: interfaces, strict types, async/await, fetch API |
| `backend/prompts/qa_tester.txt` | QA Tester prompt: test case construction, safe test values, failure report format |
| `backend/prompts/narrate.txt` | Narration prompt: 2–3 sentences, first person plural, specific numbers, mention autonomous fixes |

### Detailed Task Breakdown

#### Task 3.1 — All Prompts (Hour 0–3, revisited throughout)

Prompts are the most important deliverable. A bad prompt means bad SDK output. Write them first so Dev 1, Dev 2, and Dev 4 can test against real LLM behaviour immediately.

- **`prompts/supervisor.txt`** — Write routing rules 1–8 in strict order. JSON-only output. Include `state_summary` placeholder. Test: Gemini returns valid `{ next_agent, instruction, reasoning }` JSON for 3 different state scenarios
- **`prompts/select_pages.txt`** — Write include/exclude criteria. Auth page gets priority 1. Skip pricing, blog, FAQ, changelogs. Test: Gemini correctly selects `/appid` over `/pricing` for OpenWeatherMap links
- **`prompts/researcher.txt`** — Define the exact knowledge_base JSON schema. Include merge rules for re-crawl. Test: Gemini builds valid schema from JSONPlaceholder scraped content
- **`prompts/architect.txt`** — Define api_schema output format. Include validation instructions. Test: Gemini catches GET endpoint with request_body
- **`prompts/engineer_python.txt`** — Python SDK requirements: use httpx, dataclass models, type hints everywhere, clear docstrings, constructor takes `api_key + base_url`. Test: generates valid Python for JSONPlaceholder schema
- **`prompts/engineer_typescript.txt`** — TypeScript requirements: strict types, interfaces for all models, async/await, fetch API, `export const client`. Test: `tsc --noEmit` passes on generated code
- **`prompts/qa_tester.txt`** — Safe test values list. Report format. Auth handling. Test: Gemini constructs correct httpx call from OpenWeatherMap schema
- **`prompts/narrate.txt`** — 2–3 sentences, first-person plural, include: API name, language, method count, mention autonomous fixes if any. Test: output sounds natural when read by TTS

#### Task 3.2 — Validate Schema Tool (Hour 2–4)

Pure Python — no LLM needed. Six deterministic checks with auto-fix.

- Create `backend/tools/validate_schema.py` as a LangChain `@tool`:
  - Input: `schema (dict)`
  - Output: `{ valid (bool), issues (list), fixed_schema (dict), fixes_applied (list[str]) }`
- **Check 1:** GET/DELETE with `request_body` → remove `request_body`, add to `fixes_applied`
- **Check 2:** Path params in path string (e.g. `{user_id}`) not in `path_params` array → auto-add missing param
- **Check 3:** All endpoints must have `method`, `path`, `description` → mark `CRITICAL` if missing
- **Check 4:** `base_url` must be a valid URL (starts with http/https)
- **Check 5:** `auth.type` must be one of: `bearer`, `api_key`, `basic`, `none`
- **Check 6:** No duplicate endpoint names → append `_2` to duplicates
- Return `valid=False` only if CRITICAL issues exist; non-critical issues are auto-fixed and reported

#### Task 3.3 — Architect Agent (Hour 2–5)

- Create `backend/agents/architect.py` — `architect_node(state)` function:
  - Emit SSE: `architect_validating`
  - Call Gemini 1.5 Pro with `ARCHITECT_PROMPT` + `knowledge_base` JSON
  - LLM structures `knowledge_base.endpoints_raw` into clean `api_schema` with all required fields
  - Call `validate_schema(api_schema)` tool → get `fixed_schema` + `fixes_applied`
  - For each fix: emit SSE `architect_fix` (fix description)
  - Emit SSE: `architect_done` (endpoint_count, fixes_count)
  - Return state with `api_schema = fixed_schema`, `schema_fixes = fixes_applied`
- Test with JSONPlaceholder knowledge base → verify `api_schema` has all endpoints with correct methods, paths, params

#### Task 3.4 — Syntax Check Tool (Hour 2–4)

- Create `backend/tools/syntax_check.py` as a LangChain `@tool`:
  - Input: `code (str)`, `language (str: 'python'|'typescript')`, `filename (str)`
  - Output: `{ valid (bool), error (str|None), line (int|None), col (int|None) }`
- **Python check:** `ast.parse(code)` → SyntaxError returns `{ valid: False, error, line }`
- **TypeScript check:** write to tempfile, run `subprocess(['tsc', '--noEmit', '--strict', '--target', 'ES2020', tmp])`, parse stderr
- Test: pass syntactically invalid Python (missing colon) → verify error with line number returned

#### Task 3.5 — Engineer Agent (Hour 3–6)

The Engineer generates all SDK files in a single LLM call, then validates each one. Internal retry before escalating.

- Create `backend/agents/engineer.py` — `engineer_node(state)` function:
  - Read `api_schema` + `language` from state
  - Detect if this is a fix visit: check `state['messages']` for previous Engineer `AIMessage`
  - **First visit:** call Gemini with `ENGINEER_PROMPT` + `api_schema` JSON → generates 4 files
  - **Fix visit:** call Gemini with failure report + current `sdk_files` → generates patched files
- Generated files for **Python:** `client.py`, `models.py`, `tests/test_client.py`, `README.md`
- Generated files for **TypeScript:** `client.ts`, `models.ts`, `tests/test_client.ts`, `README.md`
- Syntax check loop for each file:
  - Call `syntax_check(code, language, filename)`
  - If invalid: attempt one internal fix via second LLM call with error + code
  - If still invalid after retry: emit `engineer_syntax_error` SSE, include in `syntax_errors` list, escalate to Supervisor
- Emit SSE per file: `engineer_writing` (filename), `engineer_file_done` (filename, line_count)
- Return state with `sdk_files` dict

#### Task 3.6 — Packager Node (Hour 5–7)

Packager is deterministic — no LLM routing. Fast, reliable, clearly signals completion.

- Create `backend/agents/packager.py` — `packager_node(state)` function:
  - For each `.py` file in `sdk_files`: run `black.format_str(content, mode=black.Mode())`
  - For each file: emit SSE `file_ready (filename, content)` — VS Code writes on receipt
  - Build ZIP fallback: `build_zip(final_files)` → save to `backend/jobs/{job_id}/sdk.zip`
- **Narration LLM call:**
  - Build `job_summary` JSON: `api_name`, `language`, `endpoint_count`, `file_count`, `qa_rerouts`, `qa_fixes`
  - Call Gemini with `NARRATE_PROMPT` + `job_summary` → 2–3 sentence spoken summary
  - Emit SSE: `narrate (text)` — both extensions speak this via TTS
- Emit SSE: `complete (zip_url, summary stats)`
- Return state with `final_files`, `narration_text`, `status='success'`

#### Task 3.7 — TypeScript Full Path (Hour 14–17)

- Test `engineer_typescript.txt` prompt on JSONPlaceholder and REST Countries schemas
- Verify `tsc --noEmit --strict` passes on generated TypeScript with no manual fixes
- Fix common TypeScript generation issues: implicit any types, missing return types, non-null assertions
- Verify TypeScript client has proper interface types for all response models
- Ensure README.md includes correct TypeScript install and import instructions

### Hour-by-Hour Schedule

| Time | Task |
|------|------|
| 00:00–01:30 | SETUP: Gemini responds to `supervisor.txt` prompt with valid JSON. Engineer prompt generates valid Python for hardcoded schema |
| 01:30–03:00 | Write all 8 prompts. Test each in isolation. Fix until Gemini returns correct output format for each |
| 03:00–05:00 | Build `validate_schema` tool (6 checks, auto-fix). Build `syntax_check` tool (Python ast.parse + tsc subprocess) |
| 05:00–07:00 | Build Architect agent (Gemini call + validate_schema). Build Engineer agent (generate + syntax check + internal retry) |
| 06:00–08:00 | CHECKPOINT 1: Architect + Engineer wired into graph with Dev 1. `sdk_files` populated in state after full run |
| 07:00–09:00 | Build Packager node (Black lint, `file_ready` SSE, ZIP, narration LLM call) |
| 08:00–13:00 | Full squad online. Test Engineer fix path: inject bad code, verify Supervisor routes to Engineer and fix is applied |
| 13:00–14:00 | CHECKPOINT 2: Narration TTS speaks 3-sentence summary correctly. All 11 OWM endpoints verified |
| 14:00–17:00 | TypeScript full path: `engineer_typescript.txt` prompt, tsc validation, fix common issues |
| 17:00–18:00 | Refine prompts based on stress test failures — this is expected, prompts need iteration |
| 18:00–21:00 | Stress test 8 full runs. Fix prompt failures. Ensure narration sounds natural for all 4 demo APIs |
| 21:00–23:00 | Write final versions of all prompts. Prepare `examples/jsonplaceholder_typescript/` |

---

## 5. 🎨 DEV 4 — Frontend & Extensions Engineer

### Primary Responsibility

Dev 4 owns everything the user sees and touches: the Chrome extension popup with its colour-coded terminal, the VS Code extension with its Agent Panel webview and file injector, the Chrome↔VS Code bridge protocol, the TTS narration system in both environments, the in-page overlay panel, and the history sidebar.

### Stack & Tools

| | |
|---|---|
| **Chrome Ext** | Manifest v3, Vanilla JS, Web Speech API, SSE EventSource, WebSocket |
| **VS Code Ext** | TypeScript, vscode API, Webview API, vscode.workspace.fs, URI handler |
| **Bridge** | WebSocket on `ws://localhost:47291`, `vscode://` URI fallback, clipboard fallback |
| **UI Colours** | Supervisor: `#a78bfa` · Reroute: `#fbbf24` · Researcher: `#60a5fa` · Architect: `#34d399` · Engineer: `#86efac` · QA pass: `#4ade80` · QA fail: `#f87171` · Packager: `#94a3b8` |

### Deliverables — File by File

| File / Module | Responsibility |
|---------------|----------------|
| `chrome-extension/manifest.json` | Manifest v3: permissions (activeTab, scripting, storage, tabs), host_permissions for localhost:8000 |
| `chrome-extension/popup/popup.html` | 400×520 dark terminal UI: URL input, language selector, output selector, Generate button, scrolling terminal log |
| `chrome-extension/popup/popup.js` | SSE EventSource consumer: parse events, render coloured lines, handle reroute amber flash, TTS trigger |
| `chrome-extension/popup/popup.css` | Dark terminal theme, agent colour variables, scrollable log, button states |
| `chrome-extension/content/content.js` | `extractMainContent()`, `extractDocLinks()` (cap at 100), overlay panel injection + update |
| `chrome-extension/background/background.js` | WebSocket probe to `ws://localhost:47291` (100ms timeout), `vscode://` URI open |
| `chrome-extension/lib/bridge.js` | Chrome→VS Code bridge: WS send or URI fallback, `port_info` handling, clipboard fallback |
| `chrome-extension/lib/tts.js` | `TTSController`: speak(), toggle(), stop(), voice selection (en-GB Google > Daniel > Alex) |
| `chrome-extension/lib/api.js` | Backend HTTP helpers: `postStart()`, `streamSSE()`, `downloadZip()` |
| `vscode-extension/src/extension.ts` | Activation: register commands (generate, resume, history), URI handler registration |
| `vscode-extension/src/bridge/uriHandler.ts` | `handleUri()`: extract job_id, open AgentPanel, connect SSE stream |
| `vscode-extension/src/bridge/wsServer.ts` | WS server on port 47291 (fallback 47292, 47293): receive `new_job`, send `vscode_ready` |
| `vscode-extension/src/panels/AgentPanel.ts` | Webview HTML with SSE terminal, colour-coded agent rows, narrate toggle |
| `vscode-extension/src/injector/fileWriter.ts` | Write `file_ready` events to `{workspace}/src/sdk/`, create directories, `revealInExplorer` |
| `vscode-extension/src/injector/installer.ts` | Run `pip install` / `npm install` in integrated terminal on `install_cmd` event |
| `vscode-extension/src/injector/opener.ts` | Open `client.py` or `client.ts` in editor on `complete` event |
| `vscode-extension/src/tts/narrator.ts` | `postMessage { type: 'speak', text }` to Webview for TTS |
| `vscode-extension/src/memory/historyView.ts` | TreeView: list past jobs from checkpoint files, Re-open / Re-run buttons |

### Detailed Task Breakdown

#### Task 4.1 — Chrome Extension Scaffolding (Hour 0–2)

- Create `chrome-extension/` with correct Manifest v3 structure:
  - `permissions`: activeTab, scripting, storage, tabs
  - `host_permissions`: `http://localhost:8000/*`
  - `content_scripts`: `content.js` on `all_urls` at `document_idle`
  - `background`: `background.js` as `service_worker`
  - `action`: `popup.html`
- Load extension in Chrome: `chrome://extensions` → Developer mode → Load unpacked → select `chrome-extension/`
- Verify: clicking extension icon opens popup with no JS errors in devtools

#### Task 4.2 — content.js — Page Capture (Hour 1–3)

`content.js` is the bridge between the browser page and the backend. It must reliably extract both text content and structured links.

- Implement `extractMainContent()`:
  - Try selectors in order: `main`, `article`, `[role='main']`, `.content`, `.docs-content`, `.markdown-body`, `body`
  - Return first match with `innerText.trim().length > 500`, sliced to 50000 chars
- Implement `extractDocLinks()`:
  - `querySelectorAll('a[href]')` — deduplicate by href
  - Filter: same origin, no hash, text length 3–80 chars
  - Add `inNav: true` if link is inside `nav/aside/[role='navigation']/.sidebar`
  - Cap at 100 links
- Listen for `GET_PAGE_CONTENT` message → respond with `{ url, title, content, links }`
- Listen for `SHOW_OVERLAY` + `UPDATE_OVERLAY` messages → inject/update sidebar panel
- Test on 5 real API doc sites: verify links list has text/href/inNav for each

#### Task 4.3 — Popup Terminal UI (Hour 2–5)

The popup is what judges will stare at during the demo. It must look polished and the colour coding must be instantly readable.

- `popup.html`: 400×520px, dark background (`#0d1117`), scrollable terminal log div, form fields:
  - URL input: auto-fills from active tab via `chrome.tabs.query`
  - Language selector: Python (default) / TypeScript toggle buttons
  - Output selector: VS Code (default) / Download ZIP toggle
  - Generate button: large, accent colour, disabled state during generation
  - Terminal log: monospace font, auto-scrolls to bottom, each line has agent prefix and colour
  - Bottom bar: Narrate ON/OFF toggle, Download ZIP button, Open in VS Code button
- `popup.js` — SSE consumer:
  - On Generate click: send `GET_PAGE_CONTENT` to `content.js` → `POST /generate/start` → get `job_id`
  - Open `EventSource('http://localhost:8000/generate/stream?job_id=X')`
  - For each SSE event: call `renderLine(event)` → append coloured text to terminal
  - On `reroute` event: flash amber on terminal border for 2 seconds
  - On `narrate` event: call `tts.speak(event.text)` if narrate toggle is ON
  - On `complete` event: enable Download ZIP + Open in VS Code buttons
- Implement all SSE event type → terminal line mappings with correct colours (see colour table above)
- Handle C5: popup closed mid-generation → on reopen, check `chrome.storage` for active `job_id` → show 'Job in progress — resume' banner

#### Task 4.4 — TTS System — Chrome (Hour 3–4)

- Create `chrome-extension/lib/tts.js` — `TTSController` class:
  - `constructor`: check `'speechSynthesis' in window` → set `this.available`
  - `speak(text)`: cancel any current utterance, create `SpeechSynthesisUtterance`
  - Voice selection priority: en-GB Google > name includes 'Daniel' > name includes 'Alex' > fallback to `voices[0]`
  - `rate: 1.05`, `pitch: 0.95`
  - `toggle()`, `stop()` methods
- Handle C4 edge case: `speechSynthesis` unavailable → silently disable narrate toggle, show no error
- Test: `speak()` call → browser speaks "We built a 9-method Python SDK for JSONPlaceholder"

#### Task 4.5 — Chrome↔VS Code Bridge (Hour 3–5)

The bridge is the most complex piece of Dev 4's work. It has three layers: WebSocket (preferred), URI handler (fallback), clipboard (last resort).

- `background.js` — WebSocket probe:
  - On popup open: WebSocket probe to `ws://localhost:47291` with 100ms timeout
  - OPEN → store `wsConnection`, show `● VS Code connected` green badge in popup
  - CLOSED → show `○ VS Code not detected` with install hint text
- `lib/bridge.js` — send `new_job`:
  - If `wsConnection` open: `ws.send({ type: 'new_job', job_id, url, language })`
  - If ws closed: `window.open('vscode://docs-to-code.extension/generate?job_id=' + job_id)`
  - If neither works (V4): copy `job_id` to clipboard, show 'Open VS Code → run Resume Job' banner
- Handle `port_info` message from VS Code: if VS Code used fallback port 47292/47293, update `wsConnection`
- Chrome popup log: `✓ client.py → VS Code` when receiving `file_written` confirmation from VS Code

#### Task 4.6 — In-Page Overlay Panel (Hour 4–6)

The overlay makes the demo look impressive — the docs page itself shows the agent status.

- `content.js` — `injectOverlayPanel(jobId)`:
  - Create fixed-position div, right edge of page, 280px wide
  - Header: `⚡ docs-to-code` with minimise and close buttons
  - Scrollable log area showing condensed agent events (1 line per event)
  - CSS: dark background, agent colour coding matching popup
- `content.js` — `updateOverlayPanel(event)`:
  - Append new line to overlay log based on event type
  - Show red ✗ for QA failures, green ✓ for passes
  - Amber flash on reroute events
- `popup.js`: after `job_id` received → send `SHOW_OVERLAY` to `content.js`; per SSE event → send `UPDATE_OVERLAY`
- Edge case: if content.js injection blocked by CSP → catch error, disable overlay silently (popup still works)

#### Task 4.7 — VS Code Extension (Hour 2–6)

The VS Code extension is what makes the demo closing moment work — judges watch the file tree populate in real time.

- `extension.ts` — activation:
  - Register commands: `docs-to-code.generate`, `.resume`, `.history`
  - Register URI handler: `handleUri()` for `vscode://docs-to-code.extension/generate?job_id=X`
  - Start WS server on port 47291 (try 47292, 47293 if in use) via `wsServer.ts`
- `uriHandler.ts` — `handleUri(uri)`:
  - Extract `job_id` from `URLSearchParams`
  - Call `AgentPanel.createOrShow(extensionUri, jobId)`
  - Open `SSEClient` to `http://localhost:8000/generate/stream?job_id=X`
  - Route: all events → `AgentPanel.postMessage(e)`; `file_ready` → `FileWriter.write()`; `install_cmd` → `Installer.run()`; `narrate` → `Narrator.speak()`; `complete` → `Opener.openMainFile()`
- `AgentPanel.ts` — Webview HTML:
  - Dark terminal matching Chrome popup style
  - Agent colour coding via CSS variables
  - Narrate ON/OFF toggle
  - `postMessage` handler for `'speak'` events
- `fileWriter.ts`:
  - Get workspace root: `vscode.workspace.workspaceFolders[0].uri`
  - Construct path: `{workspace}/src/sdk/{filename}`
  - Create directories recursively if needed
  - Write file via `vscode.workspace.fs.writeFile`
  - Call `revealInExplorer` on written file
  - Handle V1: no workspace open → `showErrorMessage` with open-folder action
  - Handle V2: `src/sdk/` exists → `showInformationMessage` 'Overwrite existing SDK?' yes/no dialog
- `wsServer.ts`:
  - WebSocket server on port 47291
  - Handle `new_job` message → open URI handler directly
  - On port conflict: try 47292, 47293 → send `port_info` message back to Chrome

#### Task 4.8 — UI Polish & Edge Cases (Hour 14–21)

- Popup mobile layout: ensure 400×520 renders correctly on smaller screens
- Loading states: spinner during initial page content capture and backend `/start` call
- Colour coding final pass: compare all agent colours against design spec, fix any inconsistencies
- History sidebar: show job entries from past runs with timestamps, endpoint count, re-route count
- Test all bridge fallbacks in order: WS → URI → clipboard — verify each works and shows correct UI feedback
- Handle V3: if ports 47291–47293 all in use → show error with instructions to close conflicting process
- Test V6: Webview CSP blocks `speechSynthesis` → add `media-src` nonce to CSP header in `AgentPanel`

### Hour-by-Hour Schedule

| Time | Task |
|------|------|
| 00:00–01:30 | SETUP: Chrome extension loads (no errors), VS Code extension activates, WS server starts on port 47291 |
| 01:30–03:00 | `content.js`: extractMainContent + extractDocLinks tested on 5 real docs sites. Popup renders mock SSE events with colours |
| 03:00–05:00 | Popup JS: SSE consumer working (connect to mock SSE endpoint, render coloured lines). TTS speaks on narrate event |
| 04:00–06:00 | (Parallel) VS Code AgentPanel renders coloured events. FileWriter writes mock file_ready to temp workspace. Bridge: URI opens panel |
| 06:00–08:00 | CHECKPOINT 1: Chrome popup connects to real SSE stream. `researcher_crawl_plan` events render selected/skipped pages correctly |
| 08:00–10:00 | Bridge end-to-end: Chrome click → WS message → VS Code panel opens → SSE stream active in VS Code simultaneously |
| 10:00–13:00 | `file_ready` events → files appear in VS Code workspace file tree. Verify `revealInExplorer` works |
| 13:00–14:00 | CHECKPOINT 2: Both TTS speak narration. Reroute amber flash visible. Real file tree populated in demo |
| 14:00–18:00 | Overlay panel polish. History sidebar populated from real jobs. All colour coding finalised |
| 18:00–21:00 | Test all edge cases: C1–C6 (Chrome) and V1–V6 (VS Code). Mobile popup layout. Loading states |
| 21:00–23:00 | Final UI polish. Record demo backup video. Verify all screenshots for Devpost |

---

## 6. Integration Checkpoints & Coordination

These are the four moments where all four developers must synchronise. Nothing should block these checkpoints — if an agent isn't ready, use a stub.

| Time | Checkpoint | What Must Be Working |
|------|------------|----------------------|
| Hour 1:30 | **Environment Green** | All 4 devs: venv active, Gemini responds, Chrome extension loads, VS Code extension activates, WS server on 47291 starts. Confirm in group chat before proceeding. |
| Hour 6:00 | **Checkpoint 1: Researcher Live** | Chrome click → POST /start → Supervisor routes to Researcher → Researcher completes → SSE events visible in Chrome popup (crawl_plan with selected/skipped pages). Dev 1 + Dev 2 + Dev 4 must sync here. |
| Hour 13:00 | **Checkpoint 2: Full Scenario B** | Chrome click on OpenWeatherMap → full pipeline runs → QA fails (401) → Supervisor re-routes → Engineer fixes → QA re-runs (11/11) → files appear in VS Code workspace → TTS narrates. All 4 devs present. |
| Hour 21:00 | **Demo Ready** | 2-minute demo script rehearsed twice. Backup video recorded. examples/ has 3 pre-generated SDKs. All 4 APIs tested in both languages. README complete. |

### Dependency Map

- **Dev 1's `SDKJobState` (Hour 2)** blocks: Dev 2 agent implementation, Dev 3 agent implementation — **do this FIRST**
- **Dev 1's `/generate/start` endpoint (Hour 4)** blocks: Dev 4 popup JS can't POST job — stubs acceptable until then
- **Dev 1's `/generate/stream` endpoint (Hour 4)** blocks: Dev 4 SSE consumer in both extensions
- **Dev 2's `scrape_web` tool (Hour 3)** blocks: Researcher agent Phase 2 — Dev 2 owns both
- **Dev 2's `select_pages` tool (Hour 3)** blocks: Researcher agent Phase 1 — Dev 2 owns both
- **Dev 3's `validate_schema` tool (Hour 4)** blocks: Architect agent output — Dev 3 owns both
- **Dev 3's `syntax_check` tool (Hour 4)** blocks: Engineer agent self-validation
- **Dev 4's `content.js` link extraction (Hour 3)** blocks: Researcher Phase 1 having real `page_links` to plan against

### Communication Protocol

- Use a shared team channel (WhatsApp/Slack) for live updates
- When a shared interface changes (state fields, SSE event schema, API endpoint signature) — **announce immediately**
- SSE event schema is **frozen at Hour 4** — both Dev 4 (renderer) and Dev 1 (emitter) must agree on this
- If blocked: implement a mock/stub and keep moving. Don't wait more than 20 minutes for a dependency

---

## 7. Edge Case Responsibilities

| # | Owner | Scenario | Handling |
|---|-------|----------|----------|
| R1 | Dev 2 | LLM selects 0 pages from crawl plan | Fall back to all navigation-level links (depth 1), max 5 |
| R2 | Dev 2 | Selected page returns 404 | Skip, log in SSE `agent_warn`, continue with other pages |
| R3 | Dev 2 | Page redirects to /login | Skip, emit `agent_warn`, note in `knowledge_base` |
| R5 | Dev 2 | Chrome-injected content < 300 chars | Fall back to Playwright-scrape the landing page too |
| R8 | Dev 2 | `page_links` list is empty | Find links in `page_content` via regex as fallback |
| A1 | Dev 1 | Supervisor routes same agent 3x for unresolved issue | `status=failed`, surface last error + last SDK state |
| A2 | Dev 1 | `iteration_count` >= 15 | Force END, emit `safety_cutoff` SSE event |
| A3 | Dev 1 | `qa_iteration` >= 4 | Force END: "QA could not be resolved after 4 attempts" |
| A4 | Dev 1 | Gemini rate limit hit | Exponential backoff: 2s, 4s, 8s, then fail gracefully |
| A5 | Dev 3 | Supervisor returns invalid JSON | Retry once with stricter prompt, then fail with last known routing |
| A6 | Dev 3 | Engineer internal syntax retry fails twice | Escalate to Supervisor with error + code |
| A7 | Dev 2 | QA hits auth-gated endpoint | Mark as `untestable_auth_required`, count as skip not failure |
| C1 | Dev 4 | VS Code bridge WS probe fails | Show install hint, show Download ZIP as primary CTA |
| C2 | Dev 4 | Backend not running | "Start backend server" message + copy-paste command |
| C4 | Dev 4 | `speechSynthesis` unavailable in Chrome | Silently disable narrate toggle, no error shown |
| C5 | Dev 4 | Popup closed mid-generation | Job continues; reopen shows "Job in progress — resume" banner |
| V1 | Dev 4 | No workspace folder open in VS Code | Show "Open a folder first" with open-folder action button |
| V2 | Dev 4 | `src/sdk/` already exists | Dialog: "Overwrite existing SDK?" yes/no |
| V3 | Dev 4 | WS port 47291 in use | Try 47292, 47293 — send chosen port back to Chrome in `port_info` message |

---

## 8. Demo Day Playbook

### The 2-Minute Demo Script

```
[0:00]  Chrome open on openweathermap.org/api
        "I'm on the OpenWeatherMap API docs. I click the extension."

[0:08]  Popup opens. URL auto-filled. Python selected. Hit Generate.
        "The squad starts. Supervisor delegates to the Researcher."

[0:15]  Point at the crawl plan in the popup terminal:
        "The Researcher asked the LLM which of these 34 pages are actually
         useful. It picked 4. It's skipping the pricing page, the blog,
         the migration guide. Only scraping what matters."

[0:30]  Researcher scraping events fire one by one:
        "Scraping the auth page first — that's the priority. Then endpoints."

[0:45]  Architect and Engineer events:
        "Schema validated — two auto-fixes. SDK written."

[1:00]  QA Tester fires — the centrepiece:
        "QA is calling the live API right now. Watch..."
        ✗ event fires (red) — 401 Unauthorized
        "Got a 401. Missing the API key param."

[1:10]  SUPERVISOR reroute event fires (amber):
        "Supervisor decided: this is a code bug, not a docs problem.
         Re-routing directly to Engineer — not wasting time re-scraping."

[1:20]  Engineer fix + QA re-run:
        "Fix applied. QA re-running..."
        All green: "11/11 verified."

[1:35]  VS Code comes to front. Files appear in workspace explorer.
        "No download. No ZIP. Straight into the project."
        Show IntelliSense on client methods.

[1:50]  TTS speaks the narration summary.
        "It even tells you what it built."
```

### The Three Lines That Win the Room

1. When crawl plan fires: **"The AI chose which pages to read — and which to ignore."**
2. When QA red event fires: **"That's a real HTTP 401 from the live OpenWeatherMap API."**
3. When reroute fires: **"No human told it what to do. The squad figured it out."**

### Demo APIs — Natural Re-Route Triggers

| API | Natural Failure Trigger | Demo Value |
|-----|------------------------|------------|
| **OpenWeatherMap** | Missing `?appid=` param → 401 | Reliable re-route: Engineer fixes API key injection **(PRIMARY DEMO API)** |
| **JSONPlaceholder** | `/post` vs `/posts` path → 404 | Reliable re-route: Engineer fixes endpoint path |
| **REST Countries** | Field name casing in response schema | Best TypeScript demo — shows type inference |
| **GitHub REST** | Missing Accept header / pagination | Advanced demo — shows complex header handling |

### Backup Plan

- Pre-generated examples in `/examples` → show directly in VS Code if live run fails
- Screen recording of full Scenario B saved as `demo_backup.mp4`
- If live HTTP QA fails due to network → show recording of reroute moment
- If VS Code bridge fails → run `Docs to Code: Resume Job` with pre-known `job_id`
- If Gemini API is down → have one pre-run state checkpoint ready to stream from

### What NOT to Demo Live

- GitHub full docs — 60s+, too slow for judges
- Any auth-gated API requiring real credentials
- TypeScript `tsc` validation — 15s of dead silence
- The clipboard fallback bridge — looks broken even when it works

---

*The pipeline tells you what it did. The squad tells you what it decided.* ⚡