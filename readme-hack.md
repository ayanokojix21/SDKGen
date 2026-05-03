# Docs-to-Code: AI-Powered Autonomous SDK Generation Pipeline

**Tagline:** Turn any API documentation into a fully functional, production-ready SDK with a single click—powered entirely by Google Gemma.

---

## 🛑 The Problem We Are Solving

In the modern API economy, companies spend hundreds of developer hours manually writing, maintaining, and updating SDKs (Software Development Kits) across multiple programming languages. For API consumers, the experience is equally frustrating: navigating dense, poorly structured documentation and manually writing boilerplate code to integrate an API is tedious, error-prone, and drastically slows down time-to-market.

Furthermore, documentation is often out-of-sync with the actual API behavior. When updates occur, SDKs break, leading to fragmented ecosystems and frustrated developers. The current process relies entirely on manual human effort to bridge the gap between human-readable documentation and machine-executable code.

## 🎯 Project Objective

Our objective is to completely automate the API integration lifecycle using state-of-the-art open weights models. We have built an autonomous, multi-agent AI pipeline that ingests any public API documentation URL and instantly generates, tests, and packages a functional SDK directly into the developer's IDE. 

By leveraging **Google Gemma** at the core of our orchestration, we ensure high-performance, secure, and context-aware code generation that scales effortlessly.

---

## 🧠 Powered by Google Gemma

The intelligence engine driving our entire multi-agent swarm is **Google Gemma**. Instead of relying on closed-source APIs, we utilized Gemma to achieve state-of-the-art reasoning and code-generation capabilities with maximum control and efficiency.

Here is how Gemma powers the pipeline:
- **Agentic Reasoning:** Gemma acts as the brain for each specialized node in our LangGraph architecture (Supervisor, Researcher, Architect, Engineer, and QA Tester).
- **Code Generation:** The Engineer agent utilizes Gemma to write robust, type-safe Python and TypeScript code by parsing the complex API schemas extracted from documentation.
- **Self-Correction Loops:** When the QA Tester agent detects a syntax error or a failing simulated HTTP request, Gemma analyzes the traceback and autonomously rewrites the code to fix the bug before the SDK is packaged.
- **Privacy & Security:** By using Gemma, developers can deploy this Docs-to-Code pipeline locally or within their own secure cloud infrastructure, ensuring proprietary API endpoints and internal documentation never leave their environment.

---

## 🚀 The Solution: Docs-to-Code

**Docs-to-Code** is an end-to-end ecosystem consisting of a Chrome Extension, an AI-powered Python Backend, and a VS Code Extension. 

Instead of reading docs, a developer simply navigates to an API documentation page, clicks "Generate SDK" in our Chrome Extension, and watches as the Gemma-powered swarm autonomously builds the SDK. 

### Key Features
1. **1-Click Browser Integration:** Start the process directly from the browser while reading API docs. No copy-pasting required.
2. **Gemma-Powered Multi-Agent Swarm (LangGraph):** 
   - **Researcher:** Scrapes and semantically understands the API documentation.
   - **Architect:** Designs the SDK schema, determining class structures and endpoint mappings using Gemma's strong structural reasoning.
   - **Engineer:** Writes the actual implementation code and data models.
   - **QA Tester:** Runs live syntax checks. If code fails, Gemma is prompted with the error log to iteratively fix it.
   - **Packager:** Bundles the finalized code into a ready-to-use library.
3. **Seamless IDE Injection:** A VS Code extension automatically listens for completed jobs via Server-Sent Events (SSE) and writes the generated SDK directly into the user's project files (`src/sdk/`).
4. **Context-Aware Voice Assistant:** Integrated **ElevenLabs Conversational AI** in the Chrome Extension. The voice agent instantly reads the current documentation page context, allowing developers to verbally ask questions about the API without leaving the page.
5. **Real-time SSE Streaming:** A beautiful terminal-style UI in the Chrome Extension that streams the exact thought processes and actions of the Gemma agents in real-time.

---

## 🏗️ Architecture & Tech Stack

- **Core LLM:** **Google Gemma** (handles all natural language understanding, code generation, and self-correction).
- **AI Orchestration:** LangGraph (Stateful Multi-Agent Workflows), LangChain.
- **Backend Core:** Python, FastAPI, asyncio, Server-Sent Events (SSE) via Pub/Sub architecture for multi-client broadcasting.
- **Browser Integration:** Chrome Extension (Manifest V3), Service Workers, Chrome Scripting API for DOM scraping.
- **IDE Integration:** VS Code Extension API (TypeScript), Custom URI Handlers for bridging the web and local workspace.
- **Voice & TTS:** ElevenLabs Conversational AI Web Component and API.

---

## 🔮 Future Scope

1. **Expanding Gemma's Capabilities:** Fine-tuning a specific Gemma model purely on API documentation and SDK repositories to create an ultra-specialized, highly efficient SDK generation model.
2. **Multi-Language Support:** Expand beyond Python and TypeScript to automatically generate SDKs for Go, Rust, Java, and Swift simultaneously.
3. **CI/CD Integration:** Create a GitHub App that monitors changes in API documentation repositories and automatically opens Pull Requests with updated SDK code using Gemma's diff-generation capabilities.
4. **Authentication Handling:** Advanced AI capability to securely handle complex OAuth 2.0 flows and API key handshakes automatically within the generated SDK.

---

## 🏆 Hackathon Pitch Points (Why this wins)

- **Highlights Google Gemma:** Showcases a highly practical, complex use-case for Gemma's reasoning and coding capabilities within an advanced multi-agent framework.
- **Massive Developer Impact:** Solves a universally hated problem (writing boilerplate API wrappers and reading dense docs). Every developer and judge understands this pain point immediately.
- **Complex AI Architecture:** We aren't just wrapping a single LLM prompt. We built a robust **Agentic Workflow** with loops, self-correction, and specialized roles driven by Gemma.
- **End-to-End Polish:** It bridges the web browser (Chrome Extension), the cloud (FastAPI AI swarm), and the local filesystem (VS Code Extension) seamlessly.
- **"Wow" Factor:** The real-time terminal UI streaming agent thoughts, combined with the ability to literally *talk* to the documentation page using ElevenLabs Voice AI, makes for a highly engaging and impressive live demo.
