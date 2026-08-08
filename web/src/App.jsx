import React, { useEffect, useState } from "react";
import { generate, fetchGeneration } from "./api.js";
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
  const [toast, setToast] = useState("");

  // open a shared result: /?g=<id>
  useEffect(() => {
    const id = new URLSearchParams(window.location.search).get("g");
    if (!id) return;
    setBusy(true);
    fetchGeneration(id)
      .then((data) => { if (data.error) throw new Error(data.error); setResult(data); })
      .catch((e) => setErr(`Couldn't load shared result: ${e.message}`))
      .finally(() => setBusy(false));
  }, []);

  function flash(msg) { setToast(msg); setTimeout(() => setToast(""), 1800); }

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
      // if there are no runtime services, zerops.yaml is empty — show import instead
      setTab(data.zerops_yaml?.includes("- setup:") ? "zerops" : "import");
    } catch (e) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  }

  function runRepoExample(url) { setRepo(url); run({ mode: "repo", repo_url: url }); }

  function copy(text, label = "Copied") {
    navigator.clipboard?.writeText(text);
    flash(`${label} ✓`);
  }
  function download(name, text) {
    const blob = new Blob([text], { type: "text/yaml" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob); a.download = name; a.click();
    flash("Downloaded ✓");
  }
  function share() {
    if (!result?.id) return;
    const url = `${window.location.origin}/?g=${result.id}`;
    navigator.clipboard?.writeText(url);
    flash("Share link copied ✓");
  }
  function deploy() {
    if (!result) return;
    const runtimes = (result.graph?.nodes || [])
      .filter((n) => ["frontend", "api", "worker"].includes(n.role))
      .map((n) => n.id);
    const pushes = runtimes.length
      ? runtimes.map((h) => `zcli push ${h}`).join("\n")
      : "# (no runtime services detected — managed services deploy from the import alone)";
    const script =
`# ShipMate → Zerops
# Run this from the ROOT of your application's repository (where your source
# code lives) with zcli installed and logged in (zcli login <token>).
cat > zerops.yaml <<'ZEOF'
${result.zerops_yaml}ZEOF
cat > zerops-project-import.yml <<'IEOF'
${result.import_yaml}IEOF

# 1. create the project + all services
zcli project project-import zerops-project-import.yml

# 2. build & deploy each runtime service (zcli is interactive — it will ask
#    which project to use; each push reads the matching setup from zerops.yaml)
${pushes}

# 3. any secrets flagged in the notes must be set in the Zerops GUI
#    (service → Environment variables → secret) before the app fully works.`;
    copy(script, "Deploy script copied");
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
            {result?.score && (
              <span className={`score-badge s-${result.score.grade.split(" ")[0].replace(/[^a-z]/g, "")}`}>
                <b>{result.score.score}/10</b> {result.score.grade}
              </span>
            )}
            {result && (
              <div className="head-actions">
                <button onClick={share} title="copy a shareable link">🔗 share</button>
                <button className="deploy" onClick={deploy} title="copy the zcli deploy command">▲ deploy to zerops</button>
              </div>
            )}
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

      {toast && <div className="toast">{toast}</div>}
    </div>
  );
}
