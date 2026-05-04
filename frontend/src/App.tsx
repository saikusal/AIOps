import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { AppShell } from "./components/AppShell";
import { ApplicationsPage } from "./pages/ApplicationsPage";
import { AssistantPage } from "./pages/AssistantPage";
import { AlertsPage } from "./pages/AlertsPage";
import { CacheDashboardPage } from "./pages/CacheDashboardPage";
import { ChangeRiskPage } from "./pages/ChangeRiskPage";
import { CodeContextPage } from "./pages/CodeContextPage";
import { DocumentsPage } from "./pages/DocumentsPage";
import { EnrollTargetPage } from "./pages/EnrollTargetPage";
import { GraphPage } from "./pages/GraphPage";
import { IngestionPage } from "./pages/IngestionPage";
import { IncidentsPage } from "./pages/IncidentsPage";
import { PredictionsPage } from "./pages/PredictionsPage";

function LegacyAssistantRedirect() {
  const location = useLocation();
  return <Navigate to={`/genai${location.search}`} replace />;
}

export function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route path="/" element={<Navigate to="/domain-onboarding" replace />} />
        <Route path="/domain-onboarding" element={<EnrollTargetPage />} />
        <Route path="/ingestion" element={<IngestionPage />} />
        <Route path="/intelligence" element={<PredictionsPage />} />
        <Route path="/alerts" element={<AlertsPage />} />
        <Route path="/incidents" element={<IncidentsPage />} />
        <Route path="/topology" element={<ApplicationsPage />} />
        <Route path="/code-context" element={<CodeContextPage />} />
        <Route path="/genai" element={<AssistantPage />} />
        <Route path="/change-risk" element={<ChangeRiskPage />} />
        <Route path="/automation" element={<DocumentsPage />} />
        <Route path="/analytics" element={<CacheDashboardPage />} />
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
