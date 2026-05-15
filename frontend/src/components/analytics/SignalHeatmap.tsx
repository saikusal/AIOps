/**
 * SignalHeatmap
 * =============
 * Production-grade D3 alert density heatmap.
 *
 * - Services on the Y axis (scaleBand)
 * - Time buckets on the X axis (scaleTime)
 * - Cell color encodes alert density × max severity
 * - Hover tooltip with breakdown
 * - Click a cell to filter the correlated timeline
 * - Time-range picker (1h / 6h / 24h / 7d)
 * - Responsive via ResizeObserver — rerenders cleanly on resize
 * - Entirely imperative D3 inside a useEffect; React manages lifecycle only
 */

import * as d3 from "d3";
import { useCallback, useEffect, useRef, useState } from "react";
import type { HeatmapCell, HeatmapData, HeatmapSeverity } from "../../lib/api";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const MARGIN = { top: 24, right: 32, bottom: 56, left: 148 };
const CELL_HEIGHT = 32;
const MIN_HEIGHT = 200;

const SEVERITY_BASE_COLOR: Record<HeatmapSeverity, string> = {
  critical: "#ff4444",
  high:     "#ff8f95",
  warning:  "#ffd27a",
  info:     "#8cf4ff",
  unknown:  "#4b5563",
};

// Density-adjusted interpolators: dark bg → severity color
const SEVERITY_INTERPOLATOR: Record<HeatmapSeverity, (t: number) => string> = {
  critical: d3.interpolateRgb("#0f172a", "#ff4444"),
  high:     d3.interpolateRgb("#0f172a", "#ff8f95"),
  warning:  d3.interpolateRgb("#0f172a", "#ffd27a"),
  info:     d3.interpolateRgb("#0f172a", "#8cf4ff"),
  unknown:  d3.interpolateRgb("#0f172a", "#4b5563"),
};

export type HeatmapTimeRange = { hours: number; label: string; bucketMinutes: number };

const TIME_RANGES: HeatmapTimeRange[] = [
  { hours: 1,   label: "1h",  bucketMinutes: 5  },
  { hours: 6,   label: "6h",  bucketMinutes: 15 },
  { hours: 24,  label: "24h", bucketMinutes: 60 },
  { hours: 168, label: "7d",  bucketMinutes: 360 },
];

// ---------------------------------------------------------------------------
// Tooltip state
// ---------------------------------------------------------------------------

type TooltipState = {
  visible: boolean;
  x: number;
  y: number;
  cell: HeatmapCell | null;
};

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface Props {
  data: HeatmapData | null;
  loading: boolean;
  timeRange: HeatmapTimeRange;
  onTimeRangeChange: (r: HeatmapTimeRange) => void;
  onCellClick?: (cell: HeatmapCell) => void;
  selectedService?: string | null;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function SignalHeatmap({
  data,
  loading,
  timeRange,
  onTimeRangeChange,
  onCellClick,
  selectedService,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const svgRef       = useRef<SVGSVGElement>(null);
  const [tooltip, setTooltip] = useState<TooltipState>({ visible: false, x: 0, y: 0, cell: null });
  const [containerWidth, setContainerWidth] = useState(800);

  // Track container width via ResizeObserver
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

  // Main D3 render effect
  useEffect(() => {
    const svg = d3.select(svgRef.current);
    svg.selectAll("*").remove();

    if (!data || data.services.length === 0) return;

    const services = data.services;
    const cells    = data.cells;
    const maxCount = data.meta.max_count || 1;

    const innerW = containerWidth - MARGIN.left - MARGIN.right;
    const innerH = Math.max(services.length * CELL_HEIGHT, MIN_HEIGHT);
    const totalH  = innerH + MARGIN.top + MARGIN.bottom;

    svg
      .attr("width", containerWidth)
      .attr("height", totalH)
      .attr("viewBox", `0 0 ${containerWidth} ${totalH}`);

    const g = svg.append("g").attr("transform", `translate(${MARGIN.left},${MARGIN.top})`);

    // ------------------------------------------------------------------
    // Scales
    // ------------------------------------------------------------------
    const now  = new Date();
    const from = new Date(now.getTime() - timeRange.hours * 60 * 60 * 1000);

    const xScale = d3.scaleTime()
      .domain([from, now])
      .range([0, innerW]);

    const yScale = d3.scaleBand()
      .domain(services)
      .range([0, innerH])
      .padding(0.08);

    // ------------------------------------------------------------------
    // Grid lines
    // ------------------------------------------------------------------
    g.append("g")
      .attr("class", "grid")
      .call(
        d3.axisLeft(yScale)
          .tickSize(-innerW)
          .tickFormat(() => "")
      )
      .call(gEl => {
        gEl.select(".domain").remove();
        gEl.selectAll(".tick line")
          .attr("stroke", "rgba(255,255,255,0.04)")
          .attr("stroke-dasharray", "2,4");
      });

    // ------------------------------------------------------------------
    // Cells
    // ------------------------------------------------------------------
    const bucketWidth = Math.max(
      2,
      innerW / (timeRange.hours * 60 / timeRange.bucketMinutes) - 1
    );

    g.selectAll<SVGRectElement, HeatmapCell>(".cell")
      .data(cells, (d) => `${d.service}|${d.bucket}`)
      .join(
        (enter) => enter.append("rect").attr("class", "cell").attr("rx", 2).attr("ry", 2),
      )
      .attr("x", (d) => xScale(new Date(d.bucket)))
      .attr("y", (d) => yScale(d.service) ?? 0)
      .attr("width", bucketWidth)
      .attr("height", yScale.bandwidth())
      .attr("fill", (d) => {
        const t = Math.min(d.count / maxCount, 1);
        // Boost low counts to stay visible
        const tAdjusted = t < 0.05 ? 0.15 : t;
        return SEVERITY_INTERPOLATOR[d.max_severity]?.(tAdjusted)
          ?? SEVERITY_INTERPOLATOR.unknown(tAdjusted);
      })
      .attr("opacity", (d) =>
        selectedService && d.service !== selectedService ? 0.25 : 1
      )
      .attr("stroke", (d) =>
        selectedService === d.service
          ? SEVERITY_BASE_COLOR[d.max_severity]
          : "transparent"
      )
      .attr("stroke-width", 1.5)
      .style("cursor", "pointer")
      .on("mouseenter", function (event: MouseEvent, d: HeatmapCell) {
        d3.select(this).attr("opacity", 1).attr("stroke", SEVERITY_BASE_COLOR[d.max_severity]);
        const rect = (event.currentTarget as Element).closest("svg")?.getBoundingClientRect();
        const containerRect = containerRef.current?.getBoundingClientRect();
        if (rect && containerRect) {
          setTooltip({
            visible: true,
            x: event.clientX - containerRect.left + 12,
            y: event.clientY - containerRect.top - 8,
            cell: d,
          });
        }
      })
      .on("mouseleave", function (_: MouseEvent, d: HeatmapCell) {
        d3.select(this)
          .attr("opacity", selectedService && d.service !== selectedService ? 0.25 : 1)
          .attr("stroke", selectedService === d.service ? SEVERITY_BASE_COLOR[d.max_severity] : "transparent");
        setTooltip((t) => ({ ...t, visible: false }));
      })
      .on("click", (_: MouseEvent, d: HeatmapCell) => {
        onCellClick?.(d);
      });

    // ------------------------------------------------------------------
    // X Axis
    // ------------------------------------------------------------------
    const tickFormat = (domainValue: d3.NumberValue | Date): string => {
      const d = domainValue instanceof Date ? domainValue : new Date(Number(domainValue));
      if (timeRange.hours <= 6)  return d3.timeFormat("%-I:%M%p")(d);
      if (timeRange.hours <= 24) return d3.timeFormat("%-I%p")(d);
      return d3.timeFormat("%b %-d")(d);
    };

    g.append("g")
      .attr("transform", `translate(0,${innerH})`)
      .call(
        d3.axisBottom(xScale)
          .ticks(Math.min(timeRange.hours <= 6 ? 12 : 8, innerW / 60))
          .tickFormat(tickFormat as (value: Date | d3.NumberValue, i: number) => string)
      )
      .call(gEl => {
        gEl.select(".domain").attr("stroke", "rgba(255,255,255,0.12)");
        gEl.selectAll(".tick line").attr("stroke", "rgba(255,255,255,0.12)");
        gEl.selectAll(".tick text")
          .attr("fill", "#94a3b8")
          .attr("font-size", "11px");
      });

    // ------------------------------------------------------------------
    // Y Axis
    // ------------------------------------------------------------------
    g.append("g")
      .call(d3.axisLeft(yScale).tickSize(0).tickPadding(10))
      .call(gEl => {
        gEl.select(".domain").remove();
        gEl.selectAll(".tick text")
          .attr("fill", "#cbd5e1")
          .attr("font-size", "12px")
          .each(function () {
            const textEl = d3.select(this);
            const text = textEl.text();
            if (text.length > 18) textEl.text(text.slice(0, 16) + "…");
          });
      });

    // ------------------------------------------------------------------
    // Legend
    // ------------------------------------------------------------------
    const legendG = svg.append("g")
      .attr("transform", `translate(${MARGIN.left},${totalH - 20})`);

    const legendItems: { sev: HeatmapSeverity; label: string }[] = [
      { sev: "critical", label: "Critical" },
      { sev: "high",     label: "High"     },
      { sev: "warning",  label: "Warning"  },
      { sev: "info",     label: "Info"     },
    ];

    legendItems.forEach(({ sev, label }, i) => {
      const x = i * 90;
      legendG.append("rect")
        .attr("x", x).attr("y", 0)
        .attr("width", 12).attr("height", 12)
        .attr("rx", 2).attr("fill", SEVERITY_BASE_COLOR[sev]);
      legendG.append("text")
        .attr("x", x + 16).attr("y", 10)
        .attr("fill", "#94a3b8")
        .attr("font-size", "11px")
        .text(label);
    });

  }, [data, containerWidth, timeRange, selectedService, onCellClick]);

  // Compute SVG height for container
  const svgHeight = data && data.services.length > 0
    ? Math.max(data.services.length * CELL_HEIGHT, MIN_HEIGHT) + MARGIN.top + MARGIN.bottom
    : 200;

  return (
    <div style={{ position: "relative", width: "100%" }}>
      {/* Header row */}
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
            Alert Density
          </span>
          {data && (
            <span style={{ fontSize: 11, color: "#475569", marginLeft: 10 }}>
              {data.meta.total_alerts.toLocaleString()} alerts · {data.meta.service_count} services
            </span>
          )}
        </div>

        {/* Time range picker */}
        <div style={{ display: "flex", gap: 4 }}>
          {TIME_RANGES.map((r) => (
            <button
              key={r.label}
              onClick={() => onTimeRangeChange(r)}
              style={{
                padding: "3px 10px",
                fontSize: 12,
                borderRadius: 4,
                border: "1px solid",
                cursor: "pointer",
                borderColor: timeRange.hours === r.hours ? "#3b82f6" : "rgba(255,255,255,0.1)",
                background: timeRange.hours === r.hours ? "rgba(59,130,246,0.15)" : "transparent",
                color: timeRange.hours === r.hours ? "#93c5fd" : "#64748b",
                transition: "all 0.15s",
              }}
            >
              {r.label}
            </button>
          ))}
        </div>
      </div>

      {/* Chart area */}
      <div ref={containerRef} style={{ position: "relative", width: "100%", minHeight: svgHeight }}>
        {loading && (
          <div style={{
            position: "absolute", inset: 0, display: "flex",
            alignItems: "center", justifyContent: "center",
            background: "rgba(15,23,42,0.7)", borderRadius: 6, zIndex: 10,
          }}>
            <span style={{ color: "#64748b", fontSize: 13 }}>Loading heatmap…</span>
          </div>
        )}

        {!loading && (!data || data.services.length === 0) && (
          <div style={{
            display: "flex", alignItems: "center", justifyContent: "center",
            height: 160, color: "#475569", fontSize: 13,
          }}>
            No alert data for this time range.
          </div>
        )}

        <svg ref={svgRef} style={{ display: "block", width: "100%", overflow: "visible" }} />

        {/* Tooltip */}
        {tooltip.visible && tooltip.cell && (
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
            minWidth: 180,
            zIndex: 100,
          }}>
            <div style={{ fontWeight: 700, marginBottom: 6, color: "#f1f5f9" }}>
              {tooltip.cell.service}
            </div>
            <div style={{ color: "#94a3b8", marginBottom: 4 }}>
              {new Date(tooltip.cell.bucket).toLocaleString()}
            </div>
            <div style={{ marginBottom: 6 }}>
              <span style={{ color: "#64748b" }}>Alerts: </span>
              <strong style={{ color: SEVERITY_BASE_COLOR[tooltip.cell.max_severity] }}>
                {tooltip.cell.count}
              </strong>
            </div>
            <div style={{ borderTop: "1px solid rgba(255,255,255,0.06)", paddingTop: 6 }}>
              {Object.entries(tooltip.cell.severities).map(([sev, count]) => (
                <div key={sev} style={{
                  display: "flex", justifyContent: "space-between", gap: 16,
                  color: SEVERITY_BASE_COLOR[sev as HeatmapSeverity] ?? "#94a3b8",
                  fontSize: 11,
                }}>
                  <span style={{ textTransform: "capitalize" }}>{sev}</span>
                  <span>{count}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
