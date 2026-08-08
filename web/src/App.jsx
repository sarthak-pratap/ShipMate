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

export default function App() {
  const [mode, setMode] = useState("compose");
  const [compose, setCompose] = useState(SAMPLE_COMPOSE);
  const [prompt, setPrompt] = useState("a booking app with postgres and a nightly reminder worker");
  const [repo, setRepo] = useState("");
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [tab, setTab] = useState("zerops");

  async function run() {
    setBusy(true); setErr(""); setResult(null);
    try {
      const payload = { mode };
      if (mode === "compose") payload.compose = compose;
      if (mode === "prompt") payload.prompt = prompt;
      if (mode === "repo") payload.repo_url = repo.trim();
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

  function copy(text) { navigator.clipboard?.writeText(text); }
  function download(name, text) {
    const blob = new Blob([text], { type: "text/yaml" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob); a.download = name; a.click();
  }

  const inputLabel =
    mode === "compose" ? "paste docker-compose.yml"
    : mode === "prompt" ? "describe your app"
    : "public github repo url";

  return (
    <div className="app">
      <header>
        <div className="logo">Ship<span>Mate</span></div>
        <div className="tagline">describe an app → validated zerops.yaml + architecture map</div>
        <div className="badge-row">
          <span className="badge">deploys on zerops</span>
          <span className="badge alt">misconfig linter inside</span>
        </div>
      </header>

      <div className="modes">
        {[
          ["compose", "docker-compose"],
          ["prompt", "prompt"],
          ["repo", "repo url"],
        ].map(([m, label]) => (
          <button key={m} className={mode === m ? "on" : ""} onClick={() => setMode(m)}>
            {label}
          </button>
        ))}
      </div>

      <div className="grid">
        <section className="input">
          <span className="panel-label">{inputLabel}</span>
          {mode === "compose" && (
            <textarea value={compose} onChange={(e) => setCompose(e.target.value)} spellCheck={false} />
          )}
          {mode === "prompt" && (
            <textarea value={prompt} onChange={(e) => setPrompt(e.target.value)} spellCheck={false} />
          )}
          {mode === "repo" && (
            <>
              <input className="repo" value={repo} placeholder="https://github.com/you/project"
                     onChange={(e) => setRepo(e.target.value)}
                     onKeyDown={(e) => e.key === "Enter" && run()} />
              <div className="hint">
                public repos only · reads Dockerfile, package.json, requirements.txt, docker-compose & more
              </div>
            </>
          )}
          <button className="go" onClick={run} disabled={busy}>
            {busy ? "working…" : "generate →"}
          </button>
          {err && <div className="err">⚠ {err}</div>}
          {result?.warnings?.length > 0 && (
            <div className="warnings">
              <b>notes:</b> {result.warnings.join(" · ")}
            </div>
          )}
        </section>

        <section className="output">
          <span className="panel-label">
            {result ? `topology · ${result.project_name}` : "topology"}
          </span>
          <Diagram graph={result?.graph} />
          {result && (
            <>
              <div className="tabs">
                <button className={tab === "zerops" ? "on" : ""} onClick={() => setTab("zerops")}>zerops.yaml</button>
                <button className={tab === "import" ? "on" : ""} onClick={() => setTab("import")}>project-import</button>
                <button className={tab === "lint" ? "on" : ""} onClick={() => setTab("lint")}>
                  lint{result.lint?.length ? ` [${result.lint.length}]` : ""}
                </button>
              </div>

              {tab === "zerops" && (
                <Code text={result.zerops_yaml} onCopy={copy}
                      onDownload={() => download("zerops.yaml", result.zerops_yaml)} />
              )}
              {tab === "import" && (
                <Code text={result.import_yaml} onCopy={copy}
                      onDownload={() => download("zerops-project-import.yml", result.import_yaml)} />
              )}
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
            </>
          )}
        </section>
      </div>

      <div className="foot">
        <span>SHIPMATE · built for THE ZEROPS CHALLENGE · runs on zerops</span>
      </div>
    </div>
  );
}

function Code({ text, onCopy, onDownload }) {
  return (
    <div className="code-wrap">
      <div className="code-actions">
        <button onClick={() => onCopy(text)}>copy</button>
        <button onClick={onDownload}>download</button>
      </div>
      <pre className="code">{text}</pre>
    </div>
  );
}
