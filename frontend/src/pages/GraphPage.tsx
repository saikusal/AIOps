import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { GraphScene, type SceneNode } from "../components/graph/GraphScene";
import { fetchApplicationGraph, fetchIncidentGraph, fetchRecentAlerts, type GraphPayload } from "../lib/api";
import { useRefreshInterval } from "../lib/refresh";

function graphTitle(graph: GraphPayload) {
  if (graph.graph_type === "application") return "Application Topology";
  if (graph.graph_type === "incident") return "Incident Blast Radius";
  return "Neural Dependency Map";
}

export function GraphPage() {
  const { alertId, incidentKey, applicationKey } = useParams();
  const [selectedNode, setSelectedNode] = useState<SceneNode | null>(null);
  const { refreshMs } = useRefreshInterval();

  const alertQuery = useQuery({
    queryKey: ["recent-alerts"],
    queryFn: fetchRecentAlerts,
    refetchInterval: refreshMs,
    enabled: Boolean(alertId) || (!incidentKey && !applicationKey),
  });

  const incidentGraphQuery = useQuery({
    queryKey: ["incident-graph", incidentKey],
    queryFn: () => fetchIncidentGraph(incidentKey!),
    refetchInterval: refreshMs,
    enabled: Boolean(incidentKey),
  });

  const applicationGraphQuery = useQuery({
    queryKey: ["application-graph", applicationKey],
    queryFn: () => fetchApplicationGraph(applicationKey!),
    refetchInterval: refreshMs,
    enabled: Boolean(applicationKey),
  });

  const selectedAlert = (alertQuery.data || []).find((item) => item.alert_id === alertId) || (alertQuery.data || [])[0] || null;
  const alertGraph = useMemo<GraphPayload | null>(() => {
    if (!selectedAlert) return null;
    const root = selectedAlert.target_host || selectedAlert.alert_name || "incident";
    const nodes = [
      {
        id: root,
        label: root,
        service: root,
        kind: "service",
        status: selectedAlert.status || "unknown",
        role: "root_cause",
        depends_on: selectedAlert.depends_on || [],
        dependents: selectedAlert.blast_radius || [],
        ai_insight: selectedAlert.initial_ai_diagnosis || selectedAlert.summary || "",
      },
      ...(selectedAlert.depends_on || []).map((node) => ({
        id: node,
        label: node,
        service: node,
        kind: "dependency",
        status: "healthy",
        role: "dependency",
        depends_on: [],
        dependents: [root],
        ai_insight: `${node} is an upstream dependency.`,
      })),
      ...(selectedAlert.blast_radius || []).map((node) => ({
        id: node,
        label: node,
        service: node,
        kind: "service",
        status: selectedAlert.status === "resolved" ? "healthy" : "degraded",
        role: "impacted",
        depends_on: [root],
        dependents: [],
        ai_insight: `${node} is inside the current blast radius.`,
      })),
    ];
    const edges = [
      ...(selectedAlert.depends_on || []).map((node) => ({
        id: `${root}->${node}`,
        source: root,
        target: node,
        relationship: "depends_on",
      })),
      ...(selectedAlert.blast_radius || []).map((node) => ({
        id: `${node}->${root}`,
        source: node,
        target: root,
        relationship: "impacted_by",
      })),
    ];
    return {
      graph_type: "alert",
      key: selectedAlert.alert_id,
      title: selectedAlert.alert_name,
      summary: selectedAlert.initial_ai_diagnosis || selectedAlert.summary || "Alert graph view",
      status: selectedAlert.status || "unknown",
      root_node_id: root,
      nodes,
      edges,
      blast_radius: selectedAlert.blast_radius || [],
      evidence: {
        reasoning: selectedAlert.initial_ai_reasoning || "",
        post_command_ai_analysis: selectedAlert.post_command_ai_analysis || "",
      },
    };
  }, [selectedAlert]);

  const graph = applicationGraphQuery.data || incidentGraphQuery.data || alertGraph;
  const activeQuery =
    applicationKey ? applicationGraphQuery : incidentKey ? incidentGraphQuery : alertQuery;

  const graphNarrative = useMemo(() => {
    if (!graph) return null;
    const root = graph.nodes.find((node) => node.id === graph.root_node_id) || graph.nodes[0];
    return {
      root: root?.label || "unknown",
      dependencies: graph.nodes.filter((node) => node.role === "dependency").map((node) => node.label),
      impacted: graph.nodes.filter((node) => node.role === "impacted").map((node) => node.label),
    };
  }, [graph]);

  return (
    <>
      <section className="hero-card hero-card--graph hero-card--topology">
        <div className="eyebrow">Immersive Graph System</div>
        <h2>{graph ? graphTitle(graph) : "Topology Explorer"}</h2>
        <p>
          Explore topology, blast radius, and incident propagation from a single graph workspace built on live platform context.
        </p>
        <div className="hero-card__grid">
          <div className="hero-card__chip">Three.js</div>
          <div className="hero-card__chip">React Three Fiber</div>
          <div className="hero-card__chip">Application graph API</div>
          <div className="hero-card__chip">Incident graph API</div>
        </div>
      </section>

      {activeQuery.isLoading ? (
        <section className="page-card">
          <div className="eyebrow">Loading</div>
          <h2>Fetching graph context</h2>
          <p>The frontend is waiting on the graph APIs.</p>
        </section>
      ) : activeQuery.isError || !graph ? (
        <section className="page-card">
          <div className="eyebrow">Error</div>
          <h2>Unable to load graph data</h2>
          <p>Check that the Django backend is running and that graph data exists for the selected application or incident.</p>
        </section>
      ) : (
        <>
          <section className="graph3d-header">
            <div className="graph3d-header__left">
              <div className="eyebrow">Graph Lens</div>
              <h2>{graph.title}</h2>
              <p>{graph.summary}</p>
              <div className="page-card__meta">
                <Link className="shell__link shell__link--small" to={graph.graph_type === "application" ? `/assistant?application=${encodeURIComponent(graph.key)}` : `/assistant?incident=${encodeURIComponent(graph.key)}`}>
                  Investigate In Assistant
                </Link>
                <Link className="shell__link shell__link--small" to="/incidents">
                  Open Incidents
                </Link>
                <Link className="shell__link shell__link--small" to="/applications">
                  Open Applications
                </Link>
              </div>
            </div>
            <div className="graph3d-header__stats">
              <div className="graph3d-stat">
                <span>Status</span>
                <strong>{graph.status || "unknown"}</strong>
              </div>
              <div className="graph3d-stat">
                <span>Root Cause</span>
                <strong>{graphNarrative?.root || "unknown"}</strong>
              </div>
              <div className="graph3d-stat">
                <span>Blast Radius</span>
                <strong>{graph.blast_radius?.length || 0}</strong>
              </div>
            </div>
          </section>

          <GraphScene graph={graph} activeNodeId={selectedNode?.id || null} onSelectNode={(node) => setSelectedNode(node)} />

          <section className="graph3d-panel-grid">
            <section className="page-card">
              <div className="eyebrow">Reasoning Path</div>
              <h2>Operational Story</h2>
              <p>{String(graph.evidence?.reasoning || graph.summary || "No reasoning was recorded for this graph yet.")}</p>
              <div className="page-card__meta">
                <code>root:{graphNarrative?.root}</code>
                {(graphNarrative?.dependencies || []).map((node) => (
                  <code key={`dep-${node}`}>dependency:{node}</code>
                ))}
                {(graphNarrative?.impacted || []).map((node) => (
                  <code key={`impact-${node}`}>impacted:{node}</code>
                ))}
              </div>
            </section>
            <section className="page-card">
              <div className="eyebrow">Node Inspector</div>
              <h2>{selectedNode?.label || graphNarrative?.root || "Focus Node"}</h2>
              <p>
                {selectedNode?.description ||
                  "Select a node in the graph to inspect why it participates in the incident chain and how it contributes to the blast radius."}
              </p>
              <div className="graph3d-inspector-grid">
                <div className="graph3d-inspector-stat">
                  <span>Type</span>
                  <strong>{selectedNode?.type || "root_cause"}</strong>
                </div>
                <div className="graph3d-inspector-stat">
                  <span>Graph Type</span>
                  <strong>{graph.graph_type}</strong>
                </div>
                <div className="graph3d-inspector-stat">
                  <span>Status</span>
                  <strong>{graph.status || "unknown"}</strong>
                </div>
                <div className="graph3d-inspector-stat">
                  <span>Nodes</span>
                  <strong>{graph.nodes.length}</strong>
                </div>
              </div>
            </section>
            <section className="page-card">
              <div className="eyebrow">Evidence Stack</div>
              <h2>AI Readout</h2>
              <div className="graph3d-evidence-list">
                <article className="graph3d-evidence-item">
                  <strong>Summary</strong>
                  <p>{graph.summary || "No summary available."}</p>
                </article>
                <article className="graph3d-evidence-item">
                  <strong>Post-Command Analysis</strong>
                  <p>{String(graph.evidence?.post_command_ai_analysis || "No post-command analysis recorded yet.")}</p>
                </article>
                <article className="graph3d-evidence-item">
                  <strong>Blast Radius</strong>
                  <p>{(graph.blast_radius || []).join(", ") || "No blast radius recorded."}</p>
                </article>
              </div>
            </section>
          </section>
        </>
      )}
    </>
  );
}
