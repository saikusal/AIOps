import { Navigate, Route, Routes } from "react-router-dom";
import { AppShell } from "./components/AppShell";
import { ApplicationsPage } from "./pages/ApplicationsPage";
import { AssistantPage } from "./pages/AssistantPage";
import { AlertsPage } from "./pages/AlertsPage";
import { DocumentsPage } from "./pages/DocumentsPage";
import { GraphPage } from "./pages/GraphPage";
import { IncidentsPage } from "./pages/IncidentsPage";
import { PredictionsPage } from "./pages/PredictionsPage";

export function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route path="/" element={<Navigate to="/applications" replace />} />
        <Route path="/applications" element={<ApplicationsPage />} />
        <Route path="/assistant" element={<AssistantPage />} />
        <Route path="/alerts" element={<AlertsPage />} />
        <Route path="/incidents" element={<IncidentsPage />} />
        <Route path="/predictions" element={<PredictionsPage />} />
        <Route path="/documents" element={<DocumentsPage />} />
        <Route path="/graph" element={<GraphPage />} />
        <Route path="/graph/application/:applicationKey" element={<GraphPage />} />
        <Route path="/graph/incident/:incidentKey" element={<GraphPage />} />
        <Route path="/graph/:alertId" element={<GraphPage />} />
      </Route>
    </Routes>
  );
}
