import { Link, Navigate, useLocation, useSearchParams } from "react-router-dom";
import { AlertsPage } from "./AlertsPage";
import { AnalyticsDashboard } from "./AnalyticsDashboard";
import { ApplicationsPage } from "./ApplicationsPage";
import { AssistantPage } from "./AssistantPage";
import { ChangeRiskPage } from "./ChangeRiskPage";
import { CodeContextPage } from "./CodeContextPage";
import { DocumentsPage } from "./DocumentsPage";
import { EnrollTargetPage } from "./EnrollTargetPage";
import { IncidentsPage } from "./IncidentsPage";
import { IngestionPage } from "./IngestionPage";
import { InvestigationsPage } from "./InvestigationsPage";
import { IntegrationsPage } from "./IntegrationsPage";
import { PredictionsPage } from "./PredictionsPage";

type WorkspaceTab<T extends string> = {
  value: T;
  label: string;
  meta: string;
};

function useWorkspaceTab<T extends string>(tabs: readonly WorkspaceTab<T>[], fallback: T) {
  const [searchParams] = useSearchParams();
  const active = searchParams.get("tab") as T | null;
  return tabs.some((tab) => tab.value === active) ? active! : fallback;
}

function tabSearch(searchParams: URLSearchParams, value: string) {
  const next = new URLSearchParams(searchParams);
  next.set("tab", value);
  return `?${next.toString()}`;
}

function WorkspaceTabs<T extends string>({
  basePath,
  tabs,
  active,
}: {
  basePath: string;
  tabs: readonly WorkspaceTab<T>[];
  active: T;
}) {
  const [searchParams] = useSearchParams();
  return (
    <nav className="workspace-tabs" aria-label="Workspace views">
      {tabs.map((tab) => (
        <Link
          key={tab.value}
          className={`workspace-tab${active === tab.value ? " is-active" : ""}`}
          to={`${basePath}${tabSearch(searchParams, tab.value)}`}
        >
          <strong>{tab.label}</strong>
          <span>{tab.meta}</span>
        </Link>
      ))}
    </nav>
  );
}

function RedirectWithTab({ to, tab }: { to: string; tab: string }) {
  const location = useLocation();
  const searchParams = new URLSearchParams(location.search);
  searchParams.set("tab", tab);
  return <Navigate to={`${to}?${searchParams.toString()}`} replace />;
}

const operationsTabs = [
  { value: "overview", label: "Overview", meta: "SLO · MTTR · posture" },
  { value: "risk", label: "Risk Forecast", meta: "Predictions · active risk" },
] as const;

const onboardingTabs = [
  { value: "enroll", label: "Domain Onboarding", meta: "Targets · agents" },
  { value: "ingestion", label: "Data Ingestion", meta: "Fleet · logs · profiles" },
  { value: "integrations", label: "Integrations", meta: "External tools" },
] as const;

const topologyTabs = [
  { value: "services", label: "Service Topology", meta: "CMDB · blast radius" },
  { value: "code", label: "Code Context", meta: "Runtime to repo" },
] as const;

const incidentTabs = [
  { value: "incidents", label: "Incident Flow", meta: "War room · fix" },
  { value: "alerts", label: "Alert Feed", meta: "Signals · suppressions" },
  { value: "investigations", label: "Investigations", meta: "RCA tool trace" },
  { value: "assistant", label: "Assistant", meta: "AI explanation" },
] as const;

const automationTabs = [
  { value: "risk", label: "Change Risk", meta: "Deployments · approvals" },
  { value: "knowledge", label: "Knowledge Base", meta: "Runbooks · docs" },
] as const;

export function OperationsOverviewPage() {
  const active = useWorkspaceTab(operationsTabs, "overview");
  return (
    <>
      <WorkspaceTabs basePath="/operations" tabs={operationsTabs} active={active} />
      {active === "risk" ? <PredictionsPage /> : <AnalyticsDashboard />}
    </>
  );
}

export function OnboardingDataPage() {
  const active = useWorkspaceTab(onboardingTabs, "enroll");
  return (
    <>
      <WorkspaceTabs basePath="/onboarding" tabs={onboardingTabs} active={active} />
      {active === "ingestion" ? <IngestionPage /> : active === "integrations" ? <IntegrationsPage /> : <EnrollTargetPage />}
    </>
  );
}

export function ServiceTopologyPage() {
  const active = useWorkspaceTab(topologyTabs, "services");
  return (
    <>
      <WorkspaceTabs basePath="/topology" tabs={topologyTabs} active={active} />
      {active === "code" ? <CodeContextPage /> : <ApplicationsPage />}
    </>
  );
}

export function IncidentsRcaPage() {
  const active = useWorkspaceTab(incidentTabs, "incidents");
  return (
    <>
      <WorkspaceTabs basePath="/incidents-rca" tabs={incidentTabs} active={active} />
      {active === "alerts" ? (
        <AlertsPage />
      ) : active === "investigations" ? (
        <InvestigationsPage />
      ) : active === "assistant" ? (
        <AssistantPage />
      ) : (
        <IncidentsPage />
      )}
    </>
  );
}

export function AutomationChangeRiskPage() {
  const active = useWorkspaceTab(automationTabs, "risk");
  return (
    <>
      <WorkspaceTabs basePath="/automation" tabs={automationTabs} active={active} />
      {active === "knowledge" ? <DocumentsPage /> : <ChangeRiskPage />}
    </>
  );
}

export function OperationsRedirect() {
  return <RedirectWithTab to="/operations" tab="overview" />;
}

export function PredictionsRedirect() {
  return <RedirectWithTab to="/operations" tab="risk" />;
}

export function EnrollRedirect() {
  return <RedirectWithTab to="/onboarding" tab="enroll" />;
}

export function IngestionRedirect() {
  return <RedirectWithTab to="/onboarding" tab="ingestion" />;
}

export function IntegrationsRedirect() {
  return <RedirectWithTab to="/onboarding" tab="integrations" />;
}

export function CodeContextRedirect() {
  return <RedirectWithTab to="/topology" tab="code" />;
}

export function ApplicationsRedirect() {
  return <RedirectWithTab to="/topology" tab="services" />;
}

export function AlertsRedirect() {
  return <RedirectWithTab to="/incidents-rca" tab="alerts" />;
}

export function IncidentsRedirect() {
  return <RedirectWithTab to="/incidents-rca" tab="incidents" />;
}

export function InvestigationsRedirect() {
  return <RedirectWithTab to="/incidents-rca" tab="investigations" />;
}

export function AssistantRedirect() {
  return <RedirectWithTab to="/incidents-rca" tab="assistant" />;
}

export function ChangeRiskRedirect() {
  return <RedirectWithTab to="/automation" tab="risk" />;
}

export function DocumentsRedirect() {
  return <RedirectWithTab to="/automation" tab="knowledge" />;
}
