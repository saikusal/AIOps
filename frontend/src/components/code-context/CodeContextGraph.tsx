import { useEffect, useRef, useState } from "react";
import * as d3 from "d3";
import type { CodeContextGraphLink, CodeContextGraphNode } from "../../lib/api";

type GraphMode = "landscape" | "runtime" | "changes";

type RenderNode = CodeContextGraphNode & {
  x?: number;
  y?: number;
  vx?: number;
  vy?: number;
  fx?: number | null;
  fy?: number | null;
};

type RenderLink = {
  source: string | RenderNode;
  target: string | RenderNode;
  label: string;
  weight: number;
};

type Props = {
  nodes: CodeContextGraphNode[];
  links: CodeContextGraphLink[];
  selectedNodeId?: string | null;
  mode: GraphMode;
  onSelectNode: (node: CodeContextGraphNode | null) => void;
};

const TYPE_COLORS: Record<string, string> = {
  application: "#8cf4ff",
  repository: "#52c3ff",
  service: "#a3ffcb",
  route: "#ffd27a",
  span: "#ffb36b",
  file: "#b9c7ff",
  change: "#ff8f95",
};

const RISK_GLOWS: Record<string, string> = {
  focus: "0 0 26px rgba(140, 244, 255, 0.48)",
  warning: "0 0 24px rgba(255, 143, 149, 0.38)",
  normal: "0 0 18px rgba(82, 195, 255, 0.18)",
};

function filterGraph(nodes: CodeContextGraphNode[], links: CodeContextGraphLink[], mode: GraphMode) {
  const hiddenTypes =
    mode === "runtime"
      ? new Set(["change"])
      : mode === "changes"
        ? new Set(["route", "span"])
        : new Set<string>();

  const allowedNodes = nodes.filter((node) => !hiddenTypes.has(node.type));
  const allowedIds = new Set(allowedNodes.map((node) => node.id));
  const allowedLinks = links.filter((link) => allowedIds.has(link.source) && allowedIds.has(link.target));

  return { nodes: allowedNodes, links: allowedLinks };
}

function useElementSize<T extends HTMLElement>() {
  const ref = useRef<T | null>(null);
  const [size, setSize] = useState({ width: 0, height: 0 });

  useEffect(() => {
    if (!ref.current) return;
    const element = ref.current;
    const observer = new ResizeObserver(([entry]) => {
      const box = entry.contentRect;
      setSize({ width: box.width, height: box.height });
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  return { ref, size };
}

function nodeRadius(node: CodeContextGraphNode) {
  return Math.max(7, Math.min(22, node.size * 0.42));
}

export function CodeContextGraph({ nodes, links, selectedNodeId, mode, onSelectNode }: Props) {
  const svgRef = useRef<SVGSVGElement | null>(null);
  const { ref: containerRef, size } = useElementSize<HTMLDivElement>();

  useEffect(() => {
    if (!svgRef.current || !size.width || !size.height) return;

    const { nodes: filteredNodes, links: filteredLinks } = filterGraph(nodes, links, mode);
    const graphNodes: RenderNode[] = filteredNodes.map((node) => ({ ...node }));
    const graphLinks: RenderLink[] = filteredLinks.map((link) => ({ ...link }));

    const linkedIds = new Set<string>();
    if (selectedNodeId) {
      graphLinks.forEach((link) => {
        if (link.source === selectedNodeId) linkedIds.add(String(link.target));
        if (link.target === selectedNodeId) linkedIds.add(String(link.source));
      });
    }

    const svg = d3.select(svgRef.current);
    svg.selectAll("*").remove();
    svg.attr("viewBox", `0 0 ${size.width} ${size.height}`);
    svg.on("click", () => onSelectNode(null));

    const defs = svg.append("defs");
    const gridPattern = defs
      .append("pattern")
      .attr("id", "code-context-grid")
      .attr("width", 36)
      .attr("height", 36)
      .attr("patternUnits", "userSpaceOnUse");
    gridPattern
      .append("path")
      .attr("d", "M 36 0 L 0 0 0 36")
      .attr("fill", "none")
      .attr("stroke", "rgba(110, 188, 227, 0.07)")
      .attr("stroke-width", 1);

    svg
      .append("rect")
      .attr("width", size.width)
      .attr("height", size.height)
      .attr("fill", "url(#code-context-grid)");

    const root = svg.append("g");
    const linkLayer = root.append("g").attr("class", "code-context-graph__links");
    const labelLayer = root.append("g").attr("class", "code-context-graph__labels");
    const nodeLayer = root.append("g").attr("class", "code-context-graph__nodes");

    const zoom = d3
      .zoom<SVGSVGElement, unknown>()
      .scaleExtent([0.45, 2.2])
      .on("zoom", (event: d3.D3ZoomEvent<SVGSVGElement, unknown>) => {
        root.attr("transform", event.transform.toString());
      });

    svg.call(zoom);
    svg.on("dblclick.zoom", null);

    const simulation = d3
      .forceSimulation<RenderNode>(graphNodes)
      .force(
        "link",
        d3
          .forceLink<RenderNode, RenderLink>(graphLinks)
          .id((node: RenderNode) => node.id)
          .distance((link: RenderLink) => {
            const targetNode = typeof link.target === "string" ? null : link.target;
            const sourceNode = typeof link.source === "string" ? null : link.source;
            if (sourceNode?.type === "application" || targetNode?.type === "application") return 120;
            if (sourceNode?.type === "repository" || targetNode?.type === "repository") return 98;
            if (sourceNode?.type === "change" || targetNode?.type === "change") return 84;
            return 72;
          })
          .strength((link: RenderLink) => Math.max(0.1, Math.min(0.55, link.weight * 0.18))),
      )
      .force("charge", d3.forceManyBody().strength(-260))
      .force("center", d3.forceCenter(size.width / 2, size.height / 2))
      .force("x", d3.forceX(size.width / 2).strength(0.03))
      .force("y", d3.forceY(size.height / 2).strength(0.03))
      .force("collide", d3.forceCollide<RenderNode>().radius((node: RenderNode) => nodeRadius(node) + 20));

    const linkSelection = linkLayer
      .selectAll<SVGLineElement, RenderLink>("line")
      .data(graphLinks)
      .join("line")
      .attr("stroke", (link: RenderLink) => {
        const sourceId = typeof link.source === "string" ? link.source : link.source.id;
        const targetId = typeof link.target === "string" ? link.target : link.target.id;
        return selectedNodeId && (sourceId === selectedNodeId || targetId === selectedNodeId)
          ? "rgba(162, 242, 255, 0.92)"
          : "rgba(101, 170, 212, 0.28)";
      })
      .attr("stroke-width", (link: RenderLink) => Math.max(1, Math.min(3.2, link.weight * 1.2)))
      .attr("stroke-linecap", "round");

    const labelSelection = labelLayer
      .selectAll<SVGTextElement, RenderLink>("text")
      .data(graphLinks.filter((link: RenderLink) => link.weight >= 1.5))
      .join("text")
      .attr("class", "code-context-graph__edge-label")
      .attr("text-anchor", "middle")
      .text((link: RenderLink) => link.label);

    const nodeSelection = nodeLayer
      .selectAll<SVGGElement, RenderNode>("g")
      .data(graphNodes)
      .join("g")
      .attr("class", "code-context-graph__node")
      .style("cursor", "pointer")
      .call(
        d3
          .drag<SVGGElement, RenderNode>()
          .on("start", (event: d3.D3DragEvent<SVGGElement, RenderNode, RenderNode>, node: RenderNode) => {
            if (!event.active) simulation.alphaTarget(0.2).restart();
            node.fx = node.x;
            node.fy = node.y;
          })
          .on("drag", (event: d3.D3DragEvent<SVGGElement, RenderNode, RenderNode>, node: RenderNode) => {
            node.fx = event.x;
            node.fy = event.y;
          })
          .on("end", (event: d3.D3DragEvent<SVGGElement, RenderNode, RenderNode>, node: RenderNode) => {
            if (!event.active) simulation.alphaTarget(0);
            node.fx = null;
            node.fy = null;
          }),
      )
      .on("click", (event: MouseEvent, node: RenderNode) => {
        event.stopPropagation();
        onSelectNode(node);
      });

    nodeSelection
      .append("circle")
      .attr("r", (node: RenderNode) => nodeRadius(node) + 10)
      .attr("fill", (node: RenderNode) => TYPE_COLORS[node.type] || "#88d7ff")
      .attr("opacity", (node: RenderNode) => (selectedNodeId && node.id !== selectedNodeId && !linkedIds.has(node.id) ? 0.08 : 0.16));

    nodeSelection
      .append("circle")
      .attr("r", (node: RenderNode) => nodeRadius(node))
      .attr("fill", (node: RenderNode) => TYPE_COLORS[node.type] || "#88d7ff")
      .attr("stroke", (node: RenderNode) => (selectedNodeId === node.id ? "#f6fbff" : "rgba(255, 255, 255, 0.28)"))
      .attr("stroke-width", (node: RenderNode) => (selectedNodeId === node.id ? 2.2 : 1.1))
      .attr("opacity", (node: RenderNode) => {
        if (!selectedNodeId) return node.type === "file" ? 0.76 : 0.96;
        if (node.id === selectedNodeId || linkedIds.has(node.id)) return 1;
        return node.type === "file" ? 0.18 : 0.28;
      });

    nodeSelection
      .append("text")
      .attr("class", "code-context-graph__node-label")
      .attr("text-anchor", "middle")
      .attr("dy", (node: RenderNode) => nodeRadius(node) + 18)
      .text((node: RenderNode) => node.label);

    nodeSelection.append("title").text((node: RenderNode) => `${node.type}: ${node.label}`);

    simulation.on("tick", () => {
      linkSelection
        .attr("x1", (link: RenderLink) => (typeof link.source === "string" ? 0 : link.source.x || 0))
        .attr("y1", (link: RenderLink) => (typeof link.source === "string" ? 0 : link.source.y || 0))
        .attr("x2", (link: RenderLink) => (typeof link.target === "string" ? 0 : link.target.x || 0))
        .attr("y2", (link: RenderLink) => (typeof link.target === "string" ? 0 : link.target.y || 0));

      labelSelection
        .attr("x", (link: RenderLink) => {
          const source = typeof link.source === "string" ? null : link.source;
          const target = typeof link.target === "string" ? null : link.target;
          return ((source?.x || 0) + (target?.x || 0)) / 2;
        })
        .attr("y", (link: RenderLink) => {
          const source = typeof link.source === "string" ? null : link.source;
          const target = typeof link.target === "string" ? null : link.target;
          return ((source?.y || 0) + (target?.y || 0)) / 2 - 6;
        });

      nodeSelection.attr("transform", (node: RenderNode) => `translate(${node.x || 0}, ${node.y || 0})`);
    });

    return () => {
      simulation.stop();
    };
  }, [links, mode, nodes, onSelectNode, selectedNodeId, size.height, size.width]);

  const selectedNode = nodes.find((node) => node.id === selectedNodeId) || null;
  const selectedGlow = selectedNode ? RISK_GLOWS[selectedNode.risk] || RISK_GLOWS.normal : RISK_GLOWS.focus;

  return (
    <div className="code-context-graph">
      <div className="code-context-graph__canvas" ref={containerRef} style={{ boxShadow: selectedGlow }}>
        <svg ref={svgRef} className="code-context-graph__svg" role="img" aria-label="Code context relationship graph" />
      </div>
    </div>
  );
}
