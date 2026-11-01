/* The graph view's React half: the React Flow canvas, the node card, the subflow box and the edge. index.js turns the
   row model into a laid-out {nodes, edges, groups}; this file only draws it. */

import { memo } from 'react';
import { ReactFlow, Background, Controls, MiniMap, Handle, Position, BaseEdge, EdgeLabelRenderer, MarkerType, getSmoothStepPath } from '@xyflow/react';

// [target side, source side] per layout direction
const SIDES = { LR: [Position.Left, Position.Right], RL: [Position.Right, Position.Left], TB: [Position.Top, Position.Bottom], BT: [Position.Bottom, Position.Top] };

const RowNode = memo(function RowNode({ data }) {
  const { node, sides, active } = data;
  return (
    <div className={`dv-graph-node${active ? ' dv-active' : ''}`} style={{ '--dv-node': node.colour, width: node.width, height: node.height }} title={node.title}>
      <Handle type="target" position={sides[0]} isConnectable={false} />
      <div className="dv-graph-title"><span className="dv-graph-dot" aria-hidden="true" />{node.title}</div>
      {node.fields.length > 0 && (
        <dl className="dv-graph-fields">
          {node.fields.map((f) => (
            <div key={f.id}><dt>{f.label}</dt><dd dangerouslySetInnerHTML={{ __html: f.html }} /></div>
          ))}
        </dl>
      )}
      <Handle type="source" position={sides[1]} isConnectable={false} />
    </div>
  );
});

const GroupNode = memo(function GroupNode({ data }) {
  const { grp, onOpenGroup } = data;
  return (
    <div className="dv-graph-group" style={{ '--dv-node': grp.colour }}>
      <button type="button" className="dv-graph-grouplabel nodrag" onClick={(e) => { e.stopPropagation(); onOpenGroup(grp); }} title={`Show the ${grp.rows.length} records in ${grp.label}`}>
        {grp.label} <span>{grp.rows.length}</span>
      </button>
    </div>
  );
});

/** A smooth-step edge; parallel edges between one pair shift apart (both ends and the bend), each with its label. */
function RowEdge({ sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition, data, markerEnd, style }) {
  const across = sourcePosition === Position.Left || sourcePosition === Position.Right;
  const s = data.edge.spread;
  const side = s * 9; // px: endpoints stay on the node's side
  const sx = across ? sourceX : sourceX + side, sy = across ? sourceY + side : sourceY;
  const tx = across ? targetX : targetX + side, ty = across ? targetY + side : targetY;
  const centerX = (sx + tx) / 2 + (across ? s * 16 : 0);
  const centerY = (sy + ty) / 2 + (across ? 0 : s * 16);
  const [path, labelX, labelY] = getSmoothStepPath({ sourceX: sx, sourceY: sy, sourcePosition, targetX: tx, targetY: ty, targetPosition, borderRadius: 8, centerX, centerY });
  const label = data.edge.label;
  return (
    <>
      <BaseEdge path={path} markerEnd={markerEnd} style={style} />
      {label && (
        <EdgeLabelRenderer>
          <div className="dv-graph-elabel" style={{ transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)`, '--dv-edge': data.edge.colour }}>{label}</div>
        </EdgeLabelRenderer>
      )}
    </>
  );
}

const nodeTypes = { dvrow: RowNode, dvgroup: GroupNode };
// WHY a floor on a phone: a wide graph fitted into 390 px is unreadable; readable cards you pan to beat a thumbnail
const NARROW_MIN_ZOOM = 0.45;
const edgeTypes = { dv: RowEdge };

export function Flow({ model, tokens, selected, narrow, onOpen, onOpenGroup }) {
  const sides = SIDES[model.direction] || SIDES.LR;
  const byId = new Map(model.groups.map((g) => [g.id, g]));
  const nodes = [
    // WHY groups first: React Flow needs a parent before its children
    ...model.groups.map((g) => ({
      id: g.id, type: 'dvgroup', position: { x: g.x, y: g.y }, width: g.width, height: g.height, style: { width: g.width, height: g.height },
      data: { grp: { ...g, colour: g.slot ? tokens.series[(g.slot - 1) % tokens.series.length] : tokens.muted }, onOpenGroup },
      draggable: false, selectable: false, zIndex: 0,
    })),
    ...model.nodes.map((n) => {
      const parent = n.group && byId.get(n.group);
      return {
        id: n.id, type: 'dvrow', width: n.width, height: n.height, zIndex: 1,
        position: parent ? { x: n.x - parent.x, y: n.y - parent.y } : { x: n.x, y: n.y },
        ...(parent ? { parentId: parent.id } : {}),
        data: { node: n, sides, active: selected === n.id },
      };
    }),
  ];
  const edges = model.edges.map((e) => ({
    id: e.id, source: e.source, target: e.target, type: 'dv', data: { edge: e }, zIndex: 2,
    style: { stroke: e.colour, strokeWidth: 1.6 },
    markerEnd: { type: MarkerType.ArrowClosed, color: e.colour, width: 16, height: 16 },
  }));
  return (
    <ReactFlow
      nodes={nodes} edges={edges} nodeTypes={nodeTypes} edgeTypes={edgeTypes}
      colorMode={tokens.dark ? 'dark' : 'light'}
      fitView fitViewOptions={{ padding: 0.08, minZoom: narrow ? NARROW_MIN_ZOOM : 0.1 }} minZoom={0.1} maxZoom={2.5}
      nodesConnectable={false} edgesFocusable={false} elevateEdgesOnSelect={false}
      onNodeClick={(_e, node) => { if (node.type === 'dvrow') onOpen(node.id); }}
      style={{ position: 'absolute', inset: 0 }}
    >
      <Background gap={20} size={1} color={tokens.rule} />
      <Controls position="top-left" showInteractive={false} />
      {!narrow && (
        <MiniMap pannable zoomable position="bottom-right" ariaLabel="Graph overview" style={{ width: 160, height: 108 }}
          nodeColor={(n) => (n.type === 'dvgroup' ? 'transparent' : n.data.node.colour)}
          nodeStrokeColor={(n) => (n.type === 'dvgroup' ? n.data.grp.colour : 'transparent')} nodeBorderRadius={3} />
      )}
    </ReactFlow>
  );
}
