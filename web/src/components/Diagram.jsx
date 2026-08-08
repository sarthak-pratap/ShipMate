import React from "react";

// Neo-brutalist SVG topology diagram: flat fills, 3px black strokes,
// hard offset shadows, role-based rows (public → frontend → runtimes → managed).

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

const ROLE_FILL = {
  public: "#2eea8b",
  frontend: "#4d9fff",
  api: "#ffd02f",
  worker: "#b794ff",
  database: "#ff8a3d",
  cache: "#ff6b9d",
  storage: "#2eea8b",
  broker: "#ff8a3d",
  search: "#4d9fff",
};

export default function Diagram({ graph }) {
  if (!graph || !graph.nodes?.length) {
    return <div className="diagram-empty">[ topology renders here ]</div>;
  }

  const W = 760;
  const rowGap = 118;
  const nodeW = 158;
  const nodeH = 58;
  const SH = 5; // shadow offset

  const rows = {
    0: [{ id: "__public__", label: "PUBLIC TRAFFIC", subtitle: "https", role: "public" }],
    1: [], 2: [], 3: [],
  };
  graph.nodes.forEach((n) => rows[ROLE_ROW[n.role] ?? 2].push(n));

  const pos = {};
  const rowKeys = Object.keys(rows).filter((r) => rows[r].length);
  rowKeys.forEach((r, ri) => {
    const items = rows[r];
    const totalW = items.length * (nodeW + 34) - 34;
    const startX = (W - totalW) / 2;
    items.forEach((n, i) => {
      pos[n.id] = { x: startX + i * (nodeW + 34) + nodeW / 2, y: 44 + ri * rowGap };
    });
  });

  const H = 44 + rowKeys.length * rowGap;

  return (
    <svg className="diagram" viewBox={`0 0 ${W} ${H}`} width="100%">
      {/* edges first */}
      {graph.edges.map((e, i) => {
        const a = pos[e.source];
        const b = pos[e.target];
        if (!a || !b) return null;
        const isPublic = e.kind === "public";
        return (
          <line
            key={i}
            x1={a.x} y1={a.y + nodeH / 2}
            x2={b.x} y2={b.y - nodeH / 2 - SH}
            stroke="#111"
            strokeWidth={isPublic ? 3 : 2.5}
            strokeDasharray={isPublic ? "7 5" : "0"}
          />
        );
      })}
      {/* nodes */}
      {Object.values(rows).flat().map((n) => {
        const p = pos[n.id];
        if (!p) return null;
        const fill = ROLE_FILL[n.role] || "#ffd02f";
        const x = p.x - nodeW / 2;
        const y = p.y - nodeH / 2;
        return (
          <g key={n.id}>
            {/* hard shadow */}
            <rect x={x + SH} y={y + SH} width={nodeW} height={nodeH} fill="#111" />
            <rect x={x} y={y} width={nodeW} height={nodeH} fill={fill} stroke="#111" strokeWidth="3" />
            <text x={x + 14} y={y + 25} fill="#111" fontSize="14.5" fontWeight="800"
                  fontFamily="'Space Grotesk', system-ui" style={{ textTransform: "uppercase" }}>
              {n.label}
            </text>
            <text x={x + 14} y={y + 44} fill="#111" fontSize="11"
                  fontFamily="'IBM Plex Mono', monospace" fontWeight="600">
              {n.subtitle || ""}
            </text>
          </g>
        );
      })}
    </svg>
  );
}
