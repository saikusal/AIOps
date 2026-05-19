import React, { useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import { useNavigate } from "react-router-dom";

import { fetchIntegrations, testIntegrationConnection, type IntegrationConfig } from "../lib/api";

const catalog = [
  { name: "Prometheus", type: "metrics", tier: "Core", vendorId: "prometheus", logo: "https://cdn.jsdelivr.net/gh/devicons/devicon@latest/icons/prometheus/prometheus-original.svg" },
  { name: "VictoriaMetrics", type: "metrics", tier: "Core", vendorId: "victoriametrics", logo: "https://cdn.simpleicons.org/victoriametrics/009688" },
  { name: "Tempo", type: "traces", tier: "Core", vendorId: "tempo", logo: "https://upload.wikimedia.org/wikipedia/commons/3/3b/Grafana_icon.svg" },
  { name: "OpenSearch", type: "logs", tier: "Core", vendorId: "opensearch", logo: "https://cdn.simpleicons.org/opensearch/005EB8" },
  { name: "Splunk", type: "logs", tier: "Tier 1", vendorId: "splunk", logo: "https://cdn.jsdelivr.net/gh/devicons/devicon@latest/icons/splunk/splunk-original-wordmark.svg" },
  { name: "Dynatrace", type: "traces / topology", tier: "Tier 1", vendorId: "dynatrace", logo: "https://www.vectorlogo.zone/logos/dynatrace/dynatrace-icon.svg" },
  { name: "Datadog", type: "mixed", tier: "Tier 1", vendorId: "datadog", logo: "https://cdn.worldvectorlogo.com/logos/datadog.svg" },
  { name: "New Relic", type: "mixed", tier: "Tier 2", vendorId: "newrelic", logo: "https://cdn.worldvectorlogo.com/logos/new-relic.svg" },
  { name: "Nagios", type: "alerts", tier: "Tier 2", vendorId: "nagios", logo: "https://www.vectorlogo.zone/logos/nagios/nagios-icon.svg" },
  { name: "AWS", type: "cloud", tier: "Cloud", vendorId: "aws", logo: "https://cdn.jsdelivr.net/gh/devicons/devicon@latest/icons/amazonwebservices/amazonwebservices-original-wordmark.svg" },
  { name: "Azure", type: "cloud", tier: "Cloud", vendorId: "azure", logo: "https://cdn.jsdelivr.net/gh/devicons/devicon@latest/icons/azure/azure-original.svg" },
  { name: "GCP", type: "cloud", tier: "Cloud", vendorId: "gcp", logo: "https://cdn.jsdelivr.net/gh/devicons/devicon@latest/icons/googlecloud/googlecloud-original.svg" },
];

export function IntegrationsPage() {
  const navigate = useNavigate();
  const [integrations, setIntegrations] = useState<IntegrationConfig[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState("");
  const [isTesting, setIsTesting] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<{ name: string; status: "success" | "error"; message: string } | null>(null);

  useEffect(() => {
    let active = true;
    setIsLoading(true);
    fetchIntegrations()
      .then((rows) => {
        if (!active) return;
        setIntegrations(rows);
        setError("");
      })
      .catch((err: Error) => {
        if (!active) return;
        setError(err.message || "Unable to load integrations.");
      })
      .finally(() => {
        if (active) setIsLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  const configuredMap = useMemo(() => {
    const map = new Map<string, IntegrationConfig>();
    integrations.forEach((integration) => {
      map.set(integration.integration_type, integration);
    });
    return map;
  }, [integrations]);

  const configuredCount = catalog.filter((integration) => configuredMap.has(integration.vendorId)).length;
  const coreCount = catalog.filter((integration) => integration.tier === "Core").length;

  const handleTest = async (vendorId: string, name: string) => {
    setIsTesting(vendorId);
    setTestResult(null);
    try {
      const result = await testIntegrationConnection(vendorId);
      setIntegrations((current) =>
        current.map((item) => (item.integration_type === vendorId ? result.integration : item)),
      );
      setTestResult({ name, status: result.healthy ? "success" : "error", message: result.message });
    } catch (err) {
      setTestResult({ name, status: "error", message: err instanceof Error ? err.message : "Connection test failed." });
    } finally {
      setIsTesting(null);
    }
  };

  return (
    <div className="integrations-page">
      <header className="integrations-hero">
        <div>
          <div className="eyebrow">Integration Hub</div>
          <h2>Connected Infrastructure</h2>
          <p>Manage external telemetry sources, cloud providers, and observability platforms from one place.</p>
        </div>
        <div className="integrations-summary" aria-label="Integration summary">
          <div>
            <span>Configured</span>
            <strong>{configuredCount}</strong>
          </div>
          <div>
            <span>Catalog</span>
            <strong>{catalog.length}</strong>
          </div>
          <div>
            <span>Core Sources</span>
            <strong>{coreCount}</strong>
          </div>
        </div>
      </header>

      {error && <div className="integration-alert integration-alert--error">{error}</div>}
      {isLoading && <div className="integration-alert">Loading integrations...</div>}

      <div className="integration-grid">
        {catalog.map((integration, i) => {
          const configured = configuredMap.get(integration.vendorId);
          const isConfigured = Boolean(configured);
          return (
            <motion.div
              key={integration.name}
              initial={{ opacity: 0, y: 15 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.05, type: "spring", stiffness: 200, damping: 20 }}
              className={`integration-card ${isConfigured ? "is-configured" : ""}`}
            >
              <div className="integration-card-header">
                <div className="integration-logo-box">
                  <img src={integration.logo} alt={`${integration.name} logo`} />
                </div>
                <div className="integration-info">
                  <h3>
                    {integration.name}
                    {isConfigured && <span className="integration-status-dot" aria-label="Configured"></span>}
                  </h3>
<<<<<<< Updated upstream
                  <span className="integration-type">{integration.type}</span>
                  {configured?.health_status && <span className="integration-type">{configured.health_status}</span>}
=======
                  <div className="integration-meta-row">
                    <span className="integration-type">{integration.type}</span>
                    {configured?.health_status && <span className="integration-type">{configured.health_status}</span>}
                  </div>
                  {(configured?.capabilities || []).length ? <span className="integration-capabilities">{configured?.capabilities?.join(" · ")}</span> : null}
>>>>>>> Stashed changes
                </div>
                <span className="integration-tier">{integration.tier}</span>
              </div>

              {testResult?.name === integration.name && (
                <motion.div
                  initial={{ opacity: 0, scale: 0.95 }}
                  animate={{ opacity: 1, scale: 1 }}
                  className={`integration-test-result ${testResult.status === "success" ? "is-success" : "is-error"}`}
                >
                  {testResult.message}
                </motion.div>
              )}

              <div className="integration-actions">
                <button
                  className={`action-button integration-action ${isConfigured ? "action-button--ghost" : ""}`}
                  onClick={() => navigate(`/integrations/${integration.vendorId}`)}
                >
                  {isConfigured ? "Edit Config" : "Configure"}
                </button>
                <button
                  className="action-button action-button--ghost integration-action"
                  onClick={() => handleTest(integration.vendorId, integration.name)}
                  disabled={isTesting === integration.vendorId || !isConfigured}
                >
                  {isTesting === integration.vendorId ? "Testing..." : "Test Connection"}
                </button>
              </div>
            </motion.div>
          );
        })}
      </div>
    </div>
  );
}
