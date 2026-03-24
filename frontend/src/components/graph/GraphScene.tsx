import { Html, Line, OrbitControls, Stars } from "@react-three/drei";
import { Canvas } from "@react-three/fiber";
import { useMemo, useState } from "react";
import * as THREE from "three";
import type { GraphPayload } from "../../lib/api";

export type SceneNode = {
  id: string;
  label: string;
  type: "root_cause" | "dependency" | "impacted" | "service" | "mesh";
  position: [number, number, number];
  description?: string;
};

type SceneLink = {
  id: string;
  from: SceneNode;
  to: SceneNode;
  color: string;
  width: number;
  opacity: number;
};

type GraphSceneProps = {
  graph: GraphPayload;
  activeNodeId?: string | null;
  onSelectNode?: (node: SceneNode) => void;
};

function seededRandom(seed: string) {
  let state = 0;
  for (let index = 0; index < seed.length; index += 1) {
    state = ((state * 31) + seed.charCodeAt(index)) >>> 0;
  }

  return function next() {
    state = (1664525 * state + 1013904223) >>> 0;
    return state / 4294967296;
  };
}

function buildScene(graph: GraphPayload) {
  const random = seededRandom(graph.key || graph.title);
  const rootId = graph.root_node_id || graph.nodes[0]?.id || "root";
  const rootSource = graph.nodes.find((node) => node.id === rootId) || graph.nodes[0];

  const rootNode: SceneNode = {
    id: rootSource?.id || "root",
    label: rootSource?.label || "root",
    type: "root_cause",
    position: [0, 0, 0],
    description: graph.summary,
  };

  const dependencySources = graph.nodes.filter((node) => node.id !== rootNode.id && (node.role === "dependency" || (node.depends_on || []).length === 0));
  const impactedSources = graph.nodes.filter((node) => node.id !== rootNode.id && node.role === "impacted");
  const neutralSources = graph.nodes.filter((node) => node.id !== rootNode.id && !dependencySources.includes(node) && !impactedSources.includes(node));

  const dependencyNodes: SceneNode[] = dependencySources.map((node, index, list) => {
    const progress = list.length === 1 ? 0.5 : index / Math.max(list.length - 1, 1);
    return {
      id: node.id,
      label: node.label,
      type: "dependency",
      position: [
        -3.8,
        THREE.MathUtils.lerp(1.7, -1.7, progress),
        THREE.MathUtils.lerp(-0.24, 0.24, random()),
      ],
      description: node.ai_insight || `${node.label} is an upstream dependency in this graph.`,
    };
  });

  const impactedNodes: SceneNode[] = impactedSources.map((node, index, list) => {
    const progress = list.length === 1 ? 0.5 : index / Math.max(list.length - 1, 1);
    return {
      id: node.id,
      label: node.label,
      type: "impacted",
      position: [
        3.8,
        THREE.MathUtils.lerp(1.7, -1.7, progress),
        THREE.MathUtils.lerp(-0.24, 0.24, random()),
      ],
      description: node.ai_insight || `${node.label} is currently inside the blast radius.`,
    };
  });

  const serviceNodes: SceneNode[] = neutralSources.map((node, index, list) => {
    const angle = THREE.MathUtils.lerp(-1.1, 1.1, list.length === 1 ? 0.5 : index / Math.max(list.length - 1, 1));
    const radius = 2.6 + random() * 0.8;
    return {
      id: node.id,
      label: node.label,
      type: "service",
      position: [Math.cos(angle) * radius * 0.58, Math.sin(angle) * radius * 0.96, THREE.MathUtils.lerp(-0.16, 0.16, random())],
      description: node.ai_insight || `${node.label} is part of the current graph context.`,
    };
  });

  const meshNodes: SceneNode[] = Array.from({ length: 28 }, (_, index) => {
    const angle = random() * Math.PI * 2;
    const radius = 1.2 + Math.pow(random(), 0.88) * 4.2;
    return {
      id: `mesh-${index}`,
      label: `mesh-${index}`,
      type: "mesh",
      position: [Math.cos(angle) * radius * 1.1, Math.sin(angle) * radius * 0.92, THREE.MathUtils.lerp(-0.3, 0.3, random())],
    };
  });

  const visibleNodes = [rootNode, ...dependencyNodes, ...serviceNodes, ...impactedNodes];
  const visibleNodeMap = new Map(visibleNodes.map((node) => [node.id, node]));

  const links: SceneLink[] = graph.edges
    .map((edge) => {
      const source = visibleNodeMap.get(edge.source);
      const target = visibleNodeMap.get(edge.target);
      if (!source || !target) {
        return null;
      }
      const touchesRoot = source.id === rootNode.id || target.id === rootNode.id;
      return {
        id: edge.id,
        from: source,
        to: target,
        color: touchesRoot ? "#8df4ff" : target.type === "impacted" ? "#ff9d9d" : "#2bc9ff",
        width: touchesRoot ? 1.8 : 1,
        opacity: touchesRoot ? 0.92 : 0.34,
      } satisfies SceneLink;
    })
    .filter((item): item is SceneLink => Boolean(item));

  for (let index = 0; index < meshNodes.length; index += 1) {
    const from = meshNodes[index];
    const candidates = meshNodes
      .filter((candidate) => candidate.id !== from.id)
      .map((candidate) => ({
        candidate,
        distance: new THREE.Vector3(...from.position).distanceTo(new THREE.Vector3(...candidate.position)),
      }))
      .sort((left, right) => left.distance - right.distance)
      .slice(0, 3);

    candidates.forEach(({ candidate }, innerIndex) => {
      if (from.id < candidate.id) {
        links.push({
          id: `${from.id}-${candidate.id}-${innerIndex}`,
          from,
          to: candidate,
          color: "#1fa6d8",
          width: 0.65,
          opacity: 0.2,
        });
      }
    });
  }

  visibleNodes.filter((node) => node.type !== "root_cause").forEach((node, index) => {
    const meshNode = meshNodes[index % meshNodes.length];
    links.push({
      id: `${node.id}-${meshNode.id}`,
      from: node,
      to: meshNode,
      color: node.type === "impacted" ? "#ffb1b1" : "#30cfff",
      width: 0.8,
      opacity: 0.22,
    });
  });

  return { rootNode, visibleNodes, meshNodes, links };
}

function getCenteredPosition(position: [number, number, number], center: [number, number, number]): [number, number, number] {
  return [position[0] - center[0], position[1] - center[1], position[2] - center[2]];
}

function computeSceneCenter(nodes: SceneNode[]): [number, number, number] {
  if (!nodes.length) return [0, 0, 0];

  let minX = Number.POSITIVE_INFINITY;
  let maxX = Number.NEGATIVE_INFINITY;
  let minY = Number.POSITIVE_INFINITY;
  let maxY = Number.NEGATIVE_INFINITY;
  let minZ = Number.POSITIVE_INFINITY;
  let maxZ = Number.NEGATIVE_INFINITY;

  nodes.forEach((node) => {
    minX = Math.min(minX, node.position[0]);
    maxX = Math.max(maxX, node.position[0]);
    minY = Math.min(minY, node.position[1]);
    maxY = Math.max(maxY, node.position[1]);
    minZ = Math.min(minZ, node.position[2]);
    maxZ = Math.max(maxZ, node.position[2]);
  });

  return [(minX + maxX) / 2, (minY + maxY) / 2, (minZ + maxZ) / 2];
}

function linkTouchesNode(link: SceneLink, nodeId?: string | null) {
  return nodeId ? link.from.id === nodeId || link.to.id === nodeId : false;
}

function NodeGlow({
  node,
  isDimmed,
  isActive,
  showLabel,
  onSelect,
  onHover,
}: {
  node: SceneNode;
  isDimmed: boolean;
  isActive: boolean;
  showLabel: boolean;
  onSelect?: (node: SceneNode) => void;
  onHover?: (node: SceneNode | null) => void;
}) {
  if (node.type === "mesh") return null;

  const color =
    node.type === "root_cause"
      ? "#ff9d9d"
      : node.type === "dependency"
        ? "#46d7ff"
        : node.type === "impacted"
          ? "#ffb7b7"
          : "#8df4ff";

  const scale = node.type === "root_cause" ? 0.58 : 0.34;
  const opacity = isDimmed ? 0.22 : isActive ? 1 : 0.86;
  const glowOpacity = isDimmed ? 0.04 : isActive ? 0.22 : 0.12;

  return (
    <group
      position={node.position}
      onClick={() => onSelect?.(node)}
      onPointerOver={(event) => {
        event.stopPropagation();
        onHover?.(node);
      }}
      onPointerOut={(event) => {
        event.stopPropagation();
        onHover?.(null);
      }}
    >
      <mesh>
        <sphereGeometry args={[scale, 24, 24]} />
        <meshBasicMaterial color={color} transparent opacity={opacity} />
      </mesh>
      <mesh>
        <sphereGeometry args={[scale * 1.8, 24, 24]} />
        <meshBasicMaterial color={color} transparent opacity={glowOpacity} />
      </mesh>
      {showLabel ? (
        <Html position={[0, scale + 0.6, 0]} center distanceFactor={11}>
          <div className={`graph3d-node graph3d-node--${node.type}${isActive ? " is-active" : ""}${isDimmed ? " is-dimmed" : ""}`}>
            <div className="graph3d-node__title">{node.label}</div>
            <div className="graph3d-node__meta">
              {node.type === "root_cause"
                ? "Root Cause"
                : node.type === "dependency"
                  ? "Dependency"
                  : node.type === "impacted"
                    ? "Blast Radius"
                    : "Service"}
            </div>
          </div>
        </Html>
      ) : null}
    </group>
  );
}

function MeshPoint({ node, isDimmed }: { node: SceneNode; isDimmed: boolean }) {
  return (
    <mesh position={node.position}>
      <sphereGeometry args={[0.035, 12, 12]} />
      <meshBasicMaterial color="#31c2ee" transparent opacity={isDimmed ? 0.12 : 0.72} />
    </mesh>
  );
}

function GraphSceneContent({ graph, activeNodeId, onSelectNode }: GraphSceneProps) {
  const scene = useMemo(() => buildScene(graph), [graph]);
  const [hoveredNodeId, setHoveredNodeId] = useState<string | null>(null);
  const highlightedNodeId = hoveredNodeId || activeNodeId || scene.rootNode.id;
  const sceneCenter = useMemo(
    () => computeSceneCenter([...scene.visibleNodes, ...scene.meshNodes]),
    [scene.meshNodes, scene.visibleNodes],
  );
  const connectedNodeIds = new Set<string>([
    highlightedNodeId,
    ...scene.links
      .filter((link) => linkTouchesNode(link, highlightedNodeId))
      .flatMap((link) => [link.from.id, link.to.id]),
  ]);

  return (
    <>
      <color attach="background" args={["#02080d"]} />
      <fog attach="fog" args={["#02080d", 8, 18]} />
      <ambientLight intensity={0.52} />
      <pointLight position={[0, 0, 5]} intensity={16} color="#53c4ff" />
      <pointLight position={[0, 0, 3]} intensity={10} color="#ffb3b3" />
      <Stars radius={22} depth={18} count={320} factor={2.2} saturation={0} fade speed={0.1} />

      <mesh position={[0, 0, -3]}>
        <planeGeometry args={[22, 16]} />
        <meshBasicMaterial color="#09202a" transparent opacity={0.35} />
      </mesh>

      {scene.links.map((link) => (
        <Line
          key={link.id}
          points={[getCenteredPosition(link.from.position, sceneCenter), getCenteredPosition(link.to.position, sceneCenter)]}
          color={linkTouchesNode(link, highlightedNodeId) ? "#8df4ff" : link.color}
          lineWidth={linkTouchesNode(link, highlightedNodeId) ? link.width * 1.8 : link.width}
          transparent
          opacity={linkTouchesNode(link, highlightedNodeId) ? 0.95 : connectedNodeIds.has(link.from.id) || connectedNodeIds.has(link.to.id) ? link.opacity : link.opacity * 0.24}
        />
      ))}

      {scene.meshNodes.map((node) => (
        <MeshPoint
          key={node.id}
          node={{ ...node, position: getCenteredPosition(node.position, sceneCenter) }}
          isDimmed={Boolean(activeNodeId) && !connectedNodeIds.has(node.id)}
        />
      ))}

      {scene.visibleNodes.map((node) => (
        <NodeGlow
          key={node.id}
          node={{ ...node, position: getCenteredPosition(node.position, sceneCenter) }}
          isActive={node.id === highlightedNodeId}
          isDimmed={!connectedNodeIds.has(node.id)}
          showLabel={node.id === highlightedNodeId && Boolean(hoveredNodeId || activeNodeId)}
          onSelect={onSelectNode}
          onHover={(hovered) => setHoveredNodeId(hovered?.id || null)}
        />
      ))}

      <OrbitControls target={[0, 0, 0]} enablePan={false} minDistance={9.5} maxDistance={14} autoRotate={false} maxPolarAngle={Math.PI / 2.02} minPolarAngle={Math.PI / 2.9} />
    </>
  );
}

export function GraphScene({ graph, activeNodeId, onSelectNode }: GraphSceneProps) {
  return (
    <div className="graph3d-shell">
      <Canvas camera={{ position: [0, 0.1, 12.8], fov: 30 }}>
        <GraphSceneContent graph={graph} activeNodeId={activeNodeId} onSelectNode={onSelectNode} />
      </Canvas>
    </div>
  );
}
