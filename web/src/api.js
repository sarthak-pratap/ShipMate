const BASE = import.meta.env.VITE_API_BASE || "";

export async function generate(payload) {
  const res = await fetch(`${BASE}/api/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(`API ${res.status}`);
  return res.json();
}

export async function health() {
  const res = await fetch(`${BASE}/api/health`);
  return res.json();
}
