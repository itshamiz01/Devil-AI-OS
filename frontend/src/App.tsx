import React, { useEffect } from "react";
import { AppShell } from "./components/shell";
import { navigate, useRoute } from "./lib/router";
import { AppProviders, useAuth, usePrefs } from "./lib/store";
import { AgentDetailView, AgentsView } from "./views/Agents";
import { ApprovalsView } from "./views/Approvals";
import { AutonomyView } from "./views/Autonomy";
import { BusinessDetailView, BusinessesView } from "./views/Businesses";
import { EconomyView } from "./views/Economy";
import { GrowthView } from "./views/Growth";
import { ExperienceView } from "./views/Experience";
import { ExecutionView } from "./views/Execution";
import { FinanceView } from "./views/Finance";
import { IntelligenceView } from "./views/Intelligence";
import { IntegrationsView } from "./views/Integrations";
import { KnowledgeView } from "./views/Knowledge";
import { VoiceView } from "./views/Voice";
import { LoginView } from "./views/Login";
import { MemoryView } from "./views/Memory";
import { OperationsView } from "./views/Operations";
import { OpportunitiesView, OpportunityDetailView } from "./views/Opportunities";
import { OverviewView } from "./views/Overview";
import { PortfolioView } from "./views/Portfolio";
import { PerformanceView } from "./views/Performance";
import { ReportsView } from "./views/Reports";
import { SecurityView } from "./views/Security";
import { SettingsView } from "./views/Settings";
import { SurvivalView } from "./views/Survival";

function RoutedContent(): React.ReactElement {
  const route = useRoute();
  const { prefs } = usePrefs();

  // Honour the stored default landing view on a bare root visit.
  useEffect(() => {
    if (route.raw === "" && prefs.default_view && prefs.default_view !== "overview") {
      navigate(prefs.default_view);
    }
    // Only on mount / when the preference first loads.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [prefs.default_view]);

  switch (route.name) {
    case "overview":
      return <OverviewView />;
    case "intelligence":
      return <IntelligenceView />;
    case "opportunities":
      return route.param ? (
        <OpportunityDetailView opportunityId={route.param} />
      ) : (
        <OpportunitiesView />
      );
    case "agents":
      return route.param ? <AgentDetailView agentId={route.param} /> : <AgentsView />;
    case "execution":
      return <ExecutionView />;
    case "autonomy":
      return <AutonomyView />;
    case "businesses":
      return route.param ? (
        <BusinessDetailView businessId={route.param} />
      ) : (
        <BusinessesView />
      );
    case "finance":
      return <FinanceView />;
    case "survival":
      return <SurvivalView />;
    case "memory":
      return <MemoryView />;
    case "security":
      return <SecurityView />;
    case "integrations":
      return <IntegrationsView />;
    case "voice":
      return <VoiceView />;
    case "knowledge":
      return <KnowledgeView />;
    case "approvals":
      return <ApprovalsView />;
    case "operations":
      return <OperationsView />;
    case "performance":
      return <PerformanceView />;
    case "portfolio":
      return <PortfolioView />;
    case "economy":
      return <EconomyView />;
    case "growth":
      return <GrowthView />;
    case "experience":
      return <ExperienceView />;
    case "reports":
      return <ReportsView />;
    case "settings":
      return <SettingsView />;
    default:
      return <OverviewView />;
  }
}

function Gate(): React.ReactElement {
  const { token } = useAuth();
  const { prefs } = usePrefs();
  const route = useRoute();
  // §24 interface preferences take effect globally.
  useEffect(() => {
    document.documentElement.dataset.density = prefs.density;
    document.documentElement.dataset.motion = prefs.reduce_motion ? "reduced" : "full";
  }, [prefs.density, prefs.reduce_motion]);
  if (!token) return <LoginView />;
  return (
    <AppShell route={route}>
      <RoutedContent />
    </AppShell>
  );
}

export default function App(): React.ReactElement {
  return (
    <AppProviders>
      <Gate />
    </AppProviders>
  );
}
