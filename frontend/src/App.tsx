import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import type { ReactNode } from "react";
import { AppShell } from "./components/AppShell";
import { useAuth } from "./lib/auth";
import { AdminPage } from "./pages/AdminPage";
import { ApplicationsPage } from "./pages/ApplicationsPage";
import { AssistantPage } from "./pages/AssistantPage";
import { AlertsPage } from "./pages/AlertsPage";
import { AnalyticsDashboard } from "./pages/AnalyticsDashboard";
import { CacheDashboardPage } from "./pages/CacheDashboardPage";
import { ChangeRiskPage } from "./pages/ChangeRiskPage";
import { CodeContextPage } from "./pages/CodeContextPage";
import { DocumentsPage } from "./pages/DocumentsPage";
import { EnrollTargetPage } from "./pages/EnrollTargetPage";
import { FleetTargetPage } from "./pages/FleetTargetPage";
import { GraphPage } from "./pages/GraphPage";
import { IngestionPage } from "./pages/IngestionPage";
import { IncidentsPage } from "./pages/IncidentsPage";
import { InvestigationDetailPage } from "./pages/InvestigationDetailPage";
import { InvestigationsPage } from "./pages/InvestigationsPage";
import { IntegrationsPage } from "./pages/IntegrationsPage";
import { IntegrationConfigPage } from "./pages/IntegrationConfigPage";
import { LoginPage } from "./pages/LoginPage";
import { PredictionsPage } from "./pages/PredictionsPage";
import { TenantManagementPage } from "./pages/TenantManagementPage";

function LegacyAssistantRedirect() {
  const location = useLocation();
  return <Navigate to={`/genai${location.search}`} replace />;
}

function RequireAuth({ children }: { children: ReactNode }) {
  const { loading, user } = useAuth();
  const location = useLocation();
  if (loading) {
    return (
      <div style={{ minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center", color: "var(--color-muted,#9ca3af)" }}>
        Loading…
      </div>
    );
  }
  if (!user) {
    return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />;
  }
  return <>{children}</>;
}

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        element={
          <RequireAuth>
            <AppShell />
          </RequireAuth>
        }
      >
        <Route path="/" element={<Navigate to="/domain-onboarding" replace />} />
        <Route path="/domain-onboarding" element={<EnrollTargetPage />} />
        <Route path="/ingestion" element={<IngestionPage />} />
        <Route path="/fleet/targets/:targetId" element={<FleetTargetPage />} />
        <Route path="/intelligence" element={<PredictionsPage />} />
        <Route path="/alerts" element={<AlertsPage />} />
        <Route path="/incidents" element={<IncidentsPage />} />
        <Route path="/investigations" element={<InvestigationsPage />} />
        <Route path="/investigations/:runId" element={<InvestigationDetailPage />} />
        <Route path="/integrations" element={<IntegrationsPage />} />
        <Route path="/integrations/:vendor" element={<IntegrationConfigPage />} />
        <Route path="/settings/members" element={<TenantManagementPage />} />
        <Route path="/admin/*" element={<AdminPage />} />
        <Route path="/topology" element={<ApplicationsPage />} />
        <Route path="/code-context" element={<CodeContextPage />} />
        <Route path="/genai" element={<AssistantPage />} />
        <Route path="/change-risk" element={<ChangeRiskPage />} />
        <Route path="/automation" element={<DocumentsPage />} />
        <Route path="/analytics" element={<AnalyticsDashboard />} />
        <Route path="/analytics/cache" element={<CacheDashboardPage />} />
        {/* legacy redirects so bookmarks don't break */}
        <Route path="/enroll" element={<Navigate to="/domain-onboarding" replace />} />
        <Route path="/fleet" element={<Navigate to="/ingestion" replace />} />
        <Route path="/profiles" element={<Navigate to="/ingestion" replace />} />
        <Route path="/predictions" element={<Navigate to="/intelligence" replace />} />
        <Route path="/applications" element={<Navigate to="/topology" replace />} />
        <Route path="/assistant" element={<LegacyAssistantRedirect />} />
        <Route path="/documents" element={<Navigate to="/automation" replace />} />
        <Route path="/cache" element={<Navigate to="/analytics" replace />} />
        <Route path="/graph" element={<GraphPage />} />
        <Route path="/graph/application/:applicationKey" element={<GraphPage />} />
        <Route path="/graph/incident/:incidentKey" element={<GraphPage />} />
        <Route path="/graph/:alertId" element={<GraphPage />} />
      </Route>
    </Routes>
  );
}
