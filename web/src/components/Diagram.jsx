import React, { useEffect, useMemo, useRef, useState } from "react";

// Interactive neo-brutalist topology canvas.
//   • auto-layout in role bands (public → frontend → api/worker → managed),
//     wrapping wide bands onto multiple lines so big graphs stay readable
//   • drag a node to reposition it   • drag empty space to pan
//   • scroll / pinch to zoom (around the cursor)   • RESET button
// Pure SVG + pointer events — no external graph library, stays dependency-light.

const ROLE_ROW = {
  public: 0, frontend: 1, api: 2, worker: 2,
  database: 3, cache: 3, storage: 3, broker: 3, search: 3,
};
const ROLE_FILL = {
  public: "#2eea8b", frontend: "#4d9fff", api: "#ffd02f", worker: "#b794ff",
  database: "#ff8a3d", cache: "#ff6b9d", storage: "#2eea8b", broker: "#ff8a3d", search: "#4d9fff",
};

const NODE_W = 168, NODE_H = 60, SH = 5;
const COL_GAP = 46, ROW_GAP = 116, PER_ROW = 4, PAD = 40;

function layout(nodes) {
  // group by band
  const bands = {};
  nodes.forEach((n) => {
    const r = ROLE_ROW[n.role] ?? 2;
    (bands[r] ||= []).push(n);
  });

  const pos = {};
  let y = PAD;
  let maxRight = 0;
  Object.keys(bands).sort((a, b) => a - b).forEach((r) => {
    const items = bands[r];
    // wrap into sublines of PER_ROW
    for (let i = 0; i < items.length; i += PER_ROW) {
      const line = items.slice(i, i + PER_ROW);
      const rowW = line.length * (NODE_W + COL_GAP) - COL_GAP;
      const startX = PAD + Math.max(0, (PER_ROW * (NODE_W + COL_GAP) - COL_GAP - rowW) / 2);
      line.forEach((n, j) => {
        pos[n.id] = { x: startX + j * (NODE_W + COL_GAP), y };
        maxRight = Math.max(maxRight, pos[n.id].x + NODE_W);
      });
      y += ROW_GAP;
    }
  });
  const contentW = maxRight + PAD;
  const contentH = y - ROW_GAP + NODE_H + PAD;
  return { pos, contentW, contentH };
}

export default function Diagram({ graph }) {
  const svgRef = useRef(null);
  const [pos, setPos] = useState({});
  const [view, setView] = useState({ x: 0, y: 0, w: 800, h: 480 });
  const [expanded, setExpanded] = useState(false);
  const base = useMemo(() => (graph ? layout(graph.nodes) : null), [graph]);
  const drag = useRef(null); // {type:'node'|'pan', id?, ...}

  // close fullscreen with Escape
  useEffect(() => {
    if (!expanded) return;
    const onKey = (e) => e.key === "Escape" && setExpanded(false);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [expanded]);

  // (re)initialise positions + view whenever the graph changes
  useEffect(() => {
    if (!base) return;
    setPos(base.pos);
    setView({ x: 0, y: 0, w: base.contentW, h: base.contentH });
  }, [base]);

  if (!graph || !graph.nodes?.length) {
    return <div className="diagram-empty">[ topology renders here ]</div>;
  }

  const nodeById = Object.fromEntries(graph.nodes.map((n) => [n.id, n]));

  // ---- coordinate helpers ----
  function clientToView(e) {
    const svg = svgRef.current;
    const pt = svg.createSVGPoint();
    pt.x = e.clientX; pt.y = e.clientY;
    const m = svg.getScreenCTM().inverse();
    return pt.matrixTransform(m);
  }
  function pxPerUnit() {
    const r = svgRef.current.getBoundingClientRect();
    return r.width / view.w;
  }

  // ---- pointer handlers ----
  function onNodeDown(e, id) {
    e.stopPropagation();
    const p = clientToView(e);
    drag.current = { type: "node", id, ox: p.x - pos[id].x, oy: p.y - pos[id].y };
    e.target.setPointerCapture?.(e.pointerId);
  }
  function onBgDown(e) {
    drag.current = { type: "pan", cx: e.clientX, cy: e.clientY, vx: view.x, vy: view.y };
    svgRef.current.setPointerCapture?.(e.pointerId);
  }
  function onMove(e) {
    const d = drag.current;
    if (!d) return;
    if (d.type === "node") {
      const p = clientToView(e);
      setPos((prev) => ({ ...prev, [d.id]: { x: p.x - d.ox, y: p.y - d.oy } }));
    } else if (d.type === "pan") {
      const k = view.w / svgRef.current.getBoundingClientRect().width;
      setView((v) => ({ ...v, x: d.vx - (e.clientX - d.cx) * k, y: d.vy - (e.clientY - d.cy) * k }));
    }
  }
  function onUp() { drag.current = null; }

  function onWheel(e) {
    e.preventDefault();
    const p = clientToView(e);
    const factor = e.deltaY > 0 ? 1.12 : 0.89;
    setView((v) => {
      const nw = Math.min(Math.max(v.w * factor, 200), base.contentW * 4);
      const nh = nw * (v.h / v.w);
      // keep the point under the cursor fixed
      return { x: p.x - (p.x - v.x) * (nw / v.w), y: p.y - (p.y - v.y) * (nh / v.h), w: nw, h: nh };
    });
  }
  function reset() { setPos(base.pos); setView({ x: 0, y: 0, w: base.contentW, h: base.contentH }); }

  const cx = (id) => pos[id]?.x + NODE_W / 2;
  const cy = (id) => pos[id]?.y + NODE_H / 2;

  const canvas = (
    <div className={`diagram-wrap${expanded ? " is-expanded" : ""}`}>
      <div className="diagram-controls">
        <button onClick={reset} title="reset view">⤢ reset</button>
        <button onClick={() => setExpanded((v) => !v)} title={expanded ? "close" : "expand"}>
          {expanded ? "✕ close" : "⛶ expand"}
        </button>
        <span className="diagram-hint">drag · scroll to zoom{expanded ? " · esc to close" : ""}</span>
      </div>
      <svg
        ref={svgRef}
        className="diagram"
        viewBox={`${view.x} ${view.y} ${view.w} ${view.h}`}
        preserveAspectRatio="xMidYMid meet"
        onPointerDown={onBgDown}
        onPointerMove={onMove}
        onPointerUp={onUp}
        onPointerLeave={onUp}
        onWheel={onWheel}
      >
        {/* edges */}
        {graph.edges.map((e, i) => {
          if (!pos[e.source] || !pos[e.target]) return null;
          const isPublic = e.kind === "public";
          return (
            <line
              key={i}
              x1={cx(e.source)} y1={cy(e.source)}
              x2={cx(e.target)} y2={cy(e.target)}
              stroke="#111"
              strokeWidth={2.5}
              strokeDasharray={isPublic ? "8 6" : "0"}
            />
          );
        })}
        {/* nodes */}
        {graph.nodes.map((n) => {
          const p = pos[n.id];
          if (!p) return null;
          const fill = ROLE_FILL[n.role] || "#ffd02f";
          return (
            <g key={n.id} transform={`translate(${p.x},${p.y})`}
               style={{ cursor: "grab" }} onPointerDown={(e) => onNodeDown(e, n.id)}>
              <rect x={SH} y={SH} width={NODE_W} height={NODE_H} fill="#111" />
              <rect width={NODE_W} height={NODE_H} fill={fill} stroke="#111" strokeWidth="3" />
              <text x={14} y={26} fill="#111" fontSize="15" fontWeight="800"
                    fontFamily="'Space Grotesk', system-ui" style={{ textTransform: "uppercase" }}>
                {truncate(n.label, 16)}
              </text>
              <text x={14} y={46} fill="#111" fontSize="11.5"
                    fontFamily="'IBM Plex Mono', monospace" fontWeight="600">
                {n.subtitle || ""}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );

  if (expanded) {
    return (
      <>
        {/* keep the inline slot filled so the panel layout doesn't jump */}
        <div className="diagram-empty">[ topology expanded — press esc or ✕ to return ]</div>
        <div className="diagram-overlay" onPointerDown={(e) => { if (e.target === e.currentTarget) setExpanded(false); }}>
          {canvas}
        </div>
      </>
    );
  }
  return canvas;
}

function truncate(s, n) {
  return s && s.length > n ? s.slice(0, n - 1) + "…" : s;
}
