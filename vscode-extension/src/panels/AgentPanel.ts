/**
 * AgentPanel.ts — Docs to Code VS Code Extension
 * Dev 4: Webview panel — dark terminal, colour-coded agent rows, TTS toggle.
 */

import * as vscode from 'vscode';

const AGENT_COLOURS: Record<string, string> = {
  supervisor: '#a78bfa', reroute: '#fbbf24',
  researcher: '#60a5fa', researcher_analysing: '#60a5fa',
  researcher_crawl_plan: '#60a5fa', researcher_scraping: '#60a5fa',
  researcher_scraped: '#60a5fa', researcher_done: '#60a5fa',
  architect: '#34d399', architect_validating: '#34d399',
  architect_fix: '#34d399', architect_done: '#34d399',
  engineer: '#86efac', engineer_writing: '#86efac',
  engineer_file_done: '#86efac', engineer_syntax_error: '#f87171',
  qa_test_pass: '#4ade80', qa_test_fail: '#f87171', qa_done: '#4ade80',
  packager: '#94a3b8', file_ready: '#94a3b8',
  narrate: '#a78bfa', complete: '#4ade80',
  agent_warn: '#fbbf24', safety_cutoff: '#f87171',
};

export class AgentPanel {
  private static _panels: Map<string, AgentPanel> = new Map();

  private readonly _panel: vscode.WebviewPanel;
  private _disposables: vscode.Disposable[] = [];
  private _jobId: string;

  public static createOrShow(extensionUri: vscode.Uri, jobId: string): AgentPanel {
    const existing = AgentPanel._panels.get(jobId);
    if (existing) {
      existing._panel.reveal(vscode.ViewColumn.Beside);
      return existing;
    }
    const panel = vscode.window.createWebviewPanel(
      'docs-to-code.agentPanel',
      `⚡ SDK Gen · ${jobId.slice(0, 8)}`,
      vscode.ViewColumn.Beside,
      { enableScripts: true, retainContextWhenHidden: true }
    );
    const ap = new AgentPanel(panel, extensionUri, jobId);
    AgentPanel._panels.set(jobId, ap);
    return ap;
  }

  public static get(jobId: string): AgentPanel | undefined {
    return AgentPanel._panels.get(jobId);
  }

  private constructor(panel: vscode.WebviewPanel, _extensionUri: vscode.Uri, jobId: string) {
    this._panel = panel;
    this._jobId = jobId;
    this._panel.webview.html = this._getHtml();
    this._panel.webview.onDidReceiveMessage(
      (msg) => this._handleMsg(msg), null, this._disposables
    );
    this._panel.onDidDispose(() => this.dispose(), null, this._disposables);
  }

  public postEvent(event: Record<string, unknown>): void {
    this._panel.webview.postMessage({ type: 'sse_event', event });
  }

  public speak(text: string): void {
    this._panel.webview.postMessage({ type: 'speak', text });
  }

  public confirmFileWritten(filename: string): void {
    this._panel.webview.postMessage({
      type: 'sse_event',
      event: { type: 'file_written_confirm', filename },
    });
  }

  public dispose(): void {
    AgentPanel._panels.delete(this._jobId);
    this._panel.dispose();
    this._disposables.forEach((d) => d.dispose());
    this._disposables = [];
  }

  private _handleMsg(msg: { type: string }): void {
    if (msg.type === 'ready') {
      console.log(`[DocsToCode] Panel ready for job ${this._jobId}`);
    }
  }

  private _getHtml(): string {
    const colours = JSON.stringify(AGENT_COLOURS);
    return /* html */`<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8"/>
<meta http-equiv="Content-Security-Policy"
  content="default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; media-src *;"/>
<title>⚡ Docs to Code</title>
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#0d1117;--surf:#161b22;--over:#21262d;--brd:#30363d;
  --txt:#e6edf3;--muted:#8b949e;--accent:#a78bfa;
  --mono:'SF Mono','Cascadia Code',Consolas,monospace;
}
body{background:var(--bg);color:var(--txt);font-family:'Segoe UI',system-ui,sans-serif;
  font-size:12px;display:flex;flex-direction:column;height:100vh;overflow:hidden}
.ph{display:flex;align-items:center;justify-content:space-between;
  padding:10px 16px;background:var(--surf);border-bottom:1px solid var(--brd);flex-shrink:0}
.brand{font-family:var(--mono);font-size:13px;font-weight:700;color:var(--accent)}
.meta{font-size:10px;color:var(--muted);font-family:var(--mono)}
.tb{display:flex;align-items:center;justify-content:space-between;
  padding:6px 16px;background:var(--surf);border-bottom:1px solid var(--brd);flex-shrink:0}
.tbl{display:flex;align-items:center;gap:12px}
.nar{display:flex;align-items:center;gap:6px;font-size:11px;color:var(--muted);cursor:pointer;user-select:none}
.nar input{width:0;height:0;opacity:0;position:absolute}
.sl{position:relative;width:28px;height:16px;background:var(--over);border:1px solid var(--brd);border-radius:8px;transition:150ms}
.sl::after{content:'';position:absolute;top:2px;left:2px;width:10px;height:10px;border-radius:50%;background:var(--muted);transition:150ms}
.nar input:checked+.sl{background:rgba(167,139,250,.15);border-color:var(--accent)}
.nar input:checked+.sl::after{transform:translateX(12px);background:var(--accent)}
.pill{font-size:10px;font-family:var(--mono);color:var(--muted);background:var(--over);
  border:1px solid var(--brd);border-radius:12px;padding:2px 8px}
.pill b{color:var(--txt)}
.ibtn{background:none;border:none;color:var(--muted);cursor:pointer;font-size:11px;
  padding:3px 6px;border-radius:4px;transition:150ms}
.ibtn:hover{color:var(--txt);background:var(--over)}
.tw{flex:1;overflow:hidden;display:flex;flex-direction:column}
.th{display:flex;align-items:center;justify-content:space-between;
  padding:4px 16px;background:var(--surf);border-bottom:1px solid var(--brd);flex-shrink:0}
.tl{font-family:var(--mono);font-size:9px;color:var(--muted);text-transform:uppercase;letter-spacing:.8px}
.log{flex:1;overflow-y:auto;padding:10px 16px;display:flex;flex-direction:column;gap:1px;
  font-family:var(--mono);font-size:11px;line-height:1.65;border:2px solid transparent;transition:border-color .2s}
.log::-webkit-scrollbar{width:5px}
.log::-webkit-scrollbar-thumb{background:var(--brd);border-radius:3px}
@keyframes amber{0%,100%{border-color:transparent}35%,65%{border-color:#fbbf24;box-shadow:inset 0 0 8px rgba(251,191,36,.1)}}
.flash{animation:amber 2s ease}
.line{display:flex;align-items:flex-start;gap:8px;padding:1px 0;animation:li .12s ease}
@keyframes li{from{opacity:0;transform:translateX(-3px)}to{opacity:1;transform:translateX(0)}}
.bar{width:2px;min-height:14px;border-radius:1px;flex-shrink:0;margin-top:4px}
.txt{flex:1;word-break:break-word}
.ts{flex-shrink:0;color:var(--muted);font-size:9px;margin-top:3px;white-space:nowrap}
.placeholder{display:flex;flex-direction:column;align-items:center;justify-content:center;
  gap:10px;height:100%;color:var(--muted);text-align:center}
.bolt{font-size:32px;opacity:.25}
.fs{border-top:1px solid var(--brd);padding:8px 16px;max-height:110px;overflow-y:auto;flex-shrink:0}
.fl{font-size:9px;text-transform:uppercase;letter-spacing:.8px;color:var(--muted);margin-bottom:4px;font-family:var(--mono)}
.fe{display:flex;align-items:center;gap:6px;font-family:var(--mono);font-size:10px;color:#94a3b8;padding:2px 0;animation:li .15s ease}
.fc{color:#4ade80}
.fs.hidden{display:none}
</style></head>
<body>
<div class="ph"><div class="brand">⚡ docs-to-code</div><div class="meta" id="jm">initialising…</div></div>
<div class="tb">
  <div class="tbl">
    <label class="nar"><input type="checkbox" id="nt"/><span class="sl"></span>🔊 Narrate</label>
    <div class="pill">Endpoints <b id="se">—</b></div>
    <div class="pill">Re-routes <b id="sr">0</b></div>
  </div>
  <button class="ibtn" id="cb">✕ Clear</button>
</div>
<div class="tw">
  <div class="th"><span class="tl">agent log</span><span class="tl" id="lc">0 events</span></div>
  <div class="log" id="log" role="log" aria-live="polite">
    <div class="placeholder"><span class="bolt">⚡</span><span>Waiting for SDK generation events…</span></div>
  </div>
</div>
<div class="fs hidden" id="fs"><div class="fl">Written to workspace</div><div id="fl2"></div></div>

<script>
const C=${colours};
const log=document.getElementById('log');
const lc=document.getElementById('lc');
const se=document.getElementById('se');
const sr=document.getElementById('sr');
const jm=document.getElementById('jm');
const nt=document.getElementById('nt');
const fs=document.getElementById('fs');
const fl2=document.getElementById('fl2');
let n=0,rr=0,narOn=false;
const vscode=acquireVsCodeApi();

window.addEventListener('message',e=>{
  const m=e.data;
  if(!m)return;
  if(m.type==='sse_event')handle(m.event||{});
  if(m.type==='speak'&&narOn&&'speechSynthesis'in window){
    speechSynthesis.cancel();
    const u=new SpeechSynthesisUtterance(m.text||'');
    u.rate=1.05;u.pitch=0.95;speechSynthesis.speak(u);
  }
  if(m.type==='set_job_meta')jm.textContent='job: '+(m.jobId||'').slice(0,12)+'…';
});

function handle(ev){
  const t=ev.type||ev.event||'';
  const c=C[t]||'#8b949e';
  let txt='';
  switch(t){
    case 'supervisor': txt='🧠 [SUPERVISOR] → '+(ev.routing_to||'?')+' · '+(ev.reasoning||''); break;
    case 'reroute': rr++;sr.textContent=rr;txt='↩ [REROUTE] '+ev.from+' → '+ev.to+' · '+(ev.reason||'');flash(); break;
    case 'researcher_analysing': txt='🔍 [RESEARCHER] Analysing '+(ev.link_count||'?')+' links…'; break;
    case 'researcher_crawl_plan': txt='📋 [RESEARCHER] Plan: '+(ev.selected_count||0)+' selected · '+(ev.skipped_count||0)+' skipped'; break;
    case 'researcher_scraping': txt='🌐 [RESEARCHER] Scraping '+(ev.url||''); break;
    case 'researcher_scraped': txt='✓ [RESEARCHER] '+(ev.url||'')+' — '+Number(ev.char_count||0).toLocaleString()+' chars'; break;
    case 'researcher_done': txt='✓ [RESEARCHER] Done · '+(ev.endpoint_count||'?')+' endpoints'; if(ev.endpoint_count)se.textContent=ev.endpoint_count; break;
    case 'architect_validating': txt='🔬 [ARCHITECT] Validating schema…'; break;
    case 'architect_fix': txt='🔧 [ARCHITECT] Fix: '+(ev.fix||''); break;
    case 'architect_done': txt='✓ [ARCHITECT] Schema ready · '+(ev.endpoint_count||'?')+' endpoints · '+(ev.fixes_count||0)+' fixes'; if(ev.endpoint_count)se.textContent=ev.endpoint_count; break;
    case 'engineer_writing': txt='✍ [ENGINEER] Writing '+(ev.filename||'')+'…'; break;
    case 'engineer_file_done': txt='✓ [ENGINEER] '+(ev.filename||'')+' ('+(ev.line_count||'?')+' lines)'; break;
    case 'engineer_syntax_error': txt='✕ [ENGINEER] Syntax error in '+(ev.filename||'')+' — '+(ev.error||''); break;
    case 'qa_test_pass': txt='✓ [QA] '+(ev.endpoint||'')+' → '+(ev.status_code||200)+' ('+(ev.latency_ms||'?')+'ms)'; break;
    case 'qa_test_fail': txt='✕ [QA] '+(ev.endpoint||'')+' expected '+(ev.expected||'?')+' got '+(ev.actual||ev.status_code||'err'); break;
    case 'qa_done': txt='📊 [QA] '+(ev.passed||0)+'/'+(ev.total||0)+' passed'; break;
    case 'file_ready': txt='📁 [PACKAGER] '+(ev.filename||'')+' → writing to workspace…'; break;
    case 'file_written_confirm': txt='✓ [VS CODE] '+(ev.filename||'')+' written'; addFile(ev.filename||''); break;
    case 'narrate': txt='🔊 [NARRATE] '+(ev.text||''); break;
    case 'complete': txt='🎉 [COMPLETE] SDK generation successful!'; break;
    case 'agent_warn': txt='⚠ [WARN] '+(ev.message||''); break;
    case 'safety_cutoff': txt='⛔ [SAFETY] '+(ev.message||'Safety cutoff reached'); break;
    default: txt='['+t+'] '+(ev.message||JSON.stringify(ev).slice(0,120));
  }
  appendLine(txt,c);
}

function appendLine(txt,c){
  const p=log.querySelector('.placeholder');if(p)p.remove();
  const ln=document.createElement('div');ln.className='line';
  const b=document.createElement('div');b.className='bar';b.style.background=c;
  const t=document.createElement('div');t.className='txt';t.style.color=c;t.textContent=txt;
  const ts=document.createElement('div');ts.className='ts';
  ts.textContent=new Date().toLocaleTimeString('en-GB',{hour:'2-digit',minute:'2-digit',second:'2-digit'});
  ln.append(b,t,ts);log.appendChild(ln);log.scrollTop=log.scrollHeight;
  n++;lc.textContent=n+' event'+(n!==1?'s':'');
}

function addFile(f){
  fs.classList.remove('hidden');
  const e=document.createElement('div');e.className='fe';
  e.innerHTML='<span class="fc">✓</span>'+f;fl2.appendChild(e);
}

function flash(){
  log.classList.remove('flash');void log.offsetWidth;log.classList.add('flash');
  setTimeout(()=>log.classList.remove('flash'),2100);
}

nt.addEventListener('change',()=>{narOn=nt.checked;vscode.postMessage({type:'narrate_toggle',on:narOn});});
document.getElementById('cb').addEventListener('click',()=>{log.innerHTML='';n=0;lc.textContent='0 events';});
vscode.postMessage({type:'ready'});
</script></body></html>`;
  }
}
