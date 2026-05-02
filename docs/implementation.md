# Docs-to-Code — Final Master Plan
### LangGraph Supervisor Multi-Agent · LLM-Guided Selective Crawling · Chrome + VS Code Extensions · Live HTTP Verification · Read-Aloud Narration
### Complete Engineering Blueprint · 24-Hour Hackathon · 4-Person Team

---

## Table of Contents

1. [Vision & Core Philosophy](#1-vision--core-philosophy)
2. [The Agent Squad](#2-the-agent-squad)
3. [LangGraph State & Graph Architecture](#3-langgraph-state--graph-architecture)
4. [The Researcher Agent — LLM-Guided Selective Crawling (Deep Dive)](#4-the-researcher-agent--llm-guided-selective-crawling-deep-dive)
5. [Scenario B — The Non-Linear Agentic Flow (DEFAULT)](#5-scenario-b--the-non-linear-agentic-flow-default)
6. [All Agent Definitions & Tools](#6-all-agent-definitions--tools)
7. [SSE Event Schema — Real-Time Narration](#7-sse-event-schema--real-time-narration)
8. [Chrome Extension](#8-chrome-extension)
9. [VS Code Extension](#9-vs-code-extension)
10. [Read-Aloud Narration System](#10-read-aloud-narration-system)
11. [Cross-Extension Bridge Protocol](#11-cross-extension-bridge-protocol)
12. [Repository Structure](#12-repository-structure)
13. [Team Roles & 24-Hour Timeline](#13-team-roles--24-hour-timeline)
14. [Prompt Engineering Reference](#14-prompt-engineering-reference)
15. [Edge Cases Master Registry](#15-edge-cases-master-registry)
16. [Environment Setup](#16-environment-setup)
17. [Demo Day Playbook](#17-demo-day-playbook)

---

## 1. Vision & Core Philosophy

### What "Agentic" Actually Means Here

The old version was a for-loop with LLM calls inside it. Fixed steps, fixed
order, no awareness. The AI was a conveyor belt.

This version is a **squad of specialists** supervised by an LLM that reads the
situation and decides what to do next — including routing backwards when
something fails. Nobody hardcodes the order. The graph edges are decisions.

```
Old:  scrape → extract → types → sdk → tests → done (always, regardless)

New:  Supervisor reads state
        → delegates to the right agent
        → agent uses tools, reports result
        → Supervisor re-reads, decides again
        → loops, backtracks, or finishes based on what actually happened
```

### The Three Innovations in This Plan

**1. LLM-Guided Selective Crawling**
The Researcher does not blindly scrape every link. It gives the landing page
to the LLM, which reads the link structure and decides exactly which pages
are worth crawling — "Authentication", "Endpoints", "Reference" — and ignores
changelogs, pricing, and blog posts. Clean input → far better schema output.
On a QA failure caused by missing auth info, the Supervisor sends the Researcher
back with a targeted instruction: "Find the authentication documentation." The
Researcher asks the LLM again with that specific goal. Precision re-crawl.

**2. LangGraph Multi-Agent with Non-Linear Routing**
QA Tester calls the live API with real HTTP requests. On failure, it reports
back to the Supervisor with the exact error. The Supervisor decides whether
to re-route to Researcher (docs problem), Engineer (code problem), or both.
This loop runs until all endpoints pass or the safety limit is hit.

**3. Direct VS Code Workspace Delivery**
No ZIP. No download. Files arrive in the VS Code workspace as `file_ready`
SSE events — each file written the moment it is generated. The user watches
their file tree populate in real time.

### The One Sentence Pitch

> "An AI squad that intelligently reads only the relevant API docs, writes a
> typed SDK, calls the live endpoints to verify it works, fixes any bugs
> autonomously, and delivers the final result directly into your VS Code
> workspace — narrated aloud the whole way."

---

## 2. The Agent Squad

```
🧠 Supervisor    — Reads entire state. Decides who acts next. Never writes code.
🕵️  Researcher   — LLM-guided selective crawling. Builds a clean knowledge base.
📐 Architect     — Turns knowledge base into a validated, logical API schema.
💻 Engineer      — Writes the SDK files. Self-checks syntax before reporting.
🧪 QA Tester     — Makes real HTTP calls to the live API. Reports pass/fail exactly.
📦 Packager      — Final assembly. Emits files to VS Code. Triggers TTS narration.
```

### Why Each Agent Exists

**Supervisor** exists because no hardcoded order survives contact with real-world
APIs. Only an LLM reading the actual outcomes can decide whether to loop back,
skip ahead, or give up gracefully.

**Researcher** exists as a separate agent (not a pipeline step) because crawling
is a multi-decision process — which links to follow, how deep to go, when to
stop. These are judgment calls that benefit from LLM reasoning, not heuristics.

**Architect** exists separately from the Researcher because schema design
requires different reasoning than information gathering. The Researcher collects;
the Architect structures, validates, and fixes logical inconsistencies.

**Engineer** exists separately from the Architect because code generation and
schema design are fundamentally different tasks. Keeping them separate means
targeted re-routing — if QA fails due to a code bug, the Supervisor routes to
Engineer only, not back to Architect.

**QA Tester** exists because syntax validation is not quality assurance. An SDK
can be syntactically perfect and functionally broken. Live HTTP verification
is the only real test — and it's the demo centrepiece.

**Packager** is a deterministic node (not an LLM agent) because final assembly
should be reliable and fast. It does call the LLM once — for the narration
summary — but all file operations are code, not prompts.

---

## 3. LangGraph State & Graph Architecture

### The Shared State Object

All agents read from and write to one shared state. No manual string passing.
State is the single source of truth — every agent decision is based on it.

```python
from typing import TypedDict, Annotated, Sequence
from langchain_core.messages import BaseMessage
import operator

class SDKJobState(TypedDict):

    # ── Core conversation ─────────────────────────────────────────────────
    # Every agent appends messages here. Supervisor reads all of them.
    messages: Annotated[Sequence[BaseMessage], operator.add]

    # ── Job metadata ──────────────────────────────────────────────────────
    job_id:        str
    target_url:    str
    language:      str        # "python" | "typescript"
    page_content:  str        # landing page text — injected by Chrome extension
    page_links:    list[dict] # [{ "text": "Auth", "href": "/docs/auth" }, ...]
                              # extracted by content.js, sent with page_content

    # ── Researcher outputs ────────────────────────────────────────────────
    crawl_plan:     list[dict] | None   # LLM-selected pages to crawl
                                        # [{ "url": "...", "reason": "...", "priority": 1 }]
    crawled_pages:  list[dict] | None   # pages actually scraped
                                        # [{ "url": "...", "content": "..." }]
    knowledge_base: dict | None         # structured research output
                                        # { endpoints_raw, auth_info, base_url, notes }

    # ── Architect outputs ─────────────────────────────────────────────────
    api_schema:     dict | None         # validated, structured endpoint schema
    schema_fixes:   list[str]           # list of auto-fixes applied by Architect

    # ── Engineer outputs ──────────────────────────────────────────────────
    sdk_files:      dict | None         # { "client.py": "...", "models.py": "...", ... }
    syntax_errors:  list[str]           # syntax issues found and fixed internally

    # ── QA Tester outputs ─────────────────────────────────────────────────
    test_results:   list[dict] | None   # [{ endpoint, method, url, status,
                                        #    expected, passed, error, latency_ms }]
    qa_iteration:   int                 # how many QA rounds have run

    # ── Packager outputs ──────────────────────────────────────────────────
    final_files:    dict | None         # linted, final files sent to VS Code
    narration_text: str | None          # spoken summary generated by LLM

    # ── Routing & control ─────────────────────────────────────────────────
    next_agent:      str
    iteration_count: int      # total graph iterations — safety ceiling: 15
    status:          str      # "running" | "success" | "failed"
    failure_reason:  str | None

    # ── SSE event queue (append-only, consumed by FastAPI stream endpoint) ─
    sse_events: Annotated[list[dict], operator.add]
```

### The LangGraph Graph

```python
from langgraph.graph import StateGraph, END

graph = StateGraph(SDKJobState)

graph.add_node("supervisor",  supervisor_node)
graph.add_node("researcher",  researcher_node)
graph.add_node("architect",   architect_node)
graph.add_node("engineer",    engineer_node)
graph.add_node("qa_tester",   qa_tester_node)
graph.add_node("packager",    packager_node)

graph.set_entry_point("supervisor")

# Every agent reports back to Supervisor — it always reads before deciding
graph.add_edge("researcher", "supervisor")
graph.add_edge("architect",  "supervisor")
graph.add_edge("engineer",   "supervisor")
graph.add_edge("qa_tester",  "supervisor")
graph.add_edge("packager",   END)

# Supervisor routes via conditional edge — LLM decision
graph.add_conditional_edges(
    "supervisor",
    route_next,
    {
        "researcher": "researcher",
        "architect":  "architect",
        "engineer":   "engineer",
        "qa_tester":  "qa_tester",
        "packager":   "packager",
        "end":        END,
    }
)

app = graph.compile()
```

### The Router Function

```python
def route_next(state: SDKJobState) -> str:
    """
    Pure function — reads state.next_agent set by Supervisor LLM.
    Hard safety overrides take priority over LLM decision.
    """
    if state["status"] == "failed":
        return "end"
    if state["iteration_count"] >= 15:
        # Force failure — log the reason
        return "end"
    if state["qa_iteration"] >= 4:
        # QA has looped 4 times — something is fundamentally broken
        return "end"
    return state["next_agent"]
```

---

## 4. The Researcher Agent — LLM-Guided Selective Crawling (Deep Dive)

This is the most important new system in this plan. It directly determines
the quality of everything downstream: schema, SDK, and test accuracy all depend
on how clean and complete the research is.

### The Core Problem with Brute Scraping

A typical API docs site has 30–80 pages. Maybe 5–8 of them contain useful
information for SDK generation. The rest are changelogs, pricing tables,
blog posts, SDKs for other languages, tutorials, and legal pages. Feeding all
of that to the schema extraction LLM creates noise that degrades output quality
and wastes tokens on irrelevant content.

### The Solution: Two-Phase LLM-Guided Crawl

**Phase 1 — LLM reads the landing page and selects which pages to crawl.**
The Researcher scrapes only the landing page, extracts all links as a clean
structured list, and sends them to the LLM with a targeted prompt. The LLM
returns a prioritized list of pages to crawl with a reason for each selection.
No code heuristics. No keyword matching. The LLM reads the link text and
decides what's relevant.

**Phase 2 — Researcher scrapes only the selected pages.**
Targeted scraping of 3–6 pages maximum. Combines all content into a
structured knowledge base. Done.

**Phase 3 (conditional) — Targeted re-crawl on QA failure.**
If the QA Tester finds a failure and the Supervisor determines it's a
documentation gap (e.g. wrong auth header, missing endpoint path), the
Supervisor routes back to the Researcher with a specific instruction:
*"Find the authentication documentation — the API key header name is wrong."*
The Researcher runs Phase 1 again with that goal injected into the LLM prompt,
gets a new crawl plan focused on auth/security pages, scrapes them, and
updates the knowledge base. This targeted re-crawl typically resolves the
issue in one pass.

### Phase 1 — Link Selection in Detail

```
INPUT TO LLM:
  - Target URL: https://docs.openweathermap.org/api
  - Goal: "Find all API documentation pages needed to generate a complete SDK"
  - Links: [
      { "text": "Current Weather",    "href": "/current",           "depth": 1 },
      { "text": "Forecast",           "href": "/forecast5",         "depth": 1 },
      { "text": "Authentication",     "href": "/appid",             "depth": 1 },
      { "text": "Geocoding API",      "href": "/geocoding-api",     "depth": 1 },
      { "text": "Pricing",            "href": "/price",             "depth": 1 },
      { "text": "FAQ",                "href": "/faq",               "depth": 1 },
      { "text": "Blog",               "href": "/blog",              "depth": 1 },
      { "text": "Migration Guide",    "href": "/migration",         "depth": 1 },
      { "text": "One Call API 3.0",   "href": "/onecall-3",         "depth": 1 },
      { "text": "Historical Weather", "href": "/history",           "depth": 1 },
    ]

OUTPUT FROM LLM:
  {
    "crawl_plan": [
      { "url": "https://docs.openweathermap.org/appid",
        "reason": "Authentication page — need API key header details",
        "priority": 1 },
      { "url": "https://docs.openweathermap.org/current",
        "reason": "Primary endpoint — current weather data",
        "priority": 2 },
      { "url": "https://docs.openweathermap.org/forecast5",
        "reason": "Core endpoint — 5-day forecast",
        "priority": 3 },
      { "url": "https://docs.openweathermap.org/onecall-3",
        "reason": "Core endpoint — comprehensive weather data",
        "priority": 4 }
    ],
    "skipped": [
      { "url": "/price",      "reason": "Pricing page — not relevant to SDK" },
      { "url": "/faq",        "reason": "FAQ — no endpoint definitions" },
      { "url": "/blog",       "reason": "Blog — not relevant" },
      { "url": "/migration",  "reason": "Migration guide — not needed for new SDK" },
      { "url": "/history",    "reason": "Historical data — secondary, skip for now" }
    ],
    "notes": "Authentication page is highest priority — must crawl first"
  }
```

The LLM correctly identifies that Pricing, FAQ, Blog, and Migration Guide
are useless for SDK generation. It prioritises the auth page above endpoint
pages because you can't generate correct SDK auth code without knowing the
header name and format.

### Phase 2 — Targeted Scraping

```python
async def phase_2_scrape(crawl_plan: list[dict], state: SDKJobState) -> list[dict]:
    """
    Scrapes pages in priority order.
    Emits SSE events for each page scraped.
    Returns list of { url, content } dicts.
    """
    scraped = []
    for page in sorted(crawl_plan, key=lambda x: x["priority"]):
        # Emit: 🕵️ RESEARCHER  Scraping: Authentication (/appid)
        emit_sse(state, "researcher_scraping", page["url"], page["reason"])

        content = await scrape_web_tool(page["url"])
        scraped.append({ "url": page["url"], "content": content })

        # Emit: 🕵️ RESEARCHER  ✓ Scraped /appid — 2,847 chars
        emit_sse(state, "researcher_scraped", page["url"], len(content))

    return scraped
```

### Phase 3 — Targeted Re-Crawl (Supervisor-Directed)

When the Supervisor routes back to the Researcher after a QA failure, it
includes a specific `instruction` in the message. The Researcher detects this
is a re-crawl (because `knowledge_base` is already set) and runs Phase 1 again
with the instruction injected as an additional goal:

```python
async def researcher_node(state: SDKJobState) -> SDKJobState:
    supervisor_instruction = get_last_supervisor_instruction(state["messages"])
    is_recrawl = state["knowledge_base"] is not None

    if is_recrawl:
        # Targeted re-crawl — inject Supervisor's specific goal
        # e.g. "Find the authentication documentation — the API key header is wrong"
        emit_sse(state, "researcher_recrawl", supervisor_instruction)
        crawl_plan = await llm_select_pages(
            landing_content=state["page_content"],
            links=state["page_links"],
            goal=supervisor_instruction,         # ← targeted goal
            already_crawled=state["crawled_pages"]  # ← don't re-scrape known pages
        )
        new_pages = await phase_2_scrape(crawl_plan, state)
        # Merge new pages into existing knowledge base
        updated_kb = await merge_knowledge_base(state["knowledge_base"], new_pages)
        return { **state, "crawled_pages": state["crawled_pages"] + new_pages,
                 "knowledge_base": updated_kb }
    else:
        # First crawl — full Phase 1 + Phase 2
        crawl_plan = await llm_select_pages(
            landing_content=state["page_content"],
            links=state["page_links"],
            goal="Find all pages needed to generate a complete, correct SDK"
        )
        pages = await phase_2_scrape(crawl_plan, state)
        knowledge_base = await build_knowledge_base(pages)
        return { **state, "crawl_plan": crawl_plan,
                 "crawled_pages": pages, "knowledge_base": knowledge_base }
```

### What content.js Sends (Chrome Extension)

The Chrome extension sends both page content AND a structured link list.
This is the key — the LLM gets clean link metadata, not raw HTML.

```javascript
// content.js
function extractDocLinks() {
    const links = [];
    document.querySelectorAll('a[href]').forEach(a => {
        const href = a.href;
        const text = a.innerText.trim();
        // Filter: same domain, not anchors, not external, has text
        if (href.startsWith(window.location.origin) &&
            !href.includes('#') &&
            text.length > 2 &&
            text.length < 80) {
            links.push({
                text: text,
                href: href,
                // Navigation depth hint (sidebar links vs footer links)
                inNav: !!a.closest('nav, aside, [role="navigation"]')
            });
        }
    });
    // Deduplicate by href
    return [...new Map(links.map(l => [l.href, l])).values()].slice(0, 100);
}
```

This structured list — `[{ text, href, inNav }]` — is what the LLM receives
for the crawl plan decision. It is vastly easier for the LLM to reason over
than raw HTML with anchor tags embedded in a wall of text.

### SSE Events the User Sees During Crawling

```
🕵️ RESEARCHER   Landing page received from Chrome extension (14,203 chars)
🕵️ RESEARCHER   Analysing 34 links — asking LLM which pages to crawl...
🕵️ RESEARCHER   Crawl plan ready: 4 pages selected, 30 skipped
🕵️ RESEARCHER   Selected: /appid (Authentication — priority 1)
🕵️ RESEARCHER   Selected: /current (Current Weather endpoint — priority 2)
🕵️ RESEARCHER   Selected: /forecast5 (Forecast endpoint — priority 3)
🕵️ RESEARCHER   Selected: /onecall-3 (One Call API — priority 4)
🕵️ RESEARCHER   Skipped: /price, /faq, /blog, /migration, /history (+25 more)
🕵️ RESEARCHER   Scraping /appid...
🕵️ RESEARCHER   ✓ /appid scraped (2,847 chars)
🕵️ RESEARCHER   Scraping /current...
🕵️ RESEARCHER   ✓ /current scraped (5,102 chars)
🕵️ RESEARCHER   Scraping /forecast5...
🕵️ RESEARCHER   ✓ /forecast5 scraped (4,371 chars)
🕵️ RESEARCHER   Scraping /onecall-3...
🕵️ RESEARCHER   ✓ /onecall-3 scraped (6,893 chars)
🕵️ RESEARCHER   Knowledge base built. 11 endpoints across 3 pages.
                  Auth: API key via ?appid= query param.
```

---

## 5. Scenario B — The Non-Linear Agentic Flow (DEFAULT)

This is not a fallback. This IS the system. Every job runs this way.

### Full Dynamic Flow Diagram

```
START — Chrome sends { url, language, page_content, page_links }
  │
  ▼
🧠 SUPERVISOR
  Reading: fresh job, no research yet
  Decision: route to Researcher
  Instruction: "Build complete knowledge base for SDK generation"
  │
  ▼
🕵️ RESEARCHER — Phase 1: LLM crawl plan
  → Sends landing page + 34 links to LLM
  → LLM selects 4 pages, skips 30
  → Emits crawl plan to SSE (users see every decision)
  Phase 2: Targeted scraping
  → Scrapes 4 selected pages only
  → Builds knowledge_base = { 11 endpoints, auth: api_key via ?appid= }
  Reports to Supervisor: "Knowledge base ready. 11 endpoints found."
  │
  ▼
🧠 SUPERVISOR
  Reading: knowledge_base present, no schema
  Decision: route to Architect
  Instruction: "Validate and structure the schema"
  │
  ▼
📐 ARCHITECT
  → Reads knowledge_base
  → Calls validate_schema tool
  → Finds: 2 GET endpoints incorrectly have request bodies
  → Auto-fixes: removes bodies, logs fixes
  Reports to Supervisor: "Schema clean. 2 auto-fixes applied."
  │
  ▼
🧠 SUPERVISOR
  Reading: api_schema present, no SDK
  Decision: route to Engineer
  Instruction: "Generate Python SDK from schema"
  │
  ▼
💻 ENGINEER
  → Reads api_schema
  → Generates client.py, models.py, tests/test_client.py, README.md
  → Calls syntax_check on each file internally
  → All pass
  Reports to Supervisor: "SDK written. 4 files. Syntax clean."
  │
  ▼
🧠 SUPERVISOR
  Reading: sdk_files present, no test results
  Decision: route to QA Tester
  Instruction: "Verify all 11 endpoints against the live API"
  │
  ▼
🧪 QA TESTER
  → Reads api_schema + sdk_files
  → Constructs test cases for all 11 endpoints
  → Calls execute_http_request for each

  Test  1: GET /weather?q=London&appid=KEY  → 200 ✓
  Test  2: GET /weather?q=London            → 401 ✗  (missing appid param)
  Test  3: GET /forecast?q=London&appid=KEY → 200 ✓
  ...

  Reports to Supervisor:
    "8/11 passed. FAIL: /weather call missing appid param in SDK code."
  │
  ▼
🧠 SUPERVISOR  ◄── THE WOW MOMENT
  Reading: QA failure — appid param missing from SDK call
  Decision: This is a code bug, not a docs gap — route to Engineer
  Instruction: "Fix client.py — appid query param not being appended
                to requests. Schema shows auth type: api_key via ?appid="
  │
  ▼
💻 ENGINEER (second visit)
  → Reads failure report + current client.py
  → Fixes: adds ?appid={self.api_key} to all request URLs
  → Syntax check passes
  Reports to Supervisor: "Fixed. appid param now appended to all requests."
  │
  ▼
🧠 SUPERVISOR
  Reading: fix applied, previous QA had 3 failures
  Decision: re-run QA
  │
  ▼
🧪 QA TESTER (second visit)
  → Re-tests all 11 endpoints
  → All 11 pass
  Reports to Supervisor: "11/11 endpoints verified. All passing."
  │
  ▼
🧠 SUPERVISOR
  Reading: all QA passing, no outstanding issues
  Decision: route to Packager
  │
  ▼
📦 PACKAGER (deterministic node)
  → Lints client.py with Black
  → Emits file_ready events (VS Code writes files in real time)
  → Generates narration via LLM call
  → Emits narrate event (TTS speaks in both extensions)
  │
  ▼
END
```

### What the User Sees in the Terminal — Full Annotated Log

```
🧠 SUPERVISOR    New job. Delegating research. Goal: Python SDK for OpenWeatherMap.
──────────────────────────────────────────────────────────────────────
🕵️ RESEARCHER   Landing page received (14,203 chars, 34 links)
🕵️ RESEARCHER   Asking LLM: which of these 34 pages are worth crawling?
🕵️ RESEARCHER   ✦ Crawl plan (4 selected):
🕵️ RESEARCHER     1. /appid          — Authentication details (PRIORITY 1)
🕵️ RESEARCHER     2. /current        — Current weather endpoint
🕵️ RESEARCHER     3. /forecast5      — Forecast endpoint
🕵️ RESEARCHER     4. /onecall-3      — One Call API
🕵️ RESEARCHER   ✗ Skipped 30 pages: /price, /faq, /blog, /migration...
🕵️ RESEARCHER   Scraping /appid...  ✓ (2,847 chars)
🕵️ RESEARCHER   Scraping /current... ✓ (5,102 chars)
🕵️ RESEARCHER   Scraping /forecast5... ✓ (4,371 chars)
🕵️ RESEARCHER   Scraping /onecall-3... ✓ (6,893 chars)
🕵️ RESEARCHER   Knowledge base complete: 11 endpoints, auth: api_key (?appid=)
──────────────────────────────────────────────────────────────────────
🧠 SUPERVISOR    Research complete. Schema next.
──────────────────────────────────────────────────────────────────────
📐 ARCHITECT    Validating schema...
📐 ARCHITECT    ⚠ Auto-fix 1: GET /weather had a request body — removed
📐 ARCHITECT    ⚠ Auto-fix 2: GET /onecall had a request body — removed
📐 ARCHITECT    Schema clean. 11 endpoints, 2 fixes applied.
──────────────────────────────────────────────────────────────────────
🧠 SUPERVISOR    Schema ready. Engineering the SDK.
──────────────────────────────────────────────────────────────────────
💻 ENGINEER     Writing client.py...
💻 ENGINEER     Writing models.py...
💻 ENGINEER     Writing tests/test_client.py...
💻 ENGINEER     Writing README.md...
💻 ENGINEER     Syntax check: all 4 files clean ✓
──────────────────────────────────────────────────────────────────────
🧠 SUPERVISOR    SDK ready. Sending to QA — verify live API.
──────────────────────────────────────────────────────────────────────
🧪 QA TESTER    Running live HTTP tests (11 endpoints)...
🧪 QA TESTER    ✓  GET  /weather?q=London&appid=KEY        → 200  (143ms)
🧪 QA TESTER    ✗  GET  /weather?q=London                  → 401  (missing appid)
🧪 QA TESTER    ✓  GET  /forecast?q=London&appid=KEY       → 200  (187ms)
🧪 QA TESTER    ✗  GET  /forecast?q=London                 → 401  (missing appid)
🧪 QA TESTER    ✗  GET  /onecall?lat=51.5&lon=-0.1         → 401  (missing appid)
🧪 QA TESTER    8/11 passed. 3 failures — appid param missing from SDK calls.
──────────────────────────────────────────────────────────────────────
🧠 SUPERVISOR    ⚡ QA FAILURE — Code bug: appid not appended to requests.
                 Routing back to Engineer (not Researcher — docs are fine).
──────────────────────────────────────────────────────────────────────
💻 ENGINEER     Reading failure report...
💻 ENGINEER     Fix: appending ?appid={self.api_key} to all request params
💻 ENGINEER     Syntax check: clean ✓
──────────────────────────────────────────────────────────────────────
🧠 SUPERVISOR    Fix applied. Re-running QA.
──────────────────────────────────────────────────────────────────────
🧪 QA TESTER    Re-testing all 11 endpoints...
🧪 QA TESTER    ✓  GET /weather?q=London&appid=KEY         → 200  (138ms)
🧪 QA TESTER    ✓  GET /forecast?q=London&appid=KEY        → 200  (191ms)
🧪 QA TESTER    ✓  GET /onecall?lat=51.5&lon=-0.1&appid=K  → 200  (204ms)
🧪 QA TESTER    ✓  11/11 endpoints verified against live API.
──────────────────────────────────────────────────────────────────────
🧠 SUPERVISOR    All tests passing. Sending to Packager.
──────────────────────────────────────────────────────────────────────
📦 PACKAGER     Formatting with Black...
📦 PACKAGER     ✓ client.py          → VS Code
📦 PACKAGER     ✓ models.py          → VS Code
📦 PACKAGER     ✓ tests/test_client.py → VS Code
📦 PACKAGER     ✓ README.md          → VS Code
🔊 NARRATING    "We built an 11-method Python SDK for the OpenWeatherMap API.
                 The QA agent caught a missing authentication parameter and the
                 squad corrected it autonomously. All 11 endpoints are verified."
```

---

## 6. All Agent Definitions & Tools

### 🧠 Supervisor Agent

Pure reasoning and routing. Does not call tools. Does not write code.

```python
async def supervisor_node(state: SDKJobState) -> SDKJobState:
    llm = ChatGoogleGenerativeAI(model="gemini-1.5-pro")

    state_summary = build_state_summary(state)  # compact JSON of what's done/failed

    response = await llm.ainvoke([
        SystemMessage(content=SUPERVISOR_PROMPT),
        HumanMessage(content=f"Current state:\n{state_summary}")
    ])

    decision = json.loads(response.content)

    emit_sse(state, "supervisor", decision["next_agent"],
             decision["reasoning"], decision["instruction"])

    return {
        **state,
        "next_agent": decision["next_agent"],
        "iteration_count": state["iteration_count"] + 1,
        "messages": [AIMessage(
            content=f"Routing to {decision['next_agent']}: {decision['instruction']}",
            name="supervisor"
        )]
    }
```

### 🕵️ Researcher Agent

Two tools: `scrape_web` and `select_pages_to_crawl`.

```python
@tool
async def scrape_web(url: str) -> dict:
    """
    Scrapes a single URL. Returns { url, content, char_count }.
    Uses pre-injected page_content from Chrome if URL matches landing page.
    Falls back to Playwright for all other URLs.
    Content is cleaned: strips nav/header/footer/script tags. Max 15,000 chars.
    """
    if url == state["target_url"] and len(state["page_content"]) > 300:
        return {
            "url": url,
            "content": state["page_content"],
            "source": "chrome_injection"
        }
    # Playwright scrape for sub-pages
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        await page.goto(url, timeout=15000)
        await page.wait_for_load_state("networkidle")
        content = await page.evaluate("""() => {
            // Remove noise elements
            ['nav','header','footer','script','style','.sidebar',
             '[role="banner"]','[role="navigation"]'].forEach(sel => {
                document.querySelectorAll(sel).forEach(el => el.remove());
            });
            return document.body.innerText;
        }""")
        await browser.close()
        return { "url": url, "content": content[:15000], "source": "playwright" }


@tool
async def select_pages_to_crawl(
    links: list[dict],
    landing_content: str,
    goal: str
) -> dict:
    """
    Sends landing page links to LLM for crawl plan selection.
    Returns { crawl_plan: [...], skipped: [...], notes: str }
    """
    llm = ChatGoogleGenerativeAI(model="gemini-1.5-flash")  # fast model for this
    response = await llm.ainvoke([
        SystemMessage(content=SELECT_PAGES_PROMPT),
        HumanMessage(content=f"""
GOAL: {goal}
LANDING PAGE CONTENT (first 3000 chars): {landing_content[:3000]}
AVAILABLE LINKS:
{json.dumps(links, indent=2)}
""")
    ])
    return json.loads(response.content)
```

### 📐 Architect Agent

One tool: `validate_schema`.

```python
@tool
def validate_schema(schema: dict) -> dict:
    """
    Validates API schema for logical consistency.
    Returns { valid, issues, fixed_schema, fixes_applied }

    Checks performed:
    - GET / DELETE endpoints must not have request_body
    - Path params in path string must exist in path_params array
    - All endpoints must have method, path, description
    - base_url must be a valid URL
    - auth.type must be one of: bearer, api_key, basic, none
    - No duplicate endpoint names
    - Path params in path string must match path_params list exactly
    """
    issues = []
    fixed = copy.deepcopy(schema)
    fixes = []

    for endpoint in fixed.get("endpoints", []):
        # GET/DELETE with body
        if endpoint["method"] in ["GET", "DELETE"] and endpoint.get("request_body"):
            issues.append(f"{endpoint['name']}: GET/DELETE has request_body")
            endpoint["request_body"] = None
            fixes.append(f"Removed request_body from {endpoint['name']}")

        # Path param mismatch
        path_params_in_path = re.findall(r'\{(\w+)\}', endpoint.get("path", ""))
        declared_params = [p["name"] for p in endpoint.get("path_params", [])]
        for p in path_params_in_path:
            if p not in declared_params:
                issues.append(f"{endpoint['name']}: path param {{{p}}} not in path_params")
                endpoint["path_params"].append({"name": p, "type": "string"})
                fixes.append(f"Added missing path_param '{p}' to {endpoint['name']}")

    return {
        "valid": len([i for i in issues if "CRITICAL" in i]) == 0,
        "issues": issues,
        "fixed_schema": fixed,
        "fixes_applied": fixes
    }
```

### 💻 Engineer Agent

One tool: `syntax_check`. Generates all SDK files in one LLM call.

```python
@tool
def syntax_check(code: str, language: str, filename: str) -> dict:
    """
    Validates syntax of generated code.
    Python:     ast.parse(code)
    TypeScript: writes to temp file, runs tsc --noEmit --strict

    Returns { valid, error, line, col }
    """
    if language == "python":
        try:
            ast.parse(code)
            return { "valid": True, "error": None }
        except SyntaxError as e:
            return { "valid": False, "error": str(e), "line": e.lineno }

    elif language == "typescript":
        with tempfile.NamedTemporaryFile(suffix=".ts", mode="w", delete=False) as f:
            f.write(code)
            tmp = f.name
        result = subprocess.run(
            ["tsc", "--noEmit", "--strict", "--target", "ES2020", tmp],
            capture_output=True, text=True, timeout=30
        )
        os.unlink(tmp)
        return {
            "valid": result.returncode == 0,
            "error": result.stderr if result.returncode != 0 else None
        }
```

The Engineer calls `syntax_check` on every generated file before reporting
to the Supervisor. If a file fails, the Engineer attempts one internal fix and
re-checks. Only after internal retry does it escalate to the Supervisor.

### 🧪 QA Tester Agent

One tool: `execute_http_request`. The most important agent for the demo.

```python
@tool
async def execute_http_request(
    method: str,
    url: str,
    headers: dict,
    params: dict | None,
    body: dict | None,
    expected_status: int,
    endpoint_name: str
) -> dict:
    """
    Makes a real HTTP call to a live API endpoint.

    Safety rules (hardcoded — not configurable via prompt):
    - Allowed methods: GET, POST only (no DELETE, PUT, PATCH in QA)
    - Timeout: 10 seconds
    - Max 15 requests per job total
    - No requests to private IP ranges (127.x, 192.168.x, 10.x)
    - User-Agent: "docs-to-code-qa/1.0"

    Returns {
        endpoint_name, method, url,
        status_code, response_body (first 500 chars),
        passed, error, latency_ms
    }
    """
    # Safety: block private IPs
    host = urlparse(url).hostname
    if is_private_ip(host):
        return { "passed": False, "error": "Private IP blocked", ... }

    start = time.time()
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.request(
                method, url, headers=headers,
                params=params, json=body,
                follow_redirects=True
            )
        latency = int((time.time() - start) * 1000)
        passed = response.status_code == expected_status
        return {
            "endpoint_name": endpoint_name,
            "method": method,
            "url": str(response.url),  # actual URL after params appended
            "status_code": response.status_code,
            "response_body": response.text[:500],
            "passed": passed,
            "error": None if passed else f"Expected {expected_status}, got {response.status_code}",
            "latency_ms": latency
        }
    except httpx.TimeoutException:
        return { "passed": False, "error": "Request timed out (10s)", ... }
    except Exception as e:
        return { "passed": False, "error": str(e), ... }
```

### 📦 Packager Node (deterministic)

Not an LLM agent. A reliable, fast Python function with one LLM call at the end.

```python
async def packager_node(state: SDKJobState) -> SDKJobState:
    final_files = {}

    for filename, content in state["sdk_files"].items():
        # Lint
        if filename.endswith(".py"):
            content = black.format_str(content, mode=black.Mode())
        # Emit file_ready event — VS Code writes file immediately on receipt
        emit_sse(state, "file_ready", filename=filename, content=content)
        final_files[filename] = content

    # Build ZIP fallback for Chrome-only users
    zip_bytes = build_zip(final_files)
    save_zip(state["job_id"], zip_bytes)

    # Generate narration
    summary = build_job_summary(state)
    narration = await generate_narration(summary)
    emit_sse(state, "narrate", text=narration)
    emit_sse(state, "complete", zip_url=f"/download/{state['job_id']}")

    return { **state, "final_files": final_files,
             "narration_text": narration, "status": "success" }
```

---

## 7. SSE Event Schema — Real-Time Narration

Every agent action emits one or more SSE events. This is what makes both
extensions feel alive.

```python
# ── Supervisor events ─────────────────────────────────────────────────────
{ "type": "supervisor",
  "routing_to": "engineer",
  "reasoning": "QA failed — code bug, not docs gap",
  "instruction": "Fix appid param in client.py" }

# ── Researcher events ─────────────────────────────────────────────────────
{ "type": "researcher_analysing", "link_count": 34 }
{ "type": "researcher_crawl_plan",
  "selected": [{ "url": "/appid", "reason": "Auth details", "priority": 1 }],
  "skipped_count": 30 }
{ "type": "researcher_scraping",  "url": "/appid", "reason": "Auth details" }
{ "type": "researcher_scraped",   "url": "/appid", "char_count": 2847 }
{ "type": "researcher_done",      "endpoint_count": 11, "page_count": 4 }
{ "type": "researcher_recrawl",   "reason": "Find auth docs — API key header wrong" }

# ── Architect events ──────────────────────────────────────────────────────
{ "type": "architect_validating" }
{ "type": "architect_fix",  "fix": "Removed request_body from get_weather" }
{ "type": "architect_done", "endpoint_count": 11, "fixes": 2 }

# ── Engineer events ───────────────────────────────────────────────────────
{ "type": "engineer_writing",  "filename": "client.py" }
{ "type": "engineer_syntax_ok","filename": "client.py" }
{ "type": "engineer_done",     "file_count": 4 }
{ "type": "engineer_fix",      "description": "Added appid param to all requests" }

# ── QA events ─────────────────────────────────────────────────────────────
{ "type": "qa_test",
  "endpoint": "GET /weather",
  "url": "https://api.openweathermap.org/data/2.5/weather?q=London&appid=KEY",
  "status": 200, "expected": 200, "passed": true, "latency_ms": 143 }
{ "type": "qa_test",
  "endpoint": "GET /weather",
  "url": "https://api.openweathermap.org/data/2.5/weather?q=London",
  "status": 401, "expected": 200, "passed": false,
  "error": "Expected 200, got 401" }
{ "type": "qa_done",
  "passed": 8, "failed": 3, "total": 11 }

# ── Reroute event (the wow) ───────────────────────────────────────────────
{ "type": "reroute",
  "from": "qa_tester",
  "to": "engineer",
  "reason": "appid param missing from SDK calls" }

# ── Delivery events ───────────────────────────────────────────────────────
{ "type": "file_ready",    "filename": "client.py",   "content": "..." }
{ "type": "install_cmd",   "cmd": "pip install requests" }
{ "type": "narrate",       "text": "We built an 11-method Python SDK..." }
{ "type": "complete",      "zip_url": "/download/abc123",
  "summary": { "endpoints": 11, "files": 4, "qa_rerouts": 1 } }

# ── Safety events ─────────────────────────────────────────────────────────
{ "type": "iteration",     "count": 3, "max": 15 }
{ "type": "safety_cutoff", "reason": "iteration_count exceeded 15" }
```

---

## 8. Chrome Extension

### What It Does

1. Reads the active tab URL + `document.body` content (no backend re-scraping needed)
2. Extracts structured link list — clean `[{ text, href, inNav }]` for LLM crawl selection
3. Sends both to the backend as `page_content` + `page_links`
4. Shows the full agent SSE stream in a popup terminal with colour-coded agents
5. Injects a collapsible overlay panel into the docs page itself
6. Bridges to VS Code via WebSocket or `vscode://` URI
7. Speaks narration aloud via Web Speech API

### Manifest v3

```json
{
  "manifest_version": 3,
  "name": "Docs to Code",
  "version": "1.0.0",
  "description": "Generate a typed SDK from any API docs. Delivered to VS Code.",
  "permissions": ["activeTab", "scripting", "storage", "tabs"],
  "host_permissions": ["http://localhost:8000/*"],
  "action": {
    "default_popup": "popup/popup.html",
    "default_icon": { "32": "icons/icon32.png" }
  },
  "content_scripts": [{
    "matches": ["<all_urls>"],
    "js": ["content/content.js"],
    "run_at": "document_idle"
  }],
  "background": { "service_worker": "background/background.js" }
}
```

### Popup Terminal UI

```
┌──────────────────────────────────────────────┐
│  ⚡ docs-to-code                    [?]  [⚙] │
├──────────────────────────────────────────────┤
│  openweathermap.org/api                       │  ← auto-filled
│  Language:  [Python ●]  [TypeScript]          │
│  Output:    [VS Code ●] [Download ZIP]        │
│  [▶  Generate SDK]                            │
├──────────────────────────────────────────────┤
│  🧠 SUPERVISOR    Delegating to Researcher    │  ← purple
│  🕵️ RESEARCHER   34 links found, asking LLM  │  ← blue
│  🕵️ RESEARCHER   ✦ 4 selected, 30 skipped    │
│  🕵️ RESEARCHER     1. /appid  (Auth)          │
│  🕵️ RESEARCHER     2. /current               │
│  🕵️ RESEARCHER   Scraping /appid... ✓         │
│  📐 ARCHITECT    ⚠ 2 auto-fixes applied      │  ← cyan
│  💻 ENGINEER     Syntax clean ✓               │  ← green
│  🧪 QA TESTER    ✗ GET /weather → 401        │  ← red
│  🧠 SUPERVISOR   ⚡ Rerouting → Engineer      │  ← amber flash
│  💻 ENGINEER     Fix applied: appid param     │
│  🧪 QA TESTER    ✓ 11/11 verified            │  ← green
│  📦 PACKAGER     ✓ 4 files → VS Code         │
│  🔊 Narrating...                              │
├──────────────────────────────────────────────┤
│  [🔊 Narrate: ON]         [↓ Download ZIP]   │
│  [Open in VS Code ↗]                         │
└──────────────────────────────────────────────┘
```

### Colour Coding for SSE Events

| Agent | Colour | Hex |
|---|---|---|
| Supervisor (normal) | Purple | `#a78bfa` |
| Supervisor (reroute) | Amber | `#fbbf24` |
| Researcher | Blue | `#60a5fa` |
| Architect | Cyan | `#34d399` |
| Engineer | Green | `#86efac` |
| QA Tester (pass) | Green | `#4ade80` |
| QA Tester (fail) | Red | `#f87171` |
| Packager | Slate | `#94a3b8` |

### content.js

```javascript
chrome.runtime.onMessage.addListener((msg, sender, respond) => {

  if (msg.type === "GET_PAGE_CONTENT") {
    respond({
      url: window.location.href,
      title: document.title,
      content: extractMainContent(),
      links: extractDocLinks()
    });
  }

  if (msg.type === "SHOW_OVERLAY") {
    injectOverlayPanel(msg.jobId);
  }

  if (msg.type === "UPDATE_OVERLAY") {
    updateOverlayPanel(msg.event);
  }
});

function extractMainContent() {
  const candidates = ['main', 'article', '[role="main"]',
                      '.content', '.docs-content', '.markdown-body', 'body'];
  for (const sel of candidates) {
    const el = document.querySelector(sel);
    if (el && el.innerText.trim().length > 500) {
      return el.innerText.trim().slice(0, 50000);
    }
  }
  return document.body.innerText.slice(0, 50000);
}

function extractDocLinks() {
  const seen = new Set();
  const links = [];
  document.querySelectorAll('a[href]').forEach(a => {
    const href = a.href;
    const text = a.innerText.trim();
    if (
      href.startsWith(window.location.origin) &&
      !href.includes('#') &&
      text.length >= 3 &&
      text.length <= 80 &&
      !seen.has(href)
    ) {
      seen.add(href);
      links.push({
        text,
        href,
        inNav: !!a.closest('nav, aside, [role="navigation"], .sidebar')
      });
    }
  });
  return links.slice(0, 100);  // cap at 100 links for LLM context
}
```

### Injected Overlay Panel (in-page sidebar)

```
(right edge of browser, always visible while on docs page)
┌──────────────────────────────┐
│ ⚡ docs-to-code    [—]  [×]  │
│──────────────────────────────│
│ 🕵️ 4 pages selected          │
│ 🕵️ Scraping...               │
│ 📐 Schema: 2 fixes           │
│ 🧪 ✗ /weather → 401          │
│ 🧠 ⚡ Rerouting → Engineer   │
│ 🧪 ✓ 11/11 verified          │
│ 📦 Sent to VS Code ✓         │
└──────────────────────────────┘
```

---

## 9. VS Code Extension

### What It Does

1. Receives `job_id` from Chrome via WebSocket or `vscode://` URI
2. Opens the Agent Panel Webview — mirrors same SSE stream with colour coding
3. Writes `file_ready` events directly to `{workspace}/src/sdk/`
4. Runs install command in integrated terminal automatically
5. Opens `client.py` / `client.ts` in editor on completion
6. Speaks narration through Webview Web Speech API
7. Shows History sidebar of past generations

### package.json (key fields)

```json
{
  "name": "docs-to-code",
  "displayName": "Docs to Code",
  "activationEvents": [
    "onUri",
    "onCommand:docs-to-code.generate",
    "onCommand:docs-to-code.resume",
    "onCommand:docs-to-code.history"
  ],
  "contributes": {
    "commands": [
      { "command": "docs-to-code.generate", "title": "Docs to Code: Generate SDK" },
      { "command": "docs-to-code.resume",   "title": "Docs to Code: Resume Job" },
      { "command": "docs-to-code.history",  "title": "Docs to Code: View History" }
    ],
    "viewsContainers": {
      "activitybar": [{ "id": "docs-to-code", "title": "Docs to Code", "icon": "media/icon.svg" }]
    },
    "views": {
      "docs-to-code": [{ "id": "historyView", "name": "Generation History" }]
    },
    "uriHandler": true
  }
}
```

### URI Handler

```typescript
// extension.ts
vscode.window.registerUriHandler({
  async handleUri(uri: vscode.Uri) {
    const params  = new URLSearchParams(uri.query);
    const jobId   = params.get('job_id')!;

    // 1. Open agent panel
    AgentPanel.createOrShow(context.extensionUri, jobId);

    // 2. Connect SSE stream
    const stream = new SSEClient(`http://localhost:8000/generate/stream?job_id=${jobId}`);

    // 3. Route all events to panel for display
    stream.on('*',           (e) => AgentPanel.postMessage(e));

    // 4. Act on delivery events
    stream.on('file_ready',  (e) => FileWriter.write(e.filename, e.content));
    stream.on('install_cmd', (e) => Installer.run(e.cmd));
    stream.on('narrate',     (e) => Narrator.speak(e.text));
    stream.on('complete',    ()  => Opener.openMainFile());
  }
});
```

### File Writer

```typescript
// fileWriter.ts
export class FileWriter {
  static async write(filename: string, content: string): Promise<void> {
    const workspace = vscode.workspace.workspaceFolders?.[0].uri;
    if (!workspace) {
      vscode.window.showErrorMessage('Docs to Code: Open a folder first');
      return;
    }
    const outputPath = vscode.Uri.joinPath(workspace, 'src', 'sdk', filename);
    // Create directories if needed
    await vscode.workspace.fs.createDirectory(
      vscode.Uri.joinPath(workspace, 'src', 'sdk', path.dirname(filename))
    );
    await vscode.workspace.fs.writeFile(
      outputPath,
      Buffer.from(content, 'utf-8')
    );
    // Show in file explorer
    vscode.commands.executeCommand('revealInExplorer', outputPath);
  }
}
```

### History Sidebar TreeView

```
DOCS TO CODE — HISTORY
├── OpenWeatherMap · Python · 2 min ago
│   ├── 11 endpoints · 4 files · 1 re-route
│   └── [Re-open files]  [Re-run]
├── JSONPlaceholder · TypeScript · 1 hr ago
│   ├── 9 endpoints · 4 files · 0 re-routes
│   └── [Re-open files]  [Re-run]
└── GitHub REST · Python · yesterday
    ├── 31 endpoints · 4 files · 2 re-routes
    └── [Re-open files]  [Re-run]
```

### Workspace Output Structure

```
{workspace}/
└── src/
    └── sdk/
        ├── client.py          ← opened in editor automatically
        ├── models.py
        ├── tests/
        │   └── test_client.py
        └── README.md
```

Post-delivery notification:
> **✓ SDK Ready** — 4 files in `src/sdk/` · 11 endpoints · all verified live

---

## 10. Read-Aloud Narration System

### What Gets Spoken

| Trigger | Spoken text |
|---|---|
| Job start | *"Starting SDK generation for [API name]."* |
| Crawl plan ready | *"Researcher selected [N] pages from [total] available. Skipping irrelevant content."* |
| QA failure + reroute | *"QA found a failure. Re-routing the squad."* |
| Fix confirmed | *"Engineer applied the fix. Re-running verification."* |
| All QA pass | *"All [N] endpoints verified against the live API."* |
| Job complete | Full 3-sentence narration (LLM-generated) |

### Chrome — Web Speech API

```javascript
// lib/tts.js
class TTSController {
  constructor() {
    this.enabled = true;
    this.synth   = window.speechSynthesis;
  }

  speak(text) {
    if (!this.enabled || !('speechSynthesis' in window)) return;
    this.synth.cancel();  // interrupt if already speaking
    const utt    = new SpeechSynthesisUtterance(text);
    utt.rate     = 1.05;
    utt.pitch    = 0.95;
    utt.voice    = this.synth.getVoices().find(v =>
      v.lang === 'en-GB' && v.name.includes('Google') ||
      v.name.includes('Daniel') ||
      v.name.includes('Alex')
    ) || this.synth.getVoices()[0];
    this.synth.speak(utt);
  }

  toggle() { this.enabled = !this.enabled; }
  stop()   { this.synth.cancel(); }
}
```

### VS Code — Webview postMessage Bridge

VS Code extension runtime has no TTS API. The Webview panel runs a hidden
speech iframe and receives messages from the extension:

```typescript
// narrator.ts
export class Narrator {
  static speak(text: string): void {
    AgentPanel.postMessage({ type: 'speak', text });
  }
}

// In panel.html (inside Webview)
window.addEventListener('message', (e) => {
  if (e.data.type === 'speak' && ttsEnabled) {
    window.speechSynthesis.cancel();
    const utt = new SpeechSynthesisUtterance(e.data.text);
    utt.rate  = 1.05;
    window.speechSynthesis.speak(utt);
  }
});
```

---

## 11. Cross-Extension Bridge Protocol

### Connection Detection & Sequence

```
1. Chrome popup opens
   └── background.js: WebSocket probe to ws://localhost:47291 (100ms timeout)
       ├── OPEN  → Show "● VS Code connected" green badge
       └── CLOSED → Show "○ VS Code not detected" with install hint

2. User clicks Generate
   └── content.js captures { url, page_content, page_links }
   └── popup.js: POST /generate/start → { job_id }
   └── popup.js: Opens SSE stream for job_id
   └── content.js: Injects overlay panel with job_id

3. Bridge fires (parallel, non-blocking)
   ├── WS open:    send { type:"new_job", job_id, url, language }
   │               VS Code opens panel, connects own SSE stream
   └── WS closed:  window.open("vscode://docs-to-code.extension/generate?job_id=...")
                   (VS Code comes to foreground, panel opens automatically)

4. Both extensions now streaming simultaneously from same job

5. file_ready events arrive from SSE
   └── VS Code FileWriter: writes file to workspace immediately
   └── Chrome log: "✓ client.py → VS Code"

6. complete event fires
   └── VS Code: opens client.py, runs install cmd in terminal
   └── Both: TTS speaks narration summary

FALLBACK: VS Code not open at all
   └── Chrome: copies job_id to clipboard
   └── Shows banner: "Job complete — open VS Code and run 'Resume Job'"
```

### WebSocket Message Schema

```typescript
type BridgeMessage =
  | { type: "new_job";      job_id: string; url: string; language: string }
  | { type: "ping" }
  | { type: "pong" }
  | { type: "vscode_ready"; workspace: string }
  | { type: "file_written"; filename: string }
  | { type: "port_info";    port: number }   // sent by VS Code if 47291 was taken
  | { type: "error";        message: string }
```

---

## 12. Repository Structure

```
docs-to-code/
│
├── backend/
│   ├── main.py                        # FastAPI app, CORS, routes
│   ├── job_manager.py                 # Job lifecycle, SSE queue, checkpoint I/O
│   │
│   ├── graph/
│   │   ├── state.py                   # SDKJobState TypedDict (single source of truth)
│   │   ├── graph.py                   # LangGraph StateGraph build + compile
│   │   ├── router.py                  # route_next() — safety overrides + LLM decision
│   │   └── runner.py                  # Async graph runner → pipes state.sse_events to SSE
│   │
│   ├── agents/
│   │   ├── supervisor.py              # Supervisor LLM node — reads state, routes
│   │   ├── researcher.py              # Researcher agent — Phase 1/2/3 crawl logic
│   │   ├── architect.py               # Architect agent — schema validation + fixes
│   │   ├── engineer.py                # Engineer agent — SDK generation + syntax check
│   │   ├── qa_tester.py               # QA Tester agent — live HTTP verification
│   │   └── packager.py                # Packager node — lint, emit files, narrate
│   │
│   ├── tools/
│   │   ├── scrape_web.py              # Playwright scraper tool
│   │   ├── select_pages.py            # LLM crawl planner tool
│   │   ├── validate_schema.py         # Schema logical validator tool
│   │   ├── syntax_check.py            # ast.parse / tsc syntax tool
│   │   └── execute_http.py            # Live HTTP request tool (safety rules enforced)
│   │
│   ├── prompts/
│   │   ├── supervisor.txt             # Routing logic + decision rules
│   │   ├── select_pages.txt           # Crawl plan selection
│   │   ├── researcher.txt             # Knowledge base building
│   │   ├── architect.txt              # Schema structuring
│   │   ├── engineer_python.txt        # Python SDK generation
│   │   ├── engineer_typescript.txt    # TypeScript SDK generation
│   │   ├── qa_tester.txt              # Test case construction
│   │   └── narrate.txt                # Completion narration
│   │
│   ├── jobs/                          # Runtime — one folder per job_id
│   │   └── .gitkeep
│   ├── requirements.txt
│   └── .env
│
├── chrome-extension/
│   ├── manifest.json
│   ├── popup/
│   │   ├── popup.html                 # 400×520 dark terminal UI
│   │   ├── popup.js                   # SSE consumer, bridge trigger, TTS control
│   │   └── popup.css
│   ├── content/
│   │   └── content.js                 # Page capture, link extraction, overlay injection
│   ├── background/
│   │   └── background.js              # WS probe, vscode:// URI open
│   └── lib/
│       ├── bridge.js                  # Chrome → VS Code bridge logic
│       ├── tts.js                     # Web Speech API wrapper
│       └── api.js                     # Backend HTTP helpers
│
├── vscode-extension/
│   ├── package.json
│   ├── tsconfig.json
│   └── src/
│       ├── extension.ts               # Activation, commands, URI handler
│       ├── bridge/
│       │   ├── uriHandler.ts          # vscode:// URI → open panel + stream
│       │   └── wsServer.ts            # Local WS server on port 47291
│       ├── panels/
│       │   └── AgentPanel.ts          # Webview with SSE terminal + colour coding
│       ├── injector/
│       │   ├── fileWriter.ts          # Writes file_ready events to workspace
│       │   ├── installer.ts           # Runs pip/npm install in integrated terminal
│       │   └── opener.ts              # Opens main client file in editor
│       ├── tts/
│       │   └── narrator.ts            # postMessage to Webview for TTS
│       └── memory/
│           └── historyView.ts         # TreeView of past jobs
│
├── examples/
│   ├── openweathermap_python/         # Pre-generated: client.py, models.py, tests/, README
│   ├── jsonplaceholder_typescript/    # Pre-generated TypeScript example
│   └── restcountries_python/
│
└── README.md
```

---

## 13. Team Roles & 24-Hour Timeline

### Team Split

| Member | Role | Owns |
|---|---|---|
| Dev 1 | Backend Lead | FastAPI, LangGraph graph, Supervisor agent, state design, SSE streaming, runner |
| Dev 2 | Researcher + QA | `select_pages` tool, Researcher agent (Phase 1/2/3), QA Tester agent, `execute_http` tool |
| Dev 3 | LLM / Prompts | All prompts, Architect agent, Engineer agent, Packager, narrate |
| Dev 4 | Extensions | Chrome extension, VS Code extension, bridge, TTS, file injector, overlay panel |

### Hour-by-Hour Schedule

```
00:00 – 01:30  │ SETUP
               │ • Monorepo init, .env confirmed, all keys tested
               │ • Dev 1: FastAPI + LangGraph installed, SDKJobState defined,
               │          /generate/start and /generate/stream endpoints stubbed
               │ • Dev 2: Playwright scrapes one test URL, select_pages tool
               │          returns valid JSON from Gemini for hardcoded links
               │ • Dev 3: Gemini responds to supervisor prompt with valid routing JSON,
               │          engineer prompt generates valid Python for a hardcoded schema
               │ • Dev 4: Chrome popup loads, content.js captures page + links,
               │          VS Code extension activates, WS server starts on 47291

01:30 – 06:00  │ AGENT BUILD (parallel — no integration yet)
               │
               │ Dev 1:
               │   • Full LangGraph graph with stub nodes wired
               │   • Supervisor routes between stubs based on state flags
               │   • SSE queue wired — state.sse_events stream to /generate/stream
               │   • iteration_count + safety cutoffs working
               │
               │ Dev 2:
               │   • Researcher agent: Phase 1 (select_pages) + Phase 2 (scrape)
               │     working end-to-end on jsonplaceholder.typicode.com
               │   • Researcher Phase 3 (re-crawl with targeted goal) working
               │   • QA Tester: execute_http tool tested on 3 real APIs
               │   • Safety rules in execute_http (private IP block, timeout) verified
               │
               │ Dev 3:
               │   • Architect agent: validate_schema catches all 6 issue types
               │   • Engineer agent: generates valid Python for JSONPlaceholder schema
               │   • Engineer agent: syntax_check catches and fixes common errors
               │   • Packager: emits file_ready events, narrate LLM call works
               │   • All prompts written and tested in isolation
               │
               │ Dev 4:
               │   • Chrome popup UI complete (renders mock SSE events with colours)
               │   • content.js link extraction tested on 5 real API doc sites
               │   • VS Code AgentPanel renders coloured agent events correctly
               │   • FileWriter writes mock file_ready events to temp workspace
               │   • Bridge: vscode:// URI opens panel in VS Code successfully

06:00 – 08:00  │ INTEGRATION CHECKPOINT 1
               │ Goal: Chrome click → Supervisor → Researcher (Phase 1+2) → schema saved
               │
               │ • Dev 1 + Dev 2: Researcher node wired into graph
               │   Verify: supervisor routes to researcher, researcher completes,
               │   supervisor reads knowledge_base and routes to architect
               │
               │ • Dev 4: Chrome popup connects to real SSE stream
               │   Verify: researcher_crawl_plan events render with selected/skipped pages
               │
               │ • Dev 1 + Dev 3: Architect + Engineer wired into graph
               │   Verify: full path to sdk_files in state

08:00 – 13:00  │ FULL SQUAD ONLINE
               │ Goal: Complete Scenario B — QA fails, re-routes, fixes, all pass
               │
               │ • Dev 2: QA Tester wired into graph, live HTTP tests firing
               │   Verify: qa_test SSE events show real status codes
               │
               │ • Dev 1: Supervisor re-routing logic tested
               │   Force-test: manually return wrong endpoint in Engineer, verify
               │   Supervisor routes to correct agent (Engineer not Researcher)
               │
               │ • Dev 1: iteration_count safety, qa_iteration safety tested
               │
               │ • Dev 4: vscode:// URI bridge working end-to-end
               │   Verify: Chrome click → VS Code panel opens → file_ready → files in workspace
               │
               │ • Dev 3: Narration LLM call generates good summaries for 3 test jobs

13:00 – 14:00  │ INTEGRATION CHECKPOINT 2
               │ Goal: Chrome click → full Scenario B → VS Code workspace has verified SDK
               │ • All 4 devs together
               │ • Verify the reroute event fires and is visible in both terminals
               │ • Verify QA shows real latency numbers and real status codes
               │ • Verify TTS speaks on narrate event in both extensions

14:00 – 18:00  │ POLISH + TYPESCRIPT
               │ • Dev 3: TypeScript Engineer prompt tested, tsc syntax_check working
               │   Full TypeScript path verified end-to-end
               │ • Dev 2: All 4 demo APIs tested in both languages, re-routes logged
               │   Document which APIs trigger natural Scenario B re-routes
               │ • Dev 4: Colour coding finalized, overlay panel polished,
               │          History sidebar populated from real jobs
               │ • Dev 1: Checkpoint resume tested (kill server, restart, job continues)

18:00 – 21:00  │ STRESS TEST
               │ • All 4 demo APIs × both languages = 8 full runs
               │ • Fix every failure found
               │ • Test all bridge fallbacks: WS → URI → clipboard
               │ • Test safety cutoffs: force >15 iterations, verify clean failure
               │ • Dev 4: final UI polish, popup mobile layout, loading states

21:00 – 23:00  │ DEMO PREP
               │ • Record screen: full Scenario B run with reroute visible
               │   Save as demo_backup.mp4
               │ • Write README.md
               │ • Pre-generate 3 examples → commit to /examples
               │ • Rehearse 2-minute demo script — time it twice

23:00 – 24:00  │ SUBMISSION BUFFER
               │ • Devpost form
               │ • Final bug fixes only — no new features
```

---

## 14. Prompt Engineering Reference

### `prompts/supervisor.txt`

```
You are the Supervisor of an SDK generation squad.
Your agents: researcher, architect, engineer, qa_tester, packager.

Read the full message history and current state summary carefully.
Identify exactly what has been completed, what is in progress, and what has failed.

ROUTING RULES (follow in order):
1. knowledge_base is None                    → researcher
   Instruction: "Build complete knowledge base for SDK generation"

2. api_schema is None                        → architect
   Instruction: "Validate and structure the schema from the knowledge base"

3. sdk_files is None                         → engineer
   Instruction: "Generate {language} SDK from the schema"

4. test_results is None                      → qa_tester
   Instruction: "Verify all endpoints against the live API"

5. test_results has failures:
   a. Failure looks like missing/wrong docs   → researcher
      Instruction: "Re-examine docs — specifically: {failure_detail}"
   b. Failure looks like a code bug           → engineer
      Instruction: "Fix sdk_files — specifically: {failure_detail}"

6. All test_results passed                   → packager
7. iteration_count > 15 OR qa_iteration > 3  → set status=failed, route to end
8. Same agent called 3+ times for same issue → set status=failed, route to end

Respond ONLY with this exact JSON. No preamble. No explanation.
{
  "next_agent": "<researcher|architect|engineer|qa_tester|packager|end>",
  "instruction": "<specific, actionable instruction for that agent>",
  "reasoning": "<one sentence: why this agent, why now>"
}

STATE SUMMARY:
{state_summary}
```

### `prompts/select_pages.txt`

```
You are an expert at reading API documentation site structure.

You will receive:
- A GOAL describing what we are trying to achieve
- The first 3000 characters of the landing page
- A list of all available links on the site

Your task: select which pages to crawl to achieve the GOAL.

Selection criteria:
- INCLUDE pages that likely contain: endpoint definitions, request/response schemas,
  authentication setup, API reference, parameter descriptions
- EXCLUDE pages that likely contain: pricing, blog posts, changelogs, FAQs,
  tutorials for specific frameworks, SDKs for other languages, legal pages

Prioritise auth/authentication pages FIRST — without correct auth info the
SDK will fail at runtime.

Return ONLY valid JSON. No markdown. No explanation.
{
  "crawl_plan": [
    {
      "url": "<full URL>",
      "reason": "<one sentence: what useful info this page likely contains>",
      "priority": <integer, 1 = highest>
    }
  ],
  "skipped": [
    { "url": "<full URL>", "reason": "<why not useful>" }
  ],
  "notes": "<anything unusual the researcher should know>"
}

GOAL: {goal}
LANDING PAGE (first 3000 chars): {landing_content}
AVAILABLE LINKS:
{links_json}
```

### `prompts/researcher.txt`

```
You are a Research Agent building a knowledge base for SDK generation.

You have two tools:
- scrape_web(url): scrapes a page and returns its text content
- select_pages_to_crawl(links, landing_content, goal): LLM crawl planner

Your workflow:
1. Use select_pages_to_crawl to get a prioritised crawl plan
2. Use scrape_web for each page in the plan, in priority order
3. Synthesise all scraped content into a structured knowledge_base

The knowledge_base must contain:
{
  "api_name": "<name of the API>",
  "base_url": "<base URL without trailing slash>",
  "auth": {
    "type": "bearer" | "api_key" | "basic" | "none",
    "location": "header" | "query_param" | "body",
    "key_name": "<header name or query param name>",
    "example": "<example value if shown in docs>"
  },
  "endpoints_raw": [
    {
      "name": "<descriptive name>",
      "method": "GET|POST|PUT|DELETE|PATCH",
      "path": "/path/with/{params}",
      "description": "<what this endpoint does>",
      "path_params": [{ "name": "...", "type": "...", "description": "..." }],
      "query_params": [{ "name": "...", "type": "...", "required": true|false }],
      "request_body_example": <object or null>,
      "response_example": <object or null>,
      "source_page": "<url this came from>"
    }
  ],
  "notes": "<anything unusual about this API>",
  "pages_crawled": ["<url1>", "<url2>"]
}

Be thorough. Do not skip endpoints. If two pages describe the same endpoint,
merge the information and keep the most complete version.
```

### `prompts/qa_tester.txt`

```
You are a QA Engineer. You have one tool: execute_http_request.

Your job is to verify that the generated SDK correctly represents the live API.

For each endpoint in the schema:
1. Construct the correct request (URL, method, headers, params)
2. Use safe test values for POST bodies
3. Call execute_http_request
4. Record the result

Safe POST test body: { "title": "test", "body": "test_body", "userId": 1 }
For endpoints requiring auth, use the api_key from the schema.
For endpoints requiring specific path params, use obviously safe values:
  - user IDs: 1
  - location: "London" or "51.5,-0.1"
  - date: "2024-01-01"

Report format for Supervisor:
{
  "passed": <count>,
  "failed": <count>,
  "total": <count>,
  "results": [ <TestResult per endpoint> ],
  "failure_summary": "<one paragraph: what failed and the likely root cause>"
}

SCHEMA: {schema_json}
SDK FILES: {sdk_files}
```

### `prompts/narrate.txt`

```
You are a calm, confident AI narrating what your squad just built.
Write exactly 2–3 spoken sentences.
First person plural ("We built...").
Be specific: API name, language, method count, test count.
If there were QA re-routes and autonomous fixes, mention this prominently —
it is the most impressive part.
No markdown. No filler phrases. End with something concrete about usefulness.

JOB SUMMARY: {job_summary_json}

Good example:
"We built a 9-method Python SDK for JSONPlaceholder.
Our QA agent caught an incorrect endpoint path and the squad corrected it
without any human intervention.
All 9 endpoints have been verified against the live API and are ready to use."

Bad example (too vague):
"The SDK has been successfully generated and is ready for you."
```

---

## 15. Edge Cases Master Registry

### Researcher / Crawling

| # | Scenario | Handling |
|---|---|---|
| R1 | LLM selects 0 pages from crawl plan | Fall back to scraping all navigation-level links (depth 1), max 5 |
| R2 | Selected page returns 404 | Skip, log in SSE, continue with other pages |
| R3 | Page requires login (redirects to /login) | Skip, emit `agent_warn`, note in knowledge_base |
| R4 | Page content < 200 chars after cleaning | Try raw `document.body.innerText`, otherwise skip |
| R5 | Landing page content from Chrome < 300 chars | Playwright-scrape the landing page too |
| R6 | Researcher Phase 3 re-crawl finds same pages already scraped | Skip already-crawled URLs, merge any new content found |
| R7 | All selected pages are the same domain but 403 | Emit clean error: "Documentation requires authentication" |
| R8 | Link list from Chrome has 0 entries | Researcher falls back to finding links in page_content via regex |

### Agent / Graph

| # | Scenario | Handling |
|---|---|---|
| A1 | Supervisor routes same agent 3x for same unresolved issue | status=failed, surface last error + last SDK state |
| A2 | iteration_count ≥ 15 | Force END, emit safety_cutoff event |
| A3 | qa_iteration ≥ 4 | Force END, "QA could not be resolved after 4 attempts" |
| A4 | Gemini rate limit hit | Exponential backoff ×3 (2s, 4s, 8s), then fail gracefully |
| A5 | Supervisor returns invalid JSON | Retry once with stricter prompt, then fail with last known routing |
| A6 | Engineer internal syntax retry fails twice | Escalate to Supervisor with error + code |
| A7 | QA Tester hits auth-gated endpoint | Mark as "untestable_auth_required", count as skip not failure |
| A8 | execute_http times out | Count as failed, include in failure report to Supervisor |

### Chrome Extension

| # | Scenario | Handling |
|---|---|---|
| C1 | VS Code bridge WS probe fails | Show install hint, show Download ZIP as primary CTA |
| C2 | Backend not running | "Start backend server" message + copy-paste command |
| C3 | Page content injection blocked by CSP | Graceful fallback message — backend Playwright scrapes |
| C4 | TTS `speechSynthesis` not available | Silently disable narrate toggle, no error shown to user |
| C5 | Popup closed mid-generation | Job continues on backend; reopen shows "Job in progress — [resume]" |
| C6 | Same URL submitted twice | Both create separate jobs — no deduplication in hackathon scope |

### VS Code Extension

| # | Scenario | Handling |
|---|---|---|
| V1 | No workspace folder open | Show "Open a folder first" with open-folder action button |
| V2 | src/sdk/ already exists | Dialog: "Overwrite existing SDK?" — yes/no |
| V3 | WS port 47291 in use | Try 47292, 47293 — send chosen port back to Chrome in bridge message |
| V4 | URI handler not triggered (VS Code closed) | Chrome copies job_id to clipboard + shows resume banner |
| V5 | Install command fails | Error shown in integrated terminal, suggest manual install |
| V6 | Webview CSP blocks speechSynthesis | Add `media-src 'self'` nonce, configure extension CSP header |

---

## 16. Environment Setup

### `backend/requirements.txt`

```
fastapi==0.111.0
uvicorn[standard]==0.29.0
langgraph==0.1.14
langchain==0.2.5
langchain-core==0.2.5
langchain-google-genai==1.0.6
playwright==1.44.0
beautifulsoup4==4.12.3
black==24.4.2
python-dotenv==1.0.1
pydantic==2.7.1
websockets==12.0
httpx==0.27.0
```

### `backend/.env`

```
GOOGLE_API_KEY=your_gemini_api_key_here
```

### `setup.sh`

```bash
#!/bin/bash
set -e
echo "=== Docs-to-Code Agentic Setup ==="

# Backend
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
playwright install chromium
mkdir -p jobs
echo "✓ Backend ready"

# VS Code extension
cd ../vscode-extension
npm install
npm run compile
echo "✓ VS Code extension compiled"

# Verify API key
cd ../backend
python -c "
from dotenv import load_dotenv; import os; load_dotenv()
k = os.environ.get('GOOGLE_API_KEY', '')
if k and k != 'your_gemini_api_key_here':
    print(f'✓ GOOGLE_API_KEY found ({k[:8]}...)')
else:
    print('✗ Set GOOGLE_API_KEY in backend/.env')
    exit(1)
"

echo ""
echo "┌─────────────────────────────────────────────────────┐"
echo "│  Start backend:                                     │"
echo "│  cd backend && source venv/bin/activate             │"
echo "│  uvicorn main:app --reload --port 8000              │"
echo "│                                                     │"
echo "│  Load Chrome extension:                             │"
echo "│  chrome://extensions → Load unpacked               │"
echo "│  → select chrome-extension/                        │"
echo "│                                                     │"
echo "│  Launch VS Code extension:                          │"
echo "│  cd vscode-extension → F5                          │"
echo "└─────────────────────────────────────────────────────┘"
```

---

## 17. Demo Day Playbook

### The 2-Minute Demo Script

```
[0:00] Chrome open on openweathermap.org/api
       "I'm on the OpenWeatherMap API docs. I click the extension."

[0:08] Popup opens. URL auto-filled. Python selected. Hit Generate.
       "The squad starts. Supervisor delegates to the Researcher."

[0:15] Point at the crawl plan in the popup terminal:
       "The Researcher asked the LLM which of these 34 pages are actually
        useful. It picked 4. It's skipping the pricing page, the blog,
        the migration guide. Only scraping what matters."

[0:30] Researcher scraping events fire one by one:
       "Scraping the auth page first — that's the priority. Then endpoints."

[0:45] Architect and Engineer events:
       "Schema validated — two auto-fixes. SDK written."

[1:00] QA Tester fires — the centrepiece:
       "QA is calling the live API right now. Watch..."
       ✗ event fires (red) — 401 Unauthorized
       "Got a 401. Missing the API key param."

[1:10] SUPERVISOR reroute event fires (amber):
       "Supervisor decided: this is a code bug, not a docs problem.
        Re-routing directly to Engineer — not wasting time re-scraping."

[1:20] Engineer fix + QA re-run:
       "Fix applied. QA re-running..."
       All green: "11/11 verified."

[1:35] VS Code comes to front. Files appear in workspace explorer.
       "No download. No ZIP. Straight into the project."
       Show IntelliSense on client methods.

[1:50] TTS speaks: "We built an 11-method Python SDK for OpenWeatherMap.
       Our QA agent caught a missing authentication parameter and corrected
       it autonomously. All 11 endpoints verified against the live API."
       "It even tells you what it built."
```

### The One Sentence Pitch

> "An AI squad that selectively reads only the relevant docs pages, writes a
> typed SDK, verifies it against the live API, fixes any bugs it finds
> autonomously, and delivers the result straight into your VS Code workspace."

### The Three Lines That Win the Room

When pointing at the terminal during the demo:

1. When crawl plan fires:
   *"The AI chose which pages to read — and which to ignore."*

2. When QA red event fires:
   *"That's a real HTTP 401 from the live OpenWeatherMap API."*

3. When reroute fires:
   *"No human told it what to do. The squad figured it out."*

### Backup Plan

- Pre-generated examples in `/examples` → show in VS Code directly
- Screen recording of full Scenario B saved as `demo_backup.mp4`
- If live HTTP QA fails due to network: show recording of the reroute moment
- If VS Code bridge fails: run `Docs to Code: Resume Job` with pre-known job_id

### APIs That Trigger Scenario B Naturally

| API | Natural Scenario B trigger | Notes |
|---|---|---|
| OpenWeatherMap | Missing `?appid=` param in requests | Reliable 401 → reroute |
| JSONPlaceholder | `/post` vs `/posts` path confusion | Reliable 404 → reroute |
| REST Countries | Field name casing in response schema | Good TypeScript demo |
| GitHub REST | Pagination headers, Accept header required | "Look what it handles" closer |

### What NOT to Demo Live

- GitHub full docs — 60s+, too slow for judges
- Any auth-gated API requiring real credentials
- TypeScript tsc validation — 15s, dead silence
- The clipboard fallback bridge — looks broken even when it works

---

*The pipeline tells you what it did. The squad tells you what it decided.* ⚡
