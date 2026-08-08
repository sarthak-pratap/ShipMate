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

const SEV_COLOR = { error: "#ff6b8b", warning: "#ffbf47", info: "#9aa0b4" };

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
      if (mode === "repo") { payload.files = []; payload.file_contents = {}; payload.project_name = repo.split("/").pop(); }
      const data = await generate(payload);
      if (data.error) throw new Error(data.error);
      setResult(data);
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

  return (
    <div className="app">
      <header>
        <div className="logo">Ship<span>Mate</span></div>
        <div className="tagline">Describe an app → get a validated Zerops config + a live architecture map.</div>
      </header>

      <div className="modes">
        {["compose", "prompt", "repo"].map((m) => (
          <button key={m} className={mode === m ? "on" : ""} onClick={() => setMode(m)}>
            {m === "compose" ? "🐳 docker-compose" : m === "prompt" ? "💬 Prompt" : "🐙 Repo URL"}
          </button>
        ))}
      </div>

      <div className="grid">
        <section className="input">
          {mode === "compose" && (
            <textarea value={compose} onChange={(e) => setCompose(e.target.value)} spellCheck={false} />
          )}
          {mode === "prompt" && (
            <textarea value={prompt} onChange={(e) => setPrompt(e.target.value)} spellCheck={false} />
          )}
          {mode === "repo" && (
            <input className="repo" value={repo} placeholder="https://github.com/you/project"
                   onChange={(e) => setRepo(e.target.value)} />
          )}
          <button className="go" onClick={run} disabled={busy}>
            {busy ? "Generating…" : "Generate →"}
          </button>
          {err && <div className="err">⚠ {err}</div>}
        </section>

        <section className="output">
          <Diagram graph={result?.graph} />
          {result && (
            <>
              <div className="tabs">
                <button className={tab === "zerops" ? "on" : ""} onClick={() => setTab("zerops")}>zerops.yaml</button>
                <button className={tab === "import" ? "on" : ""} onClick={() => setTab("import")}>project-import</button>
                <button className={tab === "lint" ? "on" : ""} onClick={() => setTab("lint")}>
                  lint {result.lint?.length ? `(${result.lint.length})` : ""}
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
                  {(!result.lint || !result.lint.length) && <div className="clean">✓ No issues found.</div>}
                  {result.lint?.map((f, i) => (
                    <div className="finding" key={i}>
                      <span className="sev" style={{ color: SEV_COLOR[f.severity] }}>{f.severity}</span>
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
    </div>
  );
}

function Code({ text, onCopy, onDownload }) {
  return (
    <div className="code-wrap">
      <div className="code-actions">
        <button onClick={() => onCopy(text)}>Copy</button>
        <button onClick={onDownload}>Download</button>
      </div>
      <pre className="code">{text}</pre>
    </div>
  );
}
