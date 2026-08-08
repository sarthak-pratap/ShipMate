import React, { useState } from "react";
import { generate } from "./api.js";
import Diagram from "./components/Diagram.jsx";

const SAMPLE_COMPOSE = `name: taskboard
services:
  web:
    image: node:22
    ports: ["3000:3000"]
    depends_on: [api]
  api:
    build: ./api
    ports: ["8000:8000"]
    environment:
      DB_HOST: db
      REDIS_HOST: cache
    depends_on: [db, cache]
  db:
    image: postgres:16
  cache:
    image: redis:7`;

const REPO_EXAMPLES = [
  ["voting app · 6 svc", "https://github.com/dockersamples/example-voting-app"],
  ["microblog · py+db+cache", "https://github.com/miguelgrinberg/microblog"],
  ["fastapi template", "https://github.com/fastapi/full-stack-fastapi-template"],
];

const PROMPT_EXAMPLES = [
  ["booking app", "a booking app with postgres and a nightly reminder worker"],
  ["realtime chat", "a realtime chat app with websockets, redis presence and postgres history"],
  ["rag search", "a document search tool: uploads to object storage, a worker builds embeddings into postgres, api serves queries"],
];

export default function App() {
  const [mode, setMode] = useState("compose");
  const [compose, setCompose] = useState(SAMPLE_COMPOSE);
  const [prompt, setPrompt] = useState(PROMPT_EXAMPLES[0][1]);
  const [repo, setRepo] = useState("");
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [tab, setTab] = useState("zerops");
  const [aiEnhance, setAiEnhance] = useState(false);

  async function run(overrides = {}) {
    setBusy(true); setErr(""); setResult(null);
    try {
      const payload = { mode, ai_enhance: aiEnhance, ...overrides };
      if (payload.mode === "compose" && !payload.compose) payload.compose = compose;
      if (payload.mode === "prompt" && !payload.prompt) payload.prompt = prompt;
      if (payload.mode === "repo" && !payload.repo_url) payload.repo_url = repo.trim();
      const data = await generate(payload);
      if (data.error) throw new Error(data.error);
      setResult(data);
      setTab("zerops");
    } catch (e) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  }

  function runRepoExample(url) { setRepo(url); run({ mode: "repo", repo_url: url }); }

  function copy(text) { navigator.clipboard?.writeText(text); }
  function download(name, text) {
    const blob = new Blob([text], { type: "text/yaml" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob); a.download = name; a.click();
  }

  const activeText = tab === "zerops" ? result?.zerops_yaml : result?.import_yaml;
  const activeFilename = tab === "zerops" ? "zerops.yaml" : "zerops-project-import.yml";

  return (
    <div className="app">
      <header>
        <div className="logo">Ship<span>Mate</span></div>
        <div className="tagline">app in → zerops.yaml + architecture map out</div>
        <div className="badge-row">
          <span className="badge">deploys on zerops</span>
          <span className="badge alt">misconfig linter inside</span>
        </div>
      </header>

      <div className="workbench">
        {/* ---------- input rail ---------- */}
        <section className="input">
          <div className="modes">
            {[["compose", "docker-compose"], ["prompt", "prompt"], ["repo", "repo url"]].map(([m, label]) => (
              <button key={m} className={mode === m ? "on" : ""}
                      onClick={() => { setMode(m); setErr(""); }}>
                {label}
              </button>
            ))}
          </div>

          {mode === "compose" && (
            <>
              <span className="panel-label">paste docker-compose.yml</span>
              <textarea value={compose} onChange={(e) => setCompose(e.target.value)} spellCheck={false} />
            </>
          )}

          {mode === "prompt" && (
            <>
              <span className="panel-label">describe your app</span>
              <textarea value={prompt} onChange={(e) => setPrompt(e.target.value)} spellCheck={false} />
              <div className="examples">
                {PROMPT_EXAMPLES.map(([label, p]) => (
                  <button key={label} onClick={() => setPrompt(p)}>{label}</button>
                ))}
              </div>
            </>
          )}

          {mode === "repo" && (
            <>
              <span className="panel-label">public github repo url</span>
              <input className="repo" value={repo} placeholder="https://github.com/you/project"
                     onChange={(e) => setRepo(e.target.value)}
                     onKeyDown={(e) => e.key === "Enter" && run()} />
              <div className="examples">
                {REPO_EXAMPLES.map(([label, url]) => (
                  <button key={url} onClick={() => runRepoExample(url)}>{label}</button>
                ))}
              </div>
              <div className="hint">
                reads docker-compose, Dockerfiles (multi-stage aware), package.json,
                requirements.txt & more · monorepos supported
              </div>
            </>
          )}

          {mode !== "prompt" && (
            <label className="ai-toggle">
              <input type="checkbox" checked={aiEnhance}
                     onChange={(e) => setAiEnhance(e.target.checked)} />
              <span>✨ use AI to fill gaps</span>
              <em>needs azure key</em>
            </label>
          )}
          <button className="go" onClick={() => run()} disabled={busy}>
            {busy ? "working…" : "generate →"}
          </button>
          {err && <div className="err">⚠ {err}</div>}
          {result?.warnings?.length > 0 && (
            <div className="warnings">
              <b>notes — how this was inferred:</b>
              <ul>
                {result.warnings.map((w, i) => <li key={i}>{w}</li>)}
              </ul>
            </div>
          )}
        </section>

        {/* ---------- output panel ---------- */}
        <section className="output">
          <div className="out-head">
            <span className="panel-label">
              {result ? `topology · ${result.project_name}` : "topology"}
            </span>
          </div>

          {result ? (
            <>
              <div className="diagram-box">
                <Diagram graph={result.graph} />
              </div>

              <div className="tabs">
                <button className={tab === "zerops" ? "on" : ""} onClick={() => setTab("zerops")}>zerops.yaml</button>
                <button className={tab === "import" ? "on" : ""} onClick={() => setTab("import")}>project-import</button>
                <button className={tab === "lint" ? "on" : ""} onClick={() => setTab("lint")}>
                  lint{result.lint?.length ? ` [${result.lint.length}]` : ""}
                </button>
                {tab !== "lint" && (
                  <div className="tab-actions">
                    <button onClick={() => copy(activeText)}>copy</button>
                    <button onClick={() => download(activeFilename, activeText)}>download</button>
                  </div>
                )}
              </div>

              <div className="result-area">
                {tab !== "lint" && <pre className="code">{activeText}</pre>}
                {tab === "lint" && (
                  <div className="lint">
                    {(!result.lint || !result.lint.length) && <div className="clean">✓ CLEAN — no issues found</div>}
                    {result.lint?.map((f, i) => (
                      <div className="finding" key={i}>
                        <span className={`sev ${f.severity}`}>{f.severity}</span>
                        <div>
                          <div className="msg">{f.message}</div>
                          <div className="fix">→ {f.fix}</div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </>
          ) : (
            <div className="diagram-empty">
              {busy ? "[ analysing… ]" : "[ pick a mode, hit generate — topology + yaml render here ]"}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
