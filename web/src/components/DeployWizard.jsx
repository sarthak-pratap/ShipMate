import React, { useMemo, useState } from "react";

const BASE = import.meta.env.VITE_API_BASE || "";

// Deploy wizard: asks the few questions that actually change the deploy
// command, then fetches a deterministic script from the API.
export default function DeployWizard({ result, onClose, onCopied }) {
  const runtimes = useMemo(
    () => (result.graph?.nodes || []).filter((n) => ["frontend", "api", "worker"].includes(n.role)),
    [result]
  );
  const hasDb = useMemo(
    () => (result.graph?.nodes || []).some((n) => n.role === "database"),
    [result]
  );

  const [projectName, setProjectName] = useState(result.project_name || "my-project");
  const [target, setTarget] = useState("new");
  const [push, setPush] = useState(() => new Set(runtimes.map((r) => r.id)));
  const [haDb, setHaDb] = useState(false);
  const [script, setScript] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  function togglePush(id) {
    setPush((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }

  async function generate() {
    setBusy(true); setErr(""); setScript("");
    try {
      const res = await fetch(`${BASE}/api/deploy-script`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          id: result.id,
          project_name: projectName.trim() || undefined,
          target,
          push: [...push],
          ha_db: hasDb ? haDb : undefined,
        }),
      });
      const data = await res.json();
      if (data.error) throw new Error(data.error);
      setScript(data.script);
    } catch (e) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  }

  function copyScript() {
    navigator.clipboard?.writeText(script);
    onCopied?.();
  }

  return (
    <div className="wizard-overlay" onPointerDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="wizard">
        <div className="wizard-head">
          <span className="panel-label">▲ deploy to zerops</span>
          <button className="wizard-close" onClick={onClose}>✕</button>
        </div>

        {!script ? (
          <>
            <div className="wizard-q">
              <label>1 · project name</label>
              <input value={projectName} onChange={(e) => setProjectName(e.target.value)} spellCheck={false} />
            </div>

            <div className="wizard-q">
              <label>2 · where does it go?</label>
              <div className="wizard-radios">
                <button className={target === "new" ? "on" : ""} onClick={() => setTarget("new")}>
                  create a NEW project
                </button>
                <button className={target === "existing" ? "on" : ""} onClick={() => setTarget("existing")}>
                  add to an EXISTING project
                </button>
              </div>
            </div>

            <div className="wizard-q">
              <label>3 · which services to build & push?</label>
              <div className="wizard-checks">
                {runtimes.map((r) => (
                  <button key={r.id} className={push.has(r.id) ? "on" : ""} onClick={() => togglePush(r.id)}>
                    {push.has(r.id) ? "☑" : "☐"} {r.id} <em>{r.role}</em>
                  </button>
                ))}
                {!runtimes.length && <span className="wizard-note">no runtime services — the import alone is enough</span>}
              </div>
            </div>

            {hasDb && (
              <div className="wizard-q">
                <label>4 · database resilience</label>
                <div className="wizard-radios">
                  <button className={!haDb ? "on" : ""} onClick={() => setHaDb(false)}>
                    NON_HA <em>single container · cheaper · demos</em>
                  </button>
                  <button className={haDb ? "on" : ""} onClick={() => setHaDb(true)}>
                    HA <em>replicated · survives node failure</em>
                  </button>
                </div>
              </div>
            )}

            {err && <div className="err">⚠ {err}</div>}
            <button className="go" onClick={generate} disabled={busy}>
              {busy ? "building…" : "generate my deploy script →"}
            </button>
          </>
        ) : (
          <>
            <pre className="code wizard-script">{script}</pre>
            <div className="wizard-actions">
              <button className="go" onClick={copyScript}>copy script</button>
              <button className="wizard-back" onClick={() => setScript("")}>← change answers</button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
