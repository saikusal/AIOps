/**
 * CorrelatedTimeline
 * ==================
 * Production-grade D3 multi-lane event timeline.
 *
 * Layout:
 *   Three horizontal swim lanes — Alerts / Incidents / Executions
 *   Events are circles sized by significance and colored by severity
 *   Correlation connectors (quadratic Bézier) link alerts and executions
 *   to the incident they belong to, across lanes
 *
 * Interactions:
 *   - Brush for time-range zoom (drag on the axis area)
 *   - Click event to surface a detail panel
 *   - Hover tooltip
 *   - Service filter highlights matching events
 *
 * D3 pattern: fully imperative inside useEffect; React owns only state
 * and lifecycle. No React-D3 hybrid rendering (avoids double-render bugs).
 */

import * as d3 from "d3";
import { useEffect, useRef, useState } from "react";
import type {
  CorrelatedTimelineData,
  HeatmapSeverity,
  TimelineEvent,
} from "../../lib/api";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const MARGIN = { top: 12, right: 32, bottom: 48, left: 110 };
const LANE_HEIGHT = 90;
const LANE_PADDING = 12;
const EVENT_RADIUS_BASE = 5;

const SEVERITY_COLOR: Record<string, string> = {
  critical: "#ff4444",
  high:     "#ff8f95",
  warning:  "#ffd27a",
  info:     "#8cf4ff",
  unknown:  "#4b5563",
};

const LANE_BG: Record<string, string> = {
  alerts:     "rgba(255,143,149,0.04)",
  incidents:  "rgba(255,210,122,0.04)",
  executions: "rgba(163,255,203,0.05)",
};

const LANE_BORDER: Record<string, string> = {
  alerts:     "rgba(255,143,149,0.15)",
  incidents:  "rgba(255,210,122,0.15)",
  executions: "rgba(163,255,203,0.12)",
};

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type TooltipState = {
  visible: boolean;
  x: number;
  y: number;
  event: TimelineEvent | null;
};

interface Props {
  data: CorrelatedTimelineData | null;
  loading: boolean;
  hours: number;
  onHoursChange: (h: number) => void;
  onEventClick?: (event: TimelineEvent) => void;
  filterService?: string | null;
}

const HOUR_OPTIONS = [
  { label: "1h",  value: 1  },
  { label: "6h",  value: 6  },
  { label: "12h", value: 12 },
  { label: "24h", value: 24 },
  { label: "3d",  value: 72 },
];

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function CorrelatedTimeline({
  data,
  loading,
  hours,
  onHoursChange,
  onEventClick,
  filterService,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const svgRef       = useRef<SVGSVGElement>(null);
  const [tooltip, setTooltip]             = useState<TooltipState>({ visible: false, x: 0, y: 0, event: null });
  const [selectedEventId, setSelectedEventId] = useState<string | null>(null);
  const [containerWidth, setContainerWidth]   = useState(900);
  // Brush-selected time window: [Date, Date] | null
  const [brushDomain, setBrushDomain] = useState<[Date, Date] | null>(null);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const obs = new ResizeObserver((entries) => {
      const w = entries[0]?.contentRect.width;
      if (w && w > 0) setContainerWidth(w);
    });
    obs.observe(el);
    return () => obs.disconnect();
  }, []);

  useEffect(() => {
    const svg = d3.select(svgRef.current);
    svg.selectAll("*").remove();

    if (!data || data.events.length === 0) return;

    const lanes      = data.lanes;
    const allEvents  = data.events;
    const links      = data.links;

    const innerW = containerWidth - MARGIN.left - MARGIN.right;
    const innerH = lanes.length * (LANE_HEIGHT + LANE_PADDING);
    const totalH = innerH + MARGIN.top + MARGIN.bottom + 36; // +36 for brush

    svg
      .attr("width", containerWidth)
      .attr("height", totalH)
      .attr("viewBox", `0 0 ${containerWidth} ${totalH}`);

    // ------------------------------------------------------------------
    // Time domain
    // ------------------------------------------------------------------
    const now  = new Date();
    const from = new Date(now.getTime() - hours * 3600_000);
    const fullDomain: [Date, Date] = brushDomain ?? [from, now];

    const xScale = d3.scaleTime()
      .domain(fullDomain)
      .range([0, innerW])
      .clamp(true);

    // ------------------------------------------------------------------
    // Lane Y positions
    // ------------------------------------------------------------------
    const laneY = (laneId: string): number => {
      const idx = lanes.findIndex((l) => l.id === laneId);
      return (idx < 0 ? 0 : idx) * (LANE_HEIGHT + LANE_PADDING);
    };

    const g = svg.append("g").attr("transform", `translate(${MARGIN.left},${MARGIN.top})`);

    // ------------------------------------------------------------------
    // Lane backgrounds
    // ------------------------------------------------------------------
    lanes.forEach((lane) => {
      const y = laneY(lane.id);
      g.append("rect")
        .attr("x", 0).attr("y", y)
        .attr("width", innerW).attr("height", LANE_HEIGHT)
        .attr("rx", 4)
        .attr("fill", LANE_BG[lane.id] ?? "transparent")
        .attr("stroke", LANE_BORDER[lane.id] ?? "rgba(255,255,255,0.06)")
        .attr("stroke-width", 1);

      // Lane label
      g.append("text")
        .attr("x", -8).attr("y", y + LANE_HEIGHT / 2 + 4)
        .attr("text-anchor", "end")
        .attr("fill", lane.color)
        .attr("font-size", "12px")
        .attr("font-weight", "600")
        .text(lane.label);

      // Centre line
      g.append("line")
        .attr("x1", 0).attr("x2", innerW)
        .attr("y1", y + LANE_HEIGHT / 2).attr("y2", y + LANE_HEIGHT / 2)
        .attr("stroke", LANE_BORDER[lane.id] ?? "rgba(255,255,255,0.06)")
        .attr("stroke-dasharray", "3,6");
    });

    // ------------------------------------------------------------------
    // Filter + deduplicate events by position (cluster overlapping events)
    // ------------------------------------------------------------------
    const visibleEvents = allEvents.filter((ev) => {
      const t = new Date(ev.timestamp);
      return t >= fullDomain[0] && t <= fullDomain[1];
    });

    // Build id → event map for link rendering
    const eventById = new Map<string, TimelineEvent>();
    visibleEvents.forEach((ev) => eventById.set(ev.id, ev));

    // ------------------------------------------------------------------
    // Correlation connectors (draw first, under events)
    // ------------------------------------------------------------------
    const linkG = g.append("g").attr("class", "links");

    links.forEach((link) => {
      const src = eventById.get(link.source);
      const tgt = eventById.get(link.target);
      if (!src || !tgt) return;

      const x1 = xScale(new Date(src.timestamp));
      const x2 = xScale(new Date(tgt.timestamp));
      const y1 = laneY(src.lane) + LANE_HEIGHT / 2;
      const y2 = laneY(tgt.lane) + LANE_HEIGHT / 2;

      // Quadratic Bézier with midpoint control
      const mx = (x1 + x2) / 2;
      const my = (y1 + y2) / 2 - Math.abs(y2 - y1) * 0.4;

      linkG.append("path")
        .attr("d", `M${x1},${y1} Q${mx},${my} ${x2},${y2}`)
        .attr("fill", "none")
        .attr("stroke", "rgba(255,255,255,0.07)")
        .attr("stroke-width", 1)
        .attr("stroke-dasharray", "3,5")
        .attr("pointer-events", "none");
    });

    // ------------------------------------------------------------------
    // Events
    // ------------------------------------------------------------------
    const eventG = g.append("g").attr("class", "events");

    // Radius scale: incidents are larger
    const radiusFor = (ev: TimelineEvent): number => {
      if (ev.type === "incident_opened") return EVENT_RADIUS_BASE + 3;
      if (ev.severity === "critical")    return EVENT_RADIUS_BASE + 2;
      if (ev.type === "execution" && ev.meta?.break_glass) return EVENT_RADIUS_BASE + 2;
      return EVENT_RADIUS_BASE;
    };

    visibleEvents.forEach((ev) => {
      const cx = xScale(new Date(ev.timestamp));
      const cy = laneY(ev.lane) + LANE_HEIGHT / 2;
      const r  = radiusFor(ev);
      const color = SEVERITY_COLOR[ev.severity] ?? SEVERITY_COLOR.unknown;
      const isSelected = ev.id === selectedEventId;
      const isFiltered = filterService ? ev.service !== filterService : false;

      const circle = eventG.append("circle")
        .attr("cx", cx).attr("cy", cy).attr("r", r)
        .attr("fill", color)
        .attr("fill-opacity", isFiltered ? 0.15 : isSelected ? 1 : 0.7)
        .attr("stroke", isSelected ? "#fff" : "transparent")
        .attr("stroke-width", isSelected ? 1.5 : 0)
        .style("cursor", "pointer")
        .attr("data-id", ev.id);

      // Glow ring for selected / break-glass
      if (isSelected || ev.meta?.break_glass) {
        eventG.append("circle")
          .attr("cx", cx).attr("cy", cy)
          .attr("r", r + 4)
          .attr("fill", "none")
          .attr("stroke", color)
          .attr("stroke-opacity", 0.35)
          .attr("stroke-width", 2)
          .attr("pointer-events", "none");
      }

      // Resolved incident — diamond shape
      if (ev.type === "incident_resolved") {
        circle.attr("fill", "#22c55e").attr("fill-opacity", 0.8);
        // Draw checkmark indicator
        eventG.append("line")
          .attr("x1", cx - r * 0.5).attr("y1", cy)
          .attr("x2", cx).attr("y2", cy + r * 0.5)
          .attr("stroke", "#fff").attr("stroke-width", 1.2).attr("pointer-events", "none");
        eventG.append("line")
          .attr("x1", cx).attr("y1", cy + r * 0.5)
          .attr("x2", cx + r * 0.8).attr("y2", cy - r * 0.6)
          .attr("stroke", "#fff").attr("stroke-width", 1.2).attr("pointer-events", "none");
      }

      circle
        .on("mouseenter", function (event: MouseEvent) {
          d3.select(this).attr("fill-opacity", 1).attr("r", r + 2);
          const containerRect = containerRef.current?.getBoundingClientRect();
          if (containerRect) {
            setTooltip({
              visible: true,
              x: event.clientX - containerRect.left + 14,
              y: event.clientY - containerRect.top - 8,
              event: ev,
            });
          }
        })
        .on("mouseleave", function () {
          d3.select(this)
            .attr("fill-opacity", isFiltered ? 0.15 : isSelected ? 1 : 0.7)
            .attr("r", r);
          setTooltip((t) => ({ ...t, visible: false }));
        })
        .on("click", () => {
          setSelectedEventId((cur) => cur === ev.id ? null : ev.id);
          onEventClick?.(ev);
        });
    });

    // ------------------------------------------------------------------
    // X Axis
    // ------------------------------------------------------------------
    const axisY = innerH + 8;
    const tickFormat = (domainValue: d3.NumberValue | Date): string => {
      const d = domainValue instanceof Date ? domainValue : new Date(Number(domainValue));
      if (hours <= 6)  return d3.timeFormat("%-I:%M%p")(d);
      if (hours <= 24) return d3.timeFormat("%-I%p %b %-d")(d);
      return d3.timeFormat("%b %-d")(d);
    };

    g.append("g")
      .attr("transform", `translate(0,${axisY})`)
      .call(
        d3.axisBottom(xScale)
          .ticks(Math.min(8, innerW / 80))
          .tickFormat(tickFormat as (value: Date | d3.NumberValue, i: number) => string)
      )
      .call(gEl => {
        gEl.select(".domain").attr("stroke", "rgba(255,255,255,0.1)");
        gEl.selectAll(".tick line").attr("stroke", "rgba(255,255,255,0.08)");
        gEl.selectAll(".tick text").attr("fill", "#94a3b8").attr("font-size", "11px");
      });

    // ------------------------------------------------------------------
    // Brush for time-range zoom
    // ------------------------------------------------------------------
    const brushG = g.append("g").attr("transform", `translate(0,${axisY + 22})`);

    const brush = d3.brushX()
      .extent([[0, 0], [innerW, 14]])
      .on("end", (event: d3.D3BrushEvent<unknown>) => {
        if (!event.selection) {
          setBrushDomain(null);
          return;
        }
        const [x0, x1] = event.selection as [number, number];
        const d0 = xScale.invert(x0);
        const d1 = xScale.invert(x1);
        if (d1.getTime() - d0.getTime() > 60_000) {
          setBrushDomain([d0, d1]);
        }
      });

    brushG.call(brush);
    brushG.selectAll("rect.selection")
      .attr("fill", "rgba(59,130,246,0.25)")
      .attr("stroke", "rgba(59,130,246,0.5)");
    brushG.selectAll("rect.overlay")
      .attr("fill", "transparent");

    // Brush hint label
    brushG.append("text")
      .attr("x", innerW / 2).attr("y", 28)
      .attr("text-anchor", "middle")
      .attr("fill", "#334155")
      .attr("font-size", "10px")
      .text(brushDomain ? "← drag to adjust zoom · double-click to reset" : "drag to zoom");

    brushG.on("dblclick", () => setBrushDomain(null));

    // ------------------------------------------------------------------
    // Event count badges per lane
    // ------------------------------------------------------------------
    lanes.forEach((lane) => {
      const count = visibleEvents.filter((e) => e.lane === lane.id).length;
      if (count === 0) return;
      const y = laneY(lane.id);
      const badgeG = g.append("g").attr("transform", `translate(${innerW + 6},${y + 6})`);
      badgeG.append("rect")
        .attr("width", 28).attr("height", 16)
        .attr("rx", 8)
        .attr("fill", "rgba(255,255,255,0.06)")
        .attr("stroke", LANE_BORDER[lane.id]);
      badgeG.append("text")
        .attr("x", 14).attr("y", 11.5)
        .attr("text-anchor", "middle")
        .attr("fill", lane.color)
        .attr("font-size", "10px")
        .attr("font-weight", "600")
        .text(count > 99 ? "99+" : count);
    });

  }, [data, containerWidth, hours, brushDomain, selectedEventId, filterService, onEventClick]);

  const totalH = data
    ? data.lanes.length * (LANE_HEIGHT + LANE_PADDING) + MARGIN.top + MARGIN.bottom + 36
    : 320;

  return (
    <div style={{ position: "relative", width: "100%" }}>
      {/* Header */}
      <div style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        marginBottom: 12,
        flexWrap: "wrap",
        gap: 8,
      }}>
        <div>
          <span style={{ fontSize: 11, color: "#64748b", textTransform: "uppercase", letterSpacing: "0.08em" }}>
            Correlated Timeline
          </span>
          {data && (
            <span style={{ fontSize: 11, color: "#475569", marginLeft: 10 }}>
              {data.meta.event_count} events
            </span>
          )}
          {brushDomain && (
            <button
              onClick={() => setBrushDomain(null)}
              style={{
                marginLeft: 10, fontSize: 11, color: "#3b82f6",
                background: "none", border: "none", cursor: "pointer", padding: 0,
              }}
            >
              Reset zoom ×
            </button>
          )}
        </div>

        {/* Hour picker */}
        <div style={{ display: "flex", gap: 4 }}>
          {HOUR_OPTIONS.map((o) => (
            <button
              key={o.value}
              onClick={() => { onHoursChange(o.value); setBrushDomain(null); }}
              style={{
                padding: "3px 10px",
                fontSize: 12,
                borderRadius: 4,
                border: "1px solid",
                cursor: "pointer",
                borderColor: hours === o.value ? "#3b82f6" : "rgba(255,255,255,0.1)",
                background: hours === o.value ? "rgba(59,130,246,0.15)" : "transparent",
                color: hours === o.value ? "#93c5fd" : "#64748b",
                transition: "all 0.15s",
              }}
            >
              {o.label}
            </button>
          ))}
        </div>
      </div>

      {/* Chart */}
      <div ref={containerRef} style={{ position: "relative", width: "100%", minHeight: totalH }}>
        {loading && (
          <div style={{
            position: "absolute", inset: 0, display: "flex",
            alignItems: "center", justifyContent: "center",
            background: "rgba(15,23,42,0.7)", borderRadius: 6, zIndex: 10,
          }}>
            <span style={{ color: "#64748b", fontSize: 13 }}>Loading timeline…</span>
          </div>
        )}

        {!loading && (!data || data.events.length === 0) && (
          <div style={{
            display: "flex", alignItems: "center", justifyContent: "center",
            height: 200, color: "#475569", fontSize: 13,
          }}>
            No events in this time window.
          </div>
        )}

        <svg ref={svgRef} style={{ display: "block", width: "100%", overflow: "visible" }} />

        {/* Tooltip */}
        {tooltip.visible && tooltip.event && (
          <div style={{
            position: "absolute",
            left: tooltip.x,
            top: tooltip.y,
            pointerEvents: "none",
            background: "#1e293b",
            border: "1px solid rgba(255,255,255,0.12)",
            borderRadius: 6,
            padding: "10px 14px",
            fontSize: 12,
            color: "#e2e8f0",
            boxShadow: "0 8px 32px rgba(0,0,0,0.4)",
            minWidth: 200,
            maxWidth: 280,
            zIndex: 100,
          }}>
            <div style={{
              fontWeight: 700,
              marginBottom: 4,
              color: SEVERITY_COLOR[tooltip.event.severity] ?? "#f1f5f9",
              fontSize: 13,
            }}>
              {tooltip.event.title}
            </div>
            <div style={{ color: "#94a3b8", marginBottom: 6, fontSize: 11 }}>
              {new Date(tooltip.event.timestamp).toLocaleString()}
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 2, fontSize: 11 }}>
              <span><span style={{ color: "#64748b" }}>Service: </span>{tooltip.event.service}</span>
              {tooltip.event.environment && (
                <span><span style={{ color: "#64748b" }}>Env: </span>{tooltip.event.environment}</span>
              )}
              <span><span style={{ color: "#64748b" }}>Status: </span>{tooltip.event.status}</span>
              {tooltip.event.incident_key && (
                <span style={{ color: "#ffd27a", marginTop: 2 }}>
                  ↳ {tooltip.event.incident_key.slice(0, 8)}…
                </span>
              )}
              {Boolean(tooltip.event.meta?.break_glass) && (
                <span style={{ color: "#7c3aed", fontWeight: 600, marginTop: 2 }}>
                  ⚠ Break-glass activation
                </span>
              )}
              {Boolean(tooltip.event.meta?.command_preview) && (
                <code style={{
                  marginTop: 4, padding: "3px 6px",
                  background: "rgba(0,0,0,0.3)", borderRadius: 3, display: "block",
                  color: "#a3ffcb", fontSize: 10, wordBreak: "break-all",
                }}>
                  {tooltip.event.meta.command_preview as string}
                </code>
              )}
              {typeof tooltip.event.meta?.mttr_minutes === "number" && (
                <span style={{ color: "#22c55e", marginTop: 2 }}>
                  MTTR: {tooltip.event.meta.mttr_minutes}m
                </span>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Selected event detail strip */}
      {selectedEventId && (() => {
        const ev = data?.events.find((e) => e.id === selectedEventId);
        if (!ev) return null;
        return (
          <div style={{
            marginTop: 12,
            background: "rgba(255,255,255,0.03)",
            border: `1px solid ${SEVERITY_COLOR[ev.severity] ?? "rgba(255,255,255,0.1)"}`,
            borderRadius: 6,
            padding: "10px 14px",
            fontSize: 12,
            color: "#e2e8f0",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "flex-start",
            gap: 12,
          }}>
            <div>
              <div style={{ fontWeight: 700, marginBottom: 4, color: SEVERITY_COLOR[ev.severity] }}>
                {ev.title}
              </div>
              <div style={{ color: "#94a3b8" }}>
                {ev.service} · {new Date(ev.timestamp).toLocaleString()} · {ev.status}
              </div>
            </div>
            <button
              onClick={() => setSelectedEventId(null)}
              style={{
                background: "none", border: "none", color: "#64748b",
                cursor: "pointer", fontSize: 16, lineHeight: 1, flexShrink: 0,
              }}
            >×</button>
          </div>
        );
      })()}
    </div>
  );
}
