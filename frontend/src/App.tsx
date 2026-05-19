import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { AppShell } from "./components/AppShell";
<<<<<<< Updated upstream
import { ApplicationsPage } from "./pages/ApplicationsPage";
import { AssistantPage } from "./pages/AssistantPage";
import { AlertsPage } from "./pages/AlertsPage";
=======
>>>>>>> Stashed changes
import { CacheDashboardPage } from "./pages/CacheDashboardPage";
import { FleetTargetPage } from "./pages/FleetTargetPage";
import { GraphPage } from "./pages/GraphPage";
import { InvestigationDetailPage } from "./pages/InvestigationDetailPage";
import { IntegrationConfigPage } from "./pages/IntegrationConfigPage";
<<<<<<< Updated upstream
import { PredictionsPage } from "./pages/PredictionsPage";
=======
import {
  AlertsRedirect,
  ApplicationsRedirect,
  AssistantRedirect,
  AutomationChangeRiskPage,
  ChangeRiskRedirect,
  CodeContextRedirect,
  DocumentsRedirect,
  EnrollRedirect,
  IncidentsRcaPage,
  IncidentsRedirect,
  IngestionRedirect,
  IntegrationsRedirect,
  InvestigationsRedirect,
  OnboardingDataPage,
  OperationsOverviewPage,
  OperationsRedirect,
  PredictionsRedirect,
  ServiceTopologyPage,
} from "./pages/MergedWorkspaces";
import { TenantManagementPage } from "./pages/TenantManagementPage";
>>>>>>> Stashed changes

function LegacyAssistantRedirect() {
  const location = useLocation();
  return <Navigate to={`/genai${location.search}`} replace />;
}

export function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route path="/" element={<Navigate to="/operations" replace />} />
        <Route path="/operations" element={<OperationsOverviewPage />} />
        <Route path="/onboarding" element={<OnboardingDataPage />} />
        <Route path="/topology" element={<ServiceTopologyPage />} />
        <Route path="/incidents-rca" element={<IncidentsRcaPage />} />
        <Route path="/automation" element={<AutomationChangeRiskPage />} />
        <Route path="/administration" element={<TenantManagementPage />} />
        <Route path="/fleet/targets/:targetId" element={<FleetTargetPage />} />
        <Route path="/investigations/:runId" element={<InvestigationDetailPage />} />
        <Route path="/integrations/:vendor" element={<IntegrationConfigPage />} />
<<<<<<< Updated upstream
        <Route path="/topology" element={<ApplicationsPage />} />
        <Route path="/code-context" element={<CodeContextPage />} />
        <Route path="/genai" element={<AssistantPage />} />
        <Route path="/change-risk" element={<ChangeRiskPage />} />
        <Route path="/automation" element={<DocumentsPage />} />
        <Route path="/analytics" element={<CacheDashboardPage />} />
=======
        <Route path="/analytics/cache" element={<CacheDashboardPage />} />
>>>>>>> Stashed changes
        {/* legacy redirects so bookmarks don't break */}
        <Route path="/analytics" element={<OperationsRedirect />} />
        <Route path="/intelligence" element={<PredictionsRedirect />} />
        <Route path="/predictions" element={<PredictionsRedirect />} />
        <Route path="/domain-onboarding" element={<EnrollRedirect />} />
        <Route path="/enroll" element={<EnrollRedirect />} />
        <Route path="/ingestion" element={<IngestionRedirect />} />
        <Route path="/fleet" element={<IngestionRedirect />} />
        <Route path="/profiles" element={<IngestionRedirect />} />
        <Route path="/integrations" element={<IntegrationsRedirect />} />
        <Route path="/applications" element={<ApplicationsRedirect />} />
        <Route path="/code-context" element={<CodeContextRedirect />} />
        <Route path="/alerts" element={<AlertsRedirect />} />
        <Route path="/incidents" element={<IncidentsRedirect />} />
        <Route path="/investigations" element={<InvestigationsRedirect />} />
        <Route path="/genai" element={<AssistantRedirect />} />
        <Route path="/assistant" element={<LegacyAssistantRedirect />} />
        <Route path="/change-risk" element={<ChangeRiskRedirect />} />
        <Route path="/documents" element={<DocumentsRedirect />} />
        <Route path="/settings/members" element={<Navigate to="/administration" replace />} />
        <Route path="/cache" element={<OperationsRedirect />} />
        <Route path="/graph" element={<GraphPage />} />
        <Route path="/graph/application/:applicationKey" element={<GraphPage />} />
        <Route path="/graph/incident/:incidentKey" element={<GraphPage />} />
        <Route path="/graph/:alertId" element={<GraphPage />} />
      </Route>
    </Routes>
  );
}
