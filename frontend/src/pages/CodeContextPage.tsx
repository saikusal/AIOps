import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import { CodeContextGraph } from "../components/code-context/CodeContextGraph";
import {
  fetchCodeContextGraph,
  type CodeContextGraphNode,
  type CodeContextRepositoryOption,
} from "../lib/api";
import { useRefreshQueryOptions } from "../lib/refresh";

type GraphMode = "landscape" | "runtime" | "changes";

const modeOptions: Array<{ value: GraphMode; label: string; description: string }> = [
  { value: "landscape", label: "Landscape", description: "Application, repo, runtime, and recent change paths together." },
  { value: "runtime", label: "Runtime Lens", description: "Focus on services, routes, spans, and implementation files." },
  { value: "changes", label: "Change Lens", description: "Focus on recent commits and the files they touched." },
];

function summarizeNode(node: CodeContextGraphNode | null) {
  if (!node) {
    return "Select a node to inspect ownership, implementation, trace mapping, and recent change context.";
  }
  if (node.type === "application") return "Application-level anchor for the indexed codebase and its mapped operational services.";
  if (node.type === "repository") return "Indexed source repository powering the selected application.";
  if (node.type === "service") return "Runtime service mapped to this repository through code-context bindings.";
  if (node.type === "route") return "HTTP route mapped to a handler in the indexed codebase.";
  if (node.type === "span") return "Trace span linked to a symbol or implementation file.";
  if (node.type === "file") return "Source file participating in route handling, span mapping, or dependency relations.";
  if (node.type === "change") return "Recent git change linked to touched files inside this codebase.";
  return "Operational code-context node.";
}

function formatIndexedAt(option?: CodeContextRepositoryOption | null) {
  if (!option?.indexed_at) return "Not indexed yet";
  const date = new Date(option.indexed_at);
  if (Number.isNaN(date.getTime())) return option.indexed_at;
  return date.toLocaleString();
}

function formatMetadataValue(value: unknown) {
  if (value === null || value === undefined || value === "") return "—";
  if (Array.isArray(value)) return value.join(", ") || "—";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

export function CodeContextPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [selectedNode, setSelectedNode] = useState<CodeContextGraphNode | null>(null);
  const [mode, setMode] = useState<GraphMode>("landscape");
  const refreshQueryOptions = useRefreshQueryOptions();

  const application = searchParams.get("application") || "";
  const repository = searchParams.get("repository") || "";

  const graphQuery = useQuery({
    queryKey: ["code-context-graph", application, repository],
    queryFn: () => fetchCodeContextGraph({ application, repository }),
    ...refreshQueryOptions,
  });

  const payload = graphQuery.data;

  useEffect(() => {
    setSelectedNode(null);
  }, [application, repository]);

  const activeRepository = useMemo(() => {
    if (!payload?.repository_options?.length) return null;
    return payload.repository_options.find((option) => option.name === payload.repository?.name) || payload.repository_options[0];
  }, [payload]);

  const selectedNodeEntries = useMemo(() => {
    if (!selectedNode) return [];
    return Object.entries(selectedNode.metadata || {}).filter(([, value]) => value !== null && value !== undefined && value !== "");
  }, [selectedNode]);

  return (
    <>
      <section className="hero-card hero-card--code-context">
        <div className="eyebrow">Source Intelligence Workspace</div>
        <h2>Code Context Graph</h2>
        <p>
          Connect live runtime entities to repository structure so incident analysis can move from service symptoms to handlers, spans, files, and recent changes.
        </p>
        <div className="hero-card__grid">
          <div className="hero-card__chip">D3 relationship graph</div>
          <div className="hero-card__chip">Service to repo mapping</div>
          <div className="hero-card__chip">Route and span resolution</div>
          <div className="hero-card__chip">Recent change overlay</div>
        </div>
      </section>

      <section className="code-context-header">
        <div className="code-context-header__controls">
          <label className="code-context-control">
            <span>Repository</span>
            <select
              value={payload?.repository?.name || repository}
              onChange={(event) => {
                const next = new URLSearchParams(searchParams);
                next.set("repository", event.target.value);
                next.delete("application");
                setSearchParams(next);
                setSelectedNode(null);
              }}
              disabled={!payload?.repository_options?.length}
            >
              {(payload?.repository_options || []).map((option) => (
                <option key={option.name} value={option.name}>
                  {option.name}
                </option>
              ))}
            </select>
          </label>
          <label className="code-context-control">
            <span>Application</span>
            <input value={payload?.application || application || "Unmapped"} readOnly />
          </label>
          <div className="code-context-header__actions">
            <Link className="shell__link shell__link--small" to={payload?.application ? `/genai?application=${encodeURIComponent(payload.application)}` : "/genai"}>
              Investigate In Assistant
            </Link>
            <Link className="shell__link shell__link--small" to="/topology">
              Open Topology
            </Link>
          </div>
        </div>
        <div className="code-context-header__stats">
          <div className="code-context-stat">
            <span>Services</span>
            <strong>{payload?.summary.service_count ?? 0}</strong>
          </div>
          <div className="code-context-stat">
            <span>Routes</span>
            <strong>{payload?.summary.route_count ?? 0}</strong>
          </div>
          <div className="code-context-stat">
            <span>Spans</span>
            <strong>{payload?.summary.span_count ?? 0}</strong>
          </div>
          <div className="code-context-stat">
            <span>Changes</span>
            <strong>{payload?.summary.change_count ?? 0}</strong>
          </div>
          <div className="code-context-stat">
            <span>Relations</span>
            <strong>{payload?.summary.relation_count ?? 0}</strong>
          </div>
        </div>
      </section>

      <section className="code-context-layout">
        <div className="code-context-main">
          <div className="code-context-mode-strip">
            {modeOptions.map((option) => (
              <button
                key={option.value}
                type="button"
                className={`code-context-mode${mode === option.value ? " is-active" : ""}`}
                onClick={() => setMode(option.value)}
              >
                <strong>{option.label}</strong>
                <span>{option.description}</span>
              </button>
            ))}
          </div>

          {graphQuery.isLoading ? (
            <section className="page-card">
              <div className="eyebrow">Loading</div>
              <h2>Building code graph</h2>
              <p>The React workspace is waiting on `/genai/code-context/graph/`.</p>
            </section>
          ) : graphQuery.isError || !payload ? (
            <section className="page-card">
              <div className="eyebrow">Error</div>
              <h2>Unable to load code context</h2>
              <p>Check that repository indexing has run and the backend graph endpoint is returning data.</p>
            </section>
          ) : payload.nodes.length === 0 ? (
            <section className="page-card">
              <div className="eyebrow">No Index</div>
              <h2>No indexed repository available</h2>
              <p>Register or auto-bootstrap a repository, then run the code-context sync so the graph can be built.</p>
            </section>
          ) : (
            <CodeContextGraph
              nodes={payload.nodes}
              links={payload.links}
              selectedNodeId={selectedNode?.id || null}
              mode={mode}
              onSelectNode={setSelectedNode}
            />
          )}
        </div>

        <aside className="code-context-sidepanel">
          <section className="page-card code-context-card">
            <div className="eyebrow">Index Status</div>
            <h2>{payload?.repository?.name || "Repository"}</h2>
            <p>{payload?.repository?.local_path || "No repository selected."}</p>
            <div className="code-context-mini-grid">
              <div>
                <span>Status</span>
                <strong>{payload?.repository?.index_status || "unknown"}</strong>
              </div>
              <div>
                <span>Default Branch</span>
                <strong>{payload?.repository?.default_branch || "main"}</strong>
              </div>
              <div>
                <span>Indexed At</span>
                <strong>{formatIndexedAt(activeRepository)}</strong>
              </div>
              <div>
                <span>Applications</span>
                <strong>{activeRepository?.application_names?.join(", ") || "—"}</strong>
              </div>
            </div>
          </section>

          <section className="page-card code-context-card">
            <div className="eyebrow">Node Inspector</div>
            <h2>{selectedNode?.label || "Select a graph node"}</h2>
            <p>{summarizeNode(selectedNode)}</p>
            <div className="code-context-inspector-meta">
              <div>
                <span>Type</span>
                <strong>{selectedNode?.type || "—"}</strong>
              </div>
              <div>
                <span>Risk</span>
                <strong>{selectedNode?.risk || "—"}</strong>
              </div>
            </div>
            <div className="code-context-metadata">
              {selectedNodeEntries.length ? (
                selectedNodeEntries.map(([key, value]) => (
                  <div key={key} className="code-context-metadata__row">
                    <span>{key}</span>
                    <strong>{formatMetadataValue(value)}</strong>
                  </div>
                ))
              ) : (
                <div className="code-context-metadata__empty">No node selected yet.</div>
              )}
            </div>
          </section>

          <section className="page-card code-context-card">
            <div className="eyebrow">Graph Legend</div>
            <h2>Relationship Types</h2>
            <div className="code-context-legend">
              <div><i className="is-application" />Application</div>
              <div><i className="is-repository" />Repository</div>
              <div><i className="is-service" />Service</div>
              <div><i className="is-route" />Route</div>
              <div><i className="is-span" />Span</div>
              <div><i className="is-file" />File</div>
              <div><i className="is-change" />Recent Change</div>
            </div>
          </section>
        </aside>
      </section>
    </>
  );
}
