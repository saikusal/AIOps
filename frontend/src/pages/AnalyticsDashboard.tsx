/**
 * AnalyticsDashboard
 * ==================
 * Production-grade signal analytics page combining:
 *   - Signal Heatmap   — alert density across services × time
 *   - Correlated Timeline — alerts / incidents / executions on one axis
 *
 * The two views are linked: clicking a heatmap cell filters the timeline
 * to that service. Clicking a timeline event links back to the incident.
 *
 * Data is fetched via React Query with 30s auto-refresh.
 */

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import {
  fetchCorrelatedTimeline,
  fetchSignalHeatmap,
  type HeatmapCell,
  type TimelineEvent,
} from "../lib/api";
import { CorrelatedTimeline } from "../components/analytics/CorrelatedTimeline";
import { SignalHeatmap, type HeatmapTimeRange } from "../components/analytics/SignalHeatmap";

const DEFAULT_HEATMAP_RANGE: HeatmapTimeRange = { hours: 24, label: "24h", bucketMinutes: 60 };
const DEFAULT_TIMELINE_HOURS = 6;

export function AnalyticsDashboard() {
  const [heatmapRange, setHeatmapRange]   = useState<HeatmapTimeRange>(DEFAULT_HEATMAP_RANGE);
  const [timelineHours, setTimelineHours] = useState(DEFAULT_TIMELINE_HOURS);
  const [serviceFilter, setServiceFilter] = useState<string | null>(null);
  const [selectedEvent, setSelectedEvent] = useState<TimelineEvent | null>(null);

  // ------------------------------------------------------------------
  // Data fetching
  // ------------------------------------------------------------------
  const heatmapQuery = useQuery({
    queryKey: ["signal-heatmap", heatmapRange.hours, heatmapRange.bucketMinutes, serviceFilter],
    queryFn: () => fetchSignalHeatmap({
      hours: heatmapRange.hours,
      bucket_minutes: heatmapRange.bucketMinutes,
    }),
    refetchInterval: 30_000,
    staleTime: 15_000,
  });

  const timelineQuery = useQuery({
    queryKey: ["correlated-timeline", timelineHours, serviceFilter],
    queryFn: () => fetchCorrelatedTimeline({
      hours: timelineHours,
      service: serviceFilter ?? undefined,
    }),
    refetchInterval: 30_000,
    staleTime: 15_000,
  });

  // ------------------------------------------------------------------
  // Interaction handlers
  // ------------------------------------------------------------------
  const handleCellClick = (cell: HeatmapCell) => {
    setServiceFilter((cur) => cur === cell.service ? null : cell.service);
  };

  const handleEventClick = (event: TimelineEvent) => {
    setSelectedEvent((cur) => cur?.id === event.id ? null : event);
  };

  // ------------------------------------------------------------------
  // Summary stats from heatmap data
  // ------------------------------------------------------------------
  const heatmapMeta  = heatmapQuery.data?.meta;
  const timelineMeta = timelineQuery.data?.meta;

  const criticalCount = heatmapQuery.data?.cells
    .filter((c) => c.max_severity === "critical")
    .reduce((sum, c) => sum + c.count, 0) ?? 0;

  const execCount = timelineQuery.data?.events
    .filter((e) => e.type === "execution")
    .length ?? 0;

  const breakGlassCount = timelineQuery.data?.events
    .filter((e) => e.meta?.break_glass)
    .length ?? 0;

  const openIncidents = timelineQuery.data?.events
    .filter((e) => e.type === "incident_opened")
    .length ?? 0;

  return (
    <>
      {/* Hero */}
      <section className="hero-card">
        <div className="eyebrow">Signal Analytics</div>
        <h2>Alert Density &amp; Correlated Events</h2>
        <p>
          Real-time heatmap of alert density across all services, correlated with
          incident opens, remediations, and break-glass activations.
        </p>
        <div className="hero-card__grid">
          <div className="hero-card__chip">
            {heatmapMeta?.total_alerts.toLocaleString() ?? "—"} alerts
          </div>
          <div className="hero-card__chip">
            {heatmapMeta?.service_count ?? "—"} services
          </div>
          <div className="hero-card__chip">
            {timelineMeta?.event_count ?? "—"} timeline events
          </div>
          {breakGlassCount > 0 && (
            <div className="hero-card__chip" style={{ color: "#7c3aed" }}>
              {breakGlassCount} break-glass
            </div>
          )}
        </div>
        {serviceFilter && (
          <div className="page-card__meta">
            <span style={{ fontSize: 12, color: "#8cf4ff" }}>
              Filtered to: <strong>{serviceFilter}</strong>
            </span>
            <button
              onClick={() => setServiceFilter(null)}
              style={{
                marginLeft: 8, fontSize: 11, color: "#64748b",
                background: "none", border: "none", cursor: "pointer",
              }}
            >
              Clear filter ×
            </button>
          </div>
        )}
      </section>

      {/* Summary stat cards */}
      <section className="investigation-summary-grid">
        <article className={`fleet-summary-card fleet-summary-card--${criticalCount > 0 ? "critical" : "healthy"}`}>
          <span>Critical Alerts</span>
          <strong>{criticalCount.toLocaleString()}</strong>
          <p>
            {criticalCount > 0
              ? "Critical-severity alerts firing in the selected window."
              : "No critical alerts in the selected window."}
          </p>
        </article>

        <article className="fleet-summary-card fleet-summary-card--accent">
          <span>Open Incidents</span>
          <strong>{openIncidents}</strong>
          <p>Incidents opened in the timeline window.</p>
        </article>

        <article className="fleet-summary-card fleet-summary-card--primary">
          <span>Remediations</span>
          <strong>{execCount}</strong>
          <p>Execution intents dispatched via EGAP in the timeline window.</p>
        </article>

        <article className={`fleet-summary-card fleet-summary-card--${breakGlassCount > 0 ? "warning" : "primary"}`}>
          <span>Break-Glass</span>
          <strong>{breakGlassCount}</strong>
          <p>
            {breakGlassCount > 0
              ? "Policy bypasses activated — review audit trail."
              : "No break-glass activations."}
          </p>
        </article>
      </section>

      {/* Heatmap panel */}
      <section className="page-card" style={{ marginBottom: 0 }}>
        <div className="fleet-card__top">
          <div>
            <div className="eyebrow">Services × Time</div>
            <h3>Signal Heatmap</h3>
            <p>
              Each cell represents the alert count for one service in one time
              bucket. Color intensity and hue encode count and peak severity.
              Click a cell to filter the timeline below.
            </p>
          </div>
        </div>

        {heatmapQuery.isError && (
          <div style={{ color: "#ff8f95", fontSize: 13, marginBottom: 12 }}>
            Failed to load heatmap data.
          </div>
        )}

        <SignalHeatmap
          data={heatmapQuery.data ?? null}
          loading={heatmapQuery.isFetching}
          timeRange={heatmapRange}
          onTimeRangeChange={setHeatmapRange}
          onCellClick={handleCellClick}
          selectedService={serviceFilter}
        />
      </section>

      {/* Timeline panel */}
      <section className="page-card">
        <div className="fleet-card__top">
          <div>
            <div className="eyebrow">Multi-source Event Stream</div>
            <h3>Correlated Timeline</h3>
            <p>
              Alerts, incident opens/closes, and execution intents on a shared
              time axis. Dashed connectors link events to the incident they
              belong to. Drag the axis to zoom. Click any event for detail.
            </p>
          </div>
        </div>

        {timelineQuery.isError && (
          <div style={{ color: "#ff8f95", fontSize: 13, marginBottom: 12 }}>
            Failed to load timeline data.
          </div>
        )}

        <CorrelatedTimeline
          data={timelineQuery.data ?? null}
          loading={timelineQuery.isFetching}
          hours={timelineHours}
          onHoursChange={setTimelineHours}
          onEventClick={handleEventClick}
          filterService={serviceFilter}
        />
      </section>

      {/* Selected event action strip */}
      {selectedEvent?.incident_key && (
        <section className="page-card" style={{
          background: "rgba(255,210,122,0.04)",
          border: "1px solid rgba(255,210,122,0.2)",
        }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12 }}>
            <div>
              <div style={{ fontSize: 11, color: "#64748b", textTransform: "uppercase", letterSpacing: "0.07em" }}>
                Selected event
              </div>
              <div style={{ fontWeight: 700, color: "#ffd27a", marginTop: 2 }}>
                {selectedEvent.title}
              </div>
              <div style={{ fontSize: 12, color: "#94a3b8", marginTop: 2 }}>
                {selectedEvent.service} · {new Date(selectedEvent.timestamp).toLocaleString()}
              </div>
            </div>
            <div style={{ display: "flex", gap: 8, flexShrink: 0 }}>
              <Link
                to={`/incidents?incident=${encodeURIComponent(selectedEvent.incident_key)}`}
                className="shell__link shell__link--small"
              >
                Open Incident
              </Link>
              <button
                onClick={() => setSelectedEvent(null)}
                style={{
                  background: "none", border: "1px solid rgba(255,255,255,0.1)",
                  borderRadius: 4, color: "#64748b", cursor: "pointer",
                  padding: "4px 10px", fontSize: 12,
                }}
              >
                Dismiss
              </button>
            </div>
          </div>
        </section>
      )}
    </>
  );
}
