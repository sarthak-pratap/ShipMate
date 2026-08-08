import React from "react";

// A dependency-free SVG topology diagram. Lays services out in role-based rows
// (public → frontend → runtimes → managed) and draws private-network edges.
// Swap for reactflow later if you want drag/zoom; this keeps the repo runnable
// with zero extra deps.

const ROLE_ROW = {
  frontend: 1,
  api: 2,
  worker: 2,
  database: 3,
  cache: 3,
  storage: 3,
  broker: 3,
  search: 3,
};

const ROLE_COLOR = {
  frontend: "#34e0d0",
  api: "#7c5cff",
  worker: "#9d84ff",
  database: "#ffbf47",
  cache: "#b6f24a",
  storage: "#ff6b8b",
  broker: "#ff9f43",
  search: "#4dd0e1",
};

export default function Diagram({ graph }) {
  if (!graph || !graph.nodes?.length) {
    return <div className="diagram-empty">Your architecture will appear here.</div>;
  }

  const W = 720;
  const rowGap = 120;
  const nodeW = 150;
  const nodeH = 56;

  // group nodes into rows
  const rows = { 0: [{ id: "__public__", label: "🌐 Public traffic", role: "public" }], 1: [], 2: [], 3: [] };
  graph.nodes.forEach((n) => {
    rows[ROLE_ROW[n.role] || 2].push(n);
  });

  const pos = {};
  const rowKeys = Object.keys(rows).filter((r) => rows[r].length);
  rowKeys.forEach((r, ri) => {
    const items = rows[r];
    const totalW = items.length * (nodeW + 30) - 30;
    const startX = (W - totalW) / 2;
    items.forEach((n, i) => {
      pos[n.id] = { x: startX + i * (nodeW + 30) + nodeW / 2, y: 40 + ri * rowGap };
    });
  });

  const H = 40 + rowKeys.length * rowGap;

  return (
    <svg className="diagram" viewBox={`0 0 ${W} ${H}`} width="100%">
      {/* edges */}
      {graph.edges.map((e, i) => {
        const a = pos[e.source];
        const b = pos[e.target];
        if (!a || !b) return null;
        const isPublic = e.kind === "public";
        return (
          <line
            key={i}
            x1={a.x} y1={a.y + nodeH / 2}
            x2={b.x} y2={b.y - nodeH / 2}
            stroke={isPublic ? "#34e0d0" : "#3a3f55"}
            strokeWidth={isPublic ? 2 : 1.5}
            strokeDasharray={isPublic ? "4 3" : "0"}
          />
        );
      })}
      {/* nodes */}
      {Object.entries(rows).flatMap(([, items]) =>
        items.map((n) => {
          const p = pos[n.id];
          if (!p) return null;
          const color = n.role === "public" ? "#34e0d0" : ROLE_COLOR[n.role] || "#7c5cff";
          return (
            <g key={n.id} transform={`translate(${p.x - nodeW / 2}, ${p.y - nodeH / 2})`}>
              <rect
                width={nodeW} height={nodeH} rx="10"
                fill="#171a28" stroke={color} strokeWidth="1.5"
              />
              <text x="14" y="24" fill="#e8eaf2" fontSize="14" fontWeight="600" fontFamily="system-ui">
                {n.label}
              </text>
              {n.subtitle && (
                <text x="14" y="42" fill="#9aa0b4" fontSize="11" fontFamily="monospace">
                  {n.subtitle}
                </text>
              )}
            </g>
          );
        })
      )}
    </svg>
  );
}
