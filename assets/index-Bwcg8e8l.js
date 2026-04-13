(function(){const a=document.createElement("link").relList;if(a&&a.supports&&a.supports("modulepreload"))return;for(const e of document.querySelectorAll('link[rel="modulepreload"]'))n(e);new MutationObserver(e=>{for(const i of e)if(i.type==="childList")for(const r of i.addedNodes)r.tagName==="LINK"&&r.rel==="modulepreload"&&n(r)}).observe(document,{childList:!0,subtree:!0});function s(e){const i={};return e.integrity&&(i.integrity=e.integrity),e.referrerPolicy&&(i.referrerPolicy=e.referrerPolicy),e.crossOrigin==="use-credentials"?i.credentials="include":e.crossOrigin==="anonymous"?i.credentials="omit":i.credentials="same-origin",i}function n(e){if(e.ep)return;e.ep=!0;const i=s(e);fetch(e.href,i)}})();let y=null;const O="/geometry-diagram-generator/";function b(t){return`${O}${t}`.replace(/\/\/+/g,"/")}async function x(){if(y)return y;try{y=(await fetch(b("data/runs.json"),{method:"HEAD"})).ok?"static":"live"}catch{y="live"}return y}async function V(){return await x()==="static"?(await fetch(b("data/runs.json"))).json():(await fetch("/api/runs")).json()}async function I(t){if(await x()==="static"){const n=await fetch(b(`data/runs/${t}/index.json`));return n.ok?{ok:!0,data:await n.json()}:{ok:!1}}const s=await fetch(`/api/runs/${t}`);return s.ok?{ok:!0,data:await s.json()}:{ok:!1}}async function A(t,a){if(await x()==="static"){const e=await fetch(b(`data/runs/${t}/records/${a}.json`));return e.ok?{ok:!0,data:await e.json()}:{ok:!1}}const n=await fetch(`/api/runs/${t}/records/${a}`);return n.ok?{ok:!0,data:await n.json()}:{ok:!1}}async function P(t,a){if(await x()==="static"){const e=await fetch(b(`data/runs/${t}/svg/${a}.svg`));return e.ok?e.text():null}const n=await fetch(`/api/runs/${t}/svg/${a}`);return n.ok?n.text():null}async function G(t){const a=await fetch("/api/compile-ir",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({diagram_ir:t})}),s=await a.json();return{ok:a.ok,data:s}}async function J(t){const a=await fetch("/api/render-tikz",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({tikz_code:t})}),s=await a.json();return{ok:a.ok,data:s}}function j(){return y==="static"}async function F(t,{navigate:a}){t.innerHTML='<p style="color:#888;padding:20px">Loading runs…</p>';let s;try{s=await V()}catch(e){t.innerHTML=`<p style="color:#f87171;padding:20px">Failed to load runs: ${e.message}</p>`;return}if(s.length===0){t.innerHTML='<p style="color:#888;padding:20px">No eval runs found in evals/results/.</p>';return}const n=`
    <h2>Eval Runs</h2>
    <table>
      <thead>
        <tr>
          <th>Run ID</th>
          <th>Records</th>
          <th>Strategies</th>
          <th>Pass</th>
          <th>Soft Pass</th>
          <th>Fail</th>
        </tr>
      </thead>
      <tbody>
        ${s.map(e=>{const i=e.gate_counts||{},r=i.pass||0,p=i.soft_pass||0,l=i.fail||0;return`
            <tr class="clickable" data-run="${e.run_id}">
              <td><a href="#/runs/${e.run_id}">${e.run_id}</a></td>
              <td>${e.record_count}</td>
              <td style="color:#aaa;font-size:12px">${(e.strategies||[]).join(", ")}</td>
              <td>${r>0?`<span class="badge badge-pass">${r}</span>`:'<span style="color:#555">—</span>'}</td>
              <td>${p>0?`<span class="badge badge-soft_pass">${p}</span>`:'<span style="color:#555">—</span>'}</td>
              <td>${l>0?`<span class="badge badge-fail">${l}</span>`:'<span style="color:#555">—</span>'}</td>
            </tr>
          `}).join("")}
      </tbody>
    </table>
  `;t.innerHTML=n,t.querySelectorAll("tr.clickable").forEach(e=>{e.addEventListener("click",i=>{i.target.tagName!=="A"&&a(`#/runs/${e.dataset.run}`)})})}function R(t){return`<span class="badge ${t?`badge-${t}`:"badge-null"}">${t||"unknown"}</span>`}async function Z(t,{runId:a,navigate:s}){t.innerHTML='<p style="color:#888;padding:20px">Loading…</p>';let n;try{const l=await I(a);if(!l.ok){t.innerHTML='<p style="color:#f87171;padding:20px">Run not found.</p>';return}n=l.data}catch(l){t.innerHTML=`<p style="color:#f87171;padding:20px">Failed to load: ${l.message}</p>`;return}const e=[...new Set(n.map(l=>l.strategy).filter(Boolean))].sort(),i=["pass","soft_pass","fail"];function r(l,u,o){let c=n;if(l&&(c=c.filter(d=>d.strategy===l)),u&&(c=c.filter(d=>d.gate_status===u)),o){const d=o.toLowerCase();c=c.filter(f=>(f.scenario_id||"").toLowerCase().includes(d))}const g=c.map((d,f)=>{const M=n.indexOf(d),H=d.duration_s!=null?d.duration_s.toFixed(1)+"s":"—",C=d.llm_judge_score!=null?d.llm_judge_score:"—",N=d.visual_judge_score!=null?d.visual_judge_score:"—",q=d.diagram_ir!=null?'<span title="IR available" style="color:#86efac">●</span>':'<span title="No IR" style="color:#555">○</span>',D=(d.gate_failures||[]).slice(0,3).join(", ");return`
        <tr class="clickable" data-idx="${M}">
          <td>${d.scenario_id||"—"}</td>
          <td style="color:#aaa;font-size:12px">${d.strategy||"—"}</td>
          <td style="color:#888">${d.repeat_index??"—"}</td>
          <td>${R(d.gate_status)}</td>
          <td style="color:#888;font-size:11px">${D||""}</td>
          <td style="color:#aaa">${C}</td>
          <td style="color:#aaa">${N}</td>
          <td style="color:#888">${H}</td>
          <td style="text-align:center">${q}</td>
        </tr>
      `}).join("");document.getElementById("run-tbody").innerHTML=g||'<tr><td colspan="9" style="color:#888;padding:20px;text-align:center">No records match filters.</td></tr>',document.querySelectorAll("#run-tbody tr.clickable").forEach(d=>{d.addEventListener("click",()=>s(`#/runs/${a}/records/${d.dataset.idx}`))})}t.innerHTML=`
    <h2>Run: ${a} <span style="font-size:14px;color:#888;font-weight:400">(${n.length} records)</span></h2>
    <div class="filters">
      <label>Strategy
        <select id="filter-strategy">
          <option value="">All</option>
          ${e.map(l=>`<option value="${l}">${l}</option>`).join("")}
        </select>
      </label>
      <label>Gate
        <select id="filter-gate">
          <option value="">All</option>
          ${i.map(l=>`<option value="${l}">${l}</option>`).join("")}
        </select>
      </label>
      <label>Scenario
        <input id="filter-scenario" type="text" placeholder="Search…" style="width:160px" />
      </label>
    </div>
    <table>
      <thead>
        <tr>
          <th>Scenario</th>
          <th>Strategy</th>
          <th>#</th>
          <th>Gate</th>
          <th>Failures</th>
          <th>LLM Judge</th>
          <th>Visual Judge</th>
          <th>Duration</th>
          <th title="IR available">IR</th>
        </tr>
      </thead>
      <tbody id="run-tbody"></tbody>
    </table>
  `,r("","",""),document.getElementById("filter-strategy").addEventListener("change",l=>{r(l.target.value,document.getElementById("filter-gate").value,document.getElementById("filter-scenario").value)}),document.getElementById("filter-gate").addEventListener("change",l=>{r(document.getElementById("filter-strategy").value,l.target.value,document.getElementById("filter-scenario").value)});let p;document.getElementById("filter-scenario").addEventListener("input",l=>{clearTimeout(p),p=setTimeout(()=>{r(document.getElementById("filter-strategy").value,document.getElementById("filter-gate").value,l.target.value)},150)})}function K(t,a){const s=t.split(`
`),n=a.split(`
`),e=s.length,i=n.length,r=Array.from({length:e+1},()=>new Int32Array(i+1));for(let o=e-1;o>=0;o--)for(let c=i-1;c>=0;c--)s[o]===n[c]?r[o][c]=r[o+1][c+1]+1:r[o][c]=Math.max(r[o+1][c],r[o][c+1]);const p=[];let l=0,u=0;for(;l<e||u<i;)l<e&&u<i&&s[l]===n[u]?(p.push({type:"equal",line:s[l]}),l++,u++):u<i&&(l>=e||r[l][u+1]>=r[l+1][u])?(p.push({type:"add",line:n[u]}),u++):(p.push({type:"remove",line:s[l]}),l++);return p}function z(t,a,s=3){const n=K(t,a);if(n.every(o=>o.type==="equal"))return'<div style="color:#888;font-size:12px;padding:8px">No changes.</div>';const e=new Set;n.forEach((o,c)=>{o.type!=="equal"&&e.add(c)});const i=new Set;e.forEach(o=>{for(let c=Math.max(0,o-s);c<=Math.min(n.length-1,o+s);c++)i.add(c)});let r=1,p=1;const l=[];let u=!0;return n.forEach((o,c)=>{const g=i.has(c);if(!g&&u&&l.push('<div class="diff-line-hunk">···</div>'),u=g,!g){o.type!=="add"&&r++,o.type!=="remove"&&p++;return}const d=W(o.line);o.type==="equal"?(l.push(`<div class="diff-line diff-line-equal"><span class="diff-gutter">${r}</span><span class="diff-gutter">${p}</span><span class="diff-prefix"> </span><span class="diff-content">${d}</span></div>`),r++,p++):o.type==="add"?(l.push(`<div class="diff-line diff-line-add"><span class="diff-gutter"> </span><span class="diff-gutter">${p}</span><span class="diff-prefix">+</span><span class="diff-content">${d}</span></div>`),p++):(l.push(`<div class="diff-line diff-line-remove"><span class="diff-gutter">${r}</span><span class="diff-gutter"> </span><span class="diff-prefix">-</span><span class="diff-content">${d}</span></div>`),r++)}),`<div class="diff-view">${l.join("")}</div>`}function W(t){return t.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;")}async function Q(t,{runId:a,index:s,navigate:n}){t.innerHTML='<p style="color:#888;padding:20px">Loading…</p>';let e,i;try{const[o,c]=await Promise.all([A(a,s),I(a)]);if(!o.ok){t.innerHTML='<p style="color:#f87171;padding:20px">Record not found.</p>';return}e=o.data,i=c.data.length}catch(o){t.innerHTML=`<p style="color:#f87171;padding:20px">Failed to load: ${o.message}</p>`;return}const r=e.diagram_ir!=null,p=r?JSON.stringify(e.diagram_ir,null,2):"",l=e.tikz_code||"";if(t.innerHTML=`
    <div class="record-nav">
      ${s>0?`<a href="#/runs/${a}/records/${s-1}" class="btn btn-primary" style="padding:4px 12px;font-size:12px">← Prev</a>`:""}
      <span class="nav-info">Record ${s+1} of ${i}</span>
      ${s<i-1?`<a href="#/runs/${a}/records/${s+1}" class="btn btn-primary" style="padding:4px 12px;font-size:12px">Next →</a>`:""}
    </div>

    <div class="record-layout">
      <!-- Left: metadata + editors -->
      <div>
        <!-- Metadata -->
        <div class="panel" style="margin-bottom:16px">
          <div class="panel-header">
            ${e.scenario_id||"—"}
            <span style="margin-left:8px;font-size:11px;color:#888">${e.benchmark||""}${e.tier!=null?` · tier ${e.tier}`:""}${(e.tags||[]).length?` · ${e.tags.join(", ")}`:""}</span>
            <span style="margin-left:auto">${R(e.gate_status)}</span>
          </div>
          <div class="panel-body">
            <div class="meta-grid" style="margin-bottom:12px">
              <span class="meta-key">Strategy</span><span class="meta-val">${e.strategy||"—"}</span>
              <span class="meta-key">Model</span><span class="meta-val">${e.model||"—"}</span>
              <span class="meta-key">Repeat</span><span class="meta-val">${e.repeat_index??"—"}</span>
              <span class="meta-key">Timestamp</span><span class="meta-val" style="font-size:12px">${e.timestamp?new Date(e.timestamp).toLocaleString():"—"}</span>
              <span class="meta-key">Duration</span><span class="meta-val">${e.duration_s!=null?e.duration_s.toFixed(2)+"s":"—"}</span>
              ${e.input_tokens!=null?`<span class="meta-key">Tokens</span><span class="meta-val">${e.input_tokens.toLocaleString()} in / ${(e.output_tokens??0).toLocaleString()} out</span>`:""}
              ${e.tool_calls>0?`<span class="meta-key">Tool calls</span><span class="meta-val">${e.tool_calls}${e.retries>0?` (${e.retries} retr${e.retries===1?"y":"ies"})`:""}</span>`:""}
              <span class="meta-key">Generated</span><span class="meta-val">${k(e.generation_success)} SVG: ${k(e.svg_rendered)} Checks: ${k(e.deterministic_pass)}</span>
              <span class="meta-key">Gate failures</span><span class="meta-val" style="color:#fca5a5">${(e.gate_failures||[]).join(", ")||"none"}</span>
              ${e.error?`<span class="meta-key">Error</span><span class="meta-val" style="color:#fca5a5;font-size:12px">${m(e.error)}</span>`:""}
            </div>
            <div class="prompt-text">${m(e.user_prompt||"")}</div>
          </div>
        </div>

        <!-- Judge scores -->
        ${ee(e)}

        <!-- Editors -->
        <div class="panel">
          <div class="tabs">
            ${r?'<button class="tab-btn active" data-tab="ir">Edit IR</button>':""}
            <button class="tab-btn ${r?"":"active"}" data-tab="tikz">Edit TikZ</button>
          </div>

          ${r?`
          <div class="tab-pane active" id="tab-ir">
            <textarea id="ir-editor" class="code-editor" style="min-height:360px">${m(p)}</textarea>
            <div style="margin-top:10px;display:flex;align-items:center;gap:10px;flex-wrap:wrap">
              <button class="btn btn-primary" id="btn-compile">Recompile &amp; Render</button>
              <button class="btn" id="btn-ir-diff" style="background:#2a2a2a;color:#ccc">Show Diff</button>
              <span id="compile-spinner" style="display:none"><span class="spinner"></span></span>
            </div>
            <div id="compile-error" style="display:none"></div>
            <div id="ir-diff-container" style="display:none"></div>
          </div>
          `:""}

          <div class="tab-pane ${r?"":"active"}" id="tab-tikz">
            <textarea id="tikz-editor" class="code-editor" style="min-height:360px">${m(l)}</textarea>
            <div style="margin-top:10px;display:flex;align-items:center;gap:10px;flex-wrap:wrap">
              <button class="btn btn-primary" id="btn-render">Re-render</button>
              <button class="btn" id="btn-tikz-diff" style="background:#2a2a2a;color:#ccc">Show Diff</button>
              <span id="render-spinner" style="display:none"><span class="spinner"></span></span>
            </div>
            <div id="render-error" style="display:none"></div>
            <div id="tikz-diff-container" style="display:none"></div>
          </div>
        </div>
      </div>

      <!-- Right: SVG preview + checks -->
      <div>
        <div class="panel" style="margin-bottom:16px">
          <div class="panel-header">
            SVG Preview
            <span id="svg-source-label" style="margin-left:auto;font-size:11px;color:#888;font-weight:400"></span>
          </div>
          <div class="panel-body">
            <div class="svg-preview" id="svg-container">
              <span class="svg-placeholder">Loading…</span>
            </div>
          </div>
        </div>

        <div class="panel">
          <div class="panel-header">Check Results</div>
          <div class="panel-body">
            <div id="checks-container">${X(e)}</div>
          </div>
        </div>
      </div>
    </div>
  `,e.svg_path?U(a,s):(document.getElementById("svg-container").innerHTML='<span class="svg-placeholder">No SVG available</span>',document.getElementById("svg-source-label").textContent="no SVG saved"),t.querySelectorAll(".tab-btn").forEach(o=>{o.addEventListener("click",()=>{t.querySelectorAll(".tab-btn").forEach(c=>c.classList.remove("active")),t.querySelectorAll(".tab-pane").forEach(c=>c.classList.remove("active")),o.classList.add("active"),document.getElementById(`tab-${o.dataset.tab}`).classList.add("active")})}),S("btn-ir-diff","ir-diff-container",()=>[p,document.getElementById("ir-editor").value]),S("btn-tikz-diff","tikz-diff-container",()=>[l,document.getElementById("tikz-editor").value]),r){const o=document.getElementById("btn-compile");j()&&(o.disabled=!0,o.title="Recompile requires the eval viewer backend"),o.addEventListener("click",async()=>{const c=document.getElementById("compile-spinner"),g=document.getElementById("compile-error");o.disabled=!0,c.style.display="inline",g.style.display="none";let d;try{d=JSON.parse(document.getElementById("ir-editor").value)}catch(f){h(g,`JSON parse error: ${f.message}`),o.disabled=!1,c.style.display="none";return}try{const f=await G(d);f.ok?(document.getElementById("tikz-editor").value=f.data.tikz_code||"",L(f.data.svg,"recompiled from IR"),document.getElementById("checks-container").innerHTML=Y(f.data.checks||[]),B("ir-diff-container",p,document.getElementById("ir-editor").value),B("tikz-diff-container",l,f.data.tikz_code||"")):h(g,f.data.error||"Compilation failed")}catch(f){h(g,`Request failed: ${f.message}`)}o.disabled=!1,c.style.display="none"})}const u=document.getElementById("btn-render");j()&&(u.disabled=!0,u.title="Re-render requires the eval viewer backend"),u.addEventListener("click",async()=>{const o=document.getElementById("render-spinner"),c=document.getElementById("render-error");u.disabled=!0,o.style.display="inline",c.style.display="none";const g=document.getElementById("tikz-editor").value;try{const d=await J(g);d.ok?L(d.data.svg,"re-rendered from TikZ"):h(c,d.data.error||"Render failed")}catch(d){h(c,`Request failed: ${d.message}`)}u.disabled=!1,o.style.display="none"})}function S(t,a,s){const n=document.getElementById(t),e=document.getElementById(a);if(!n||!e)return;let i=!1;n.addEventListener("click",()=>{if(i=!i,i){const[r,p]=s();e.innerHTML=z(r,p),e.style.display="block",n.textContent="Hide Diff",n.style.color="#60a5fa"}else e.style.display="none",n.textContent="Show Diff",n.style.color="#ccc"})}function B(t,a,s){const n=document.getElementById(t);n&&n.style.display!=="none"&&(n.innerHTML=z(a,s))}async function U(t,a){const s=document.getElementById("svg-container"),n=document.getElementById("svg-source-label");try{const e=await P(t,a);if(!e)throw new Error("not found");L(e,"saved SVG")}catch{s.innerHTML='<span class="svg-placeholder">SVG file not available</span>',n.textContent="file missing"}}function L(t,a){const s=document.getElementById("svg-container"),n=document.getElementById("svg-source-label");if(!t){s.innerHTML='<span class="svg-placeholder">No SVG</span>';return}s.innerHTML=t;const e=s.querySelector("svg");e&&(e.style.maxWidth="100%",e.style.height="auto"),n&&(n.textContent=a||"")}function h(t,a){t.className="error-box",t.textContent=a,t.style.display="block"}function X(t){const a=[];if(t.tikz_checks){const s=Object.entries(t.tikz_checks).map(([n,e])=>{if(typeof e!="object")return null;const i=e.type?`${n} <span style="color:#555;font-size:11px">${e.type}</span>`:n;return $(i,e.passed,e.skipped,e.error||"",!0)}).filter(Boolean);s.length&&a.push(`<h3>TikZ Checks</h3><div class="check-list">${s.join("")}</div>`)}if(t.svg_checks){const s=t.svg_checks.failures||[];a.push(`<h3 style="margin-top:12px">SVG Checks</h3><div class="check-list">${$("svg",t.svg_checks.passed,!1,s.join(", "))}</div>`)}if(t.expected_point_checks){const s=t.expected_point_checks,n=[];if(s.missing&&s.missing.length&&n.push(`missing: ${s.missing.join(", ")}`),s.mismatches)for(const[i,r]of Object.entries(s.mismatches))n.push(`${i}: expected (${r.expected}), got (${r.actual}), err=${r.error?.toFixed(4)}`);const e=n.join("; ");a.push(`<h3 style="margin-top:12px">Point Checks</h3><div class="check-list">${$("expected points",s.passed,!1,e)}</div>`)}return a.length?a.join(""):'<p style="color:#888;font-size:12px">No checks available.</p>'}function Y(t){return t.length?`<h3>IR Checks</h3><div class="check-list">${t.map(s=>$(s.check?.kind||"check",s.passed,!1,s.message||"")).join("")}</div>`:'<p style="color:#888;font-size:12px">No checks.</p>'}function $(t,a,s,n,e=!1){const i=s?"skip":a?"pass":"fail",r=s?"⊘":a?"✓":"✗",p=e?t:m(String(t));return`
    <div class="check-item ${i}">
      <span class="check-icon">${r}</span>
      <div>
        <div class="check-name">${p}</div>
        ${n?`<div class="check-msg">${m(String(n))}</div>`:""}
      </div>
    </div>
  `}function k(t){return t===!0?'<span style="color:#86efac">✓</span>':t===!1?'<span style="color:#fca5a5">✗</span>':'<span style="color:#555">—</span>'}function ee(t){const a=t.llm_judge_score!=null,s=t.visual_judge_score!=null;if(!a&&!s)return"";const n=t.llm_judge_details||{},e=["geometric_accuracy","labeling","completeness","likely_renders"];return`
    <div class="panel" style="margin-bottom:16px">
      <div class="panel-header">Judge Scores</div>
      <div class="panel-body">
        ${a?`
          <div style="margin-bottom:10px">
            <div style="display:flex;align-items:center;gap:12px;margin-bottom:6px">
              <span style="font-weight:600;font-size:13px;color:#ccc">LLM Judge</span>
              <span style="font-size:18px;font-weight:700;color:${_(t.llm_judge_score)}">${t.llm_judge_score}/5</span>
            </div>
            ${e.filter(i=>n[i]!=null).length?`
              <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:8px">
                ${e.filter(i=>n[i]!=null).map(i=>`
                  <span style="background:#1a1a1a;border:1px solid #333;border-radius:4px;padding:2px 8px;font-size:11px">
                    <span style="color:#888">${i.replace(/_/g," ")}</span>
                    <span style="color:${_(n[i])};font-weight:600;margin-left:4px">${n[i]}</span>
                  </span>
                `).join("")}
              </div>
            `:""}
            ${t.llm_judge_reasoning?`<div style="font-size:12px;color:#aaa;line-height:1.5;border-left:2px solid #333;padding-left:10px">${m(t.llm_judge_reasoning)}</div>`:""}
          </div>
        `:""}
        ${s?`
          <div ${a?'style="border-top:1px solid #222;padding-top:10px"':""}>
            <div style="display:flex;align-items:center;gap:12px;margin-bottom:6px">
              <span style="font-weight:600;font-size:13px;color:#ccc">Visual Judge</span>
              <span style="font-size:18px;font-weight:700;color:${_(t.visual_judge_score)}">${t.visual_judge_score}/5</span>
            </div>
            ${t.visual_judge_reasoning?`<div style="font-size:12px;color:#aaa;line-height:1.5;border-left:2px solid #333;padding-left:10px">${m(t.visual_judge_reasoning)}</div>`:""}
          </div>
        `:""}
      </div>
    </div>
  `}function _(t){return t>=4?"#86efac":t>=3?"#fde68a":"#fca5a5"}function m(t){return t.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;")}const v=document.getElementById("app"),te=document.getElementById("breadcrumb");function w(t){te.innerHTML=t.map((a,s)=>a.href&&s<t.length-1?`<a href="${a.href}">${a.label}</a>`:`<span style="color:#ccc">${a.label}</span>`).join(' <span style="color:#555">›</span> ')}async function T(){const a=(location.hash.replace(/^#\/?/,"")||"").split("/").filter(Boolean);if(v.innerHTML="",a.length===0)w([{label:"Runs"}]),await F(v,{navigate:E});else if(a[0]==="runs"&&a.length===2){const s=a[1];w([{label:"Runs",href:"#/"},{label:s}]),await Z(v,{runId:s,navigate:E})}else if(a[0]==="runs"&&a.length===4&&a[2]==="records"){const s=a[1],n=parseInt(a[3],10);w([{label:"Runs",href:"#/"},{label:s,href:`#/runs/${s}`},{label:`Record ${n}`}]),await Q(v,{runId:s,index:n,navigate:E})}else v.innerHTML='<p style="color:#888;padding:20px">Not found.</p>'}function E(t){location.hash=t}window.addEventListener("hashchange",T);T();
