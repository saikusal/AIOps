import { useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchCacheStats, purgeCache } from "../lib/api";
import { useRefreshInterval } from "../lib/refresh";
import { useState } from "react";

interface CacheCounters {
  instant_hits: number;
  instant_misses: number;
  instant_sets: number;
  batch_hits: number;
  batch_misses: number;
  batch_sets: number;
  meta_hits: number;
  meta_misses: number;
  meta_sets: number;
  compressed_writes: number;
  bytes_saved: number;
  stale_hits: number;
  circuit_trips: number;
  retries: number;
  revalidations: number;
  purges: number;
}

interface CacheSummary {
  total_hits: number;
  total_misses: number;
  total_requests: number;
  hit_rate_pct: number;
}

interface CacheConfig {
  instant_quantise_seconds: number;
  instant_cache_ttl: number;
  metadata_cache_ttl: number;
  stale_ttl_multiplier: number;
  gzip_threshold_bytes: number;
  retry_max_attempts: number;
  cb_failure_threshold: number;
  cb_recovery_timeout: number;
}

interface BreakerSnapshot {
  state: "closed" | "open" | "half_open";
  consecutive_failures: number;
  last_failure: number;
}

interface ValkeyInfo {
  connected: boolean;
  used_memory_human?: string;
  used_memory_peak_human?: string;
  used_memory_bytes?: number;
  key_counts?: { iq: number; meta: number; stale: number; other: number };
  total_tc_keys?: number;
  total_db_keys?: number;
  error?: string;
}

export interface CacheStats {
  counters: CacheCounters;
  summary: CacheSummary;
  config: CacheConfig;
  circuit_breakers: Record<string, BreakerSnapshot>;
  valkey: ValkeyInfo;
}

function StatCard({ label, value, sub, accent }: { label: string; value: string | number; sub?: string; accent?: string }) {
  return (
    <div className={`cache-stat-card ${accent ? `cache-stat-card--${accent}` : ""}`}>
      <div className="cache-stat-card__value">{value}</div>
      <div className="cache-stat-card__label">{label}</div>
      {sub && <div className="cache-stat-card__sub">{sub}</div>}
    </div>
  );
}

function HitRateBar({ hitRate }: { hitRate: number }) {
  const color = hitRate >= 70 ? "var(--green)" : hitRate >= 40 ? "var(--amber)" : "var(--red)";
  return (
    <div className="cache-hit-bar">
      <div className="cache-hit-bar__track">
        <div
          className="cache-hit-bar__fill"
          style={{ width: `${Math.min(hitRate, 100)}%`, background: color }}
        />
      </div>
      <span className="cache-hit-bar__label">{hitRate}% hit rate</span>
    </div>
  );
}

function BreakerBadge({ name, snap }: { name: string; snap: BreakerSnapshot }) {
  const stateColor =
    snap.state === "closed" ? "var(--green)" : snap.state === "open" ? "var(--red)" : "var(--amber)";
  return (
    <div className="cache-breaker-badge">
      <span className="cache-breaker-badge__dot" style={{ background: stateColor }} />
      <span className="cache-breaker-badge__name">{name}</span>
      <span className="cache-breaker-badge__state">{snap.state.replace("_", "-")}</span>
      {snap.consecutive_failures > 0 && (
        <span className="cache-breaker-badge__fails">{snap.consecutive_failures} fails</span>
      )}
    </div>
  );
}

export function CacheDashboardPage() {
  const { refreshMs } = useRefreshInterval();
  const queryClient = useQueryClient();
  const [purging, setPurging] = useState(false);
  const statsQuery = useQuery({
    queryKey: ["cache-stats"],
    queryFn: fetchCacheStats,
    refetchInterval: refreshMs,
  });

  const data = statsQuery.data as CacheStats | undefined;

  const handlePurge = async (prefix?: string) => {
    setPurging(true);
    try {
      await purgeCache(prefix);
      queryClient.invalidateQueries({ queryKey: ["cache-stats"] });
    } catch {
      /* ignore */
    } finally {
      setPurging(false);
    }
  };

  return (
    <>
      <section className="hero-card hero-card--cache">
        <div className="eyebrow">Observability</div>
        <h2>Cache Dashboard</h2>
        <p>
          Telemetry cache performance powered by Valkey — hit rates, circuit breakers, resilience counters, and memory usage.
        </p>
      </section>

      {statsQuery.isLoading ? (
        <section className="page-card">
          <div className="eyebrow">Loading</div>
          <h2>Fetching cache stats…</h2>
        </section>
      ) : statsQuery.isError ? (
        <section className="page-card">
          <div className="eyebrow">Error</div>
          <h2>Cache stats unavailable</h2>
        </section>
      ) : data ? (
        <>
          {/* ── Summary row ── */}
          <section className="cache-summary-row">
            <HitRateBar hitRate={data.summary.hit_rate_pct} />
            <div className="cache-summary-stats">
              <StatCard label="Total Requests" value={data.summary.total_requests} accent="blue" />
              <StatCard label="Cache Hits" value={data.summary.total_hits} accent="green" />
              <StatCard label="Cache Misses" value={data.summary.total_misses} accent="red" />
            </div>
          </section>

          {/* ── Circuit Breakers ── */}
          <section className="cache-breakers-section">
            <h3 className="cache-section-title">Circuit Breakers</h3>
            <div className="cache-breakers-row">
              {Object.entries(data.circuit_breakers).map(([name, snap]) => (
                <BreakerBadge key={name} name={name} snap={snap} />
              ))}
            </div>
            <div className="cache-resilience-stats">
              <StatCard label="Stale Served" value={data.counters.stale_hits} accent="amber" />
              <StatCard label="Retries" value={data.counters.retries} />
              <StatCard label="Circuit Trips" value={data.counters.circuit_trips} accent="red" />
              <StatCard label="BG Revalidations" value={data.counters.revalidations} accent="green" />
              <StatCard label="Purges" value={data.counters.purges} />
            </div>
          </section>

          {/* ── Backend breakdown ── */}
          <section className="cache-breakdown">
            <h3 className="cache-section-title">Backend Breakdown</h3>
            <div className="cache-breakdown-grid">
              <div className="cache-backend-card">
                <div className="cache-backend-card__header">
                  <span className="cache-backend-card__icon">VM</span>
                  <strong>VictoriaMetrics (PromQL)</strong>
                </div>
                <div className="cache-backend-card__body">
                  <div className="cache-backend-card__stat">
                    <span>Individual</span>
                    <strong>{data.counters.instant_hits} hits / {data.counters.instant_misses} misses</strong>
                  </div>
                  <div className="cache-backend-card__stat">
                    <span>Batch (MGET)</span>
                    <strong>{data.counters.batch_hits} hits / {data.counters.batch_misses} misses</strong>
                  </div>
                  <div className="cache-backend-card__stat">
                    <span>Cache Writes</span>
                    <strong>{data.counters.instant_sets + data.counters.batch_sets}</strong>
                  </div>
                  <div className="cache-backend-card__stat">
                    <span>TTL</span>
                    <strong>{data.config.instant_cache_ttl}s (quantised {data.config.instant_quantise_seconds}s)</strong>
                  </div>
                </div>
              </div>

              <div className="cache-backend-card">
                <div className="cache-backend-card__header">
                  <span className="cache-backend-card__icon">ES</span>
                  <strong>Elasticsearch + Jaeger</strong>
                </div>
                <div className="cache-backend-card__body">
                  <div className="cache-backend-card__stat">
                    <span>Metadata Hits</span>
                    <strong>{data.counters.meta_hits}</strong>
                  </div>
                  <div className="cache-backend-card__stat">
                    <span>Metadata Misses</span>
                    <strong>{data.counters.meta_misses}</strong>
                  </div>
                  <div className="cache-backend-card__stat">
                    <span>Cache Writes</span>
                    <strong>{data.counters.meta_sets}</strong>
                  </div>
                  <div className="cache-backend-card__stat">
                    <span>TTL</span>
                    <strong>{data.config.metadata_cache_ttl}s (stale ×{data.config.stale_ttl_multiplier})</strong>
                  </div>
                </div>
              </div>
            </div>
          </section>

          {/* ── Valkey / Memory ── */}
          <section className="cache-valkey-section">
            <h3 className="cache-section-title">Valkey Memory</h3>
            {data.valkey.connected ? (
              <div className="cache-valkey-grid">
                <StatCard
                  label="Memory Used"
                  value={data.valkey.used_memory_human || "—"}
                  accent="blue"
                />
                <StatCard
                  label="Peak Memory"
                  value={data.valkey.used_memory_peak_human || "—"}
                  accent="amber"
                />
                <StatCard
                  label="TC Keys (active)"
                  value={data.valkey.total_tc_keys ?? 0}
                  sub={`iq: ${data.valkey.key_counts?.iq ?? 0}, meta: ${data.valkey.key_counts?.meta ?? 0}, stale: ${data.valkey.key_counts?.stale ?? 0}`}
                  accent="green"
                />
                <StatCard
                  label="Total DB Keys"
                  value={data.valkey.total_db_keys ?? 0}
                />
                <StatCard
                  label="Compressed Writes"
                  value={data.counters.compressed_writes}
                  sub={`${(data.counters.bytes_saved / 1024).toFixed(1)} KB saved`}
                />
              </div>
            ) : (
              <div className="cache-valkey-error">
                Valkey disconnected: {data.valkey.error || "unknown"}
              </div>
            )}
          </section>

          {/* ── Purge Controls ── */}
          <section className="cache-purge-section">
            <h3 className="cache-section-title">Cache Purge</h3>
            <div className="cache-purge-row">
              <button className="cache-purge-btn cache-purge-btn--all" disabled={purging} onClick={() => handlePurge()}>
                {purging ? "Purging…" : "Purge All"}
              </button>
              <button className="cache-purge-btn" disabled={purging} onClick={() => handlePurge("iq")}>
                Purge PromQL
              </button>
              <button className="cache-purge-btn" disabled={purging} onClick={() => handlePurge("meta")}>
                Purge Metadata
              </button>
            </div>
          </section>
        </>
      ) : null}
    </>
  );
}
