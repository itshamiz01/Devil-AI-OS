// Types for backend payloads consumed by the Command Center. Field names
// mirror the backend's actual responses (verified in the P-11 Stage-1
// audit against a live instance).

export interface Metric {
  key: string;
  label: string;
  value: number | null;
  unit?: string | null;
  period: string;
  source: string;
  note?: string | null;
  state: "ok" | "unavailable";
  measured_at: string;
}

export interface OverviewData {
  operating_state: string;
  lifecycle_state: string;
  mode: string;
  security_mode: string;
  financial_suspension: boolean;
  database_healthy: boolean;
  threshold_violations: { resource: string; value: number; threshold: number }[];
  queue: { capacity: number; depth: number; running: number; by_status: Record<string, number> };
  counts: {
    businesses_total: number;
    businesses_by_status: Record<string, number>;
    agents_total: number;
    agents_by_status: Record<string, number>;
    opportunities_total: number;
    opportunities_by_status: Record<string, number>;
    tasks_by_status: Record<string, number>;
    pending_approvals: number;
    open_security_alerts: number;
    critical_alerts: number;
  };
  kpis: Metric[];
  finance: {
    currency: string;
    totals: { net_collected_minor: number; expenses_minor: number; net_profit_minor: number };
    businesses: { business_id: string; net_collected_minor: number; expenses_minor: number; net_profit_minor: number; is_fixture: boolean }[];
    internal_transfers_excluded: boolean;
    note: string;
    source: string;
  };
  measured_at: string;
}

export interface HealthCheck {
  key: string;
  label: string;
  state: "ok" | "degraded" | "down" | "unavailable";
  detail: string;
  source: string;
  measured_at: string;
}

export interface SystemHealthData {
  checks: HealthCheck[];
  overall: string;
  measured_at: string;
  // P-14 Stage B (DEF-A3): §14 monitoring surface completion.
  resources?: {
    cpu_percent: number | null;
    memory_percent: number | null;
    disk_percent: number | null;
    threshold_violations: { resource: string; value: number; threshold: number }[];
    source: string;
  };
  modules?: { module: string; state: string; checks: string[] }[];
  event_dead_letters?: number;
}

export interface ActivityItem {
  event_id: string;
  event_type: string;
  source: string;
  severity: string;
  task_id: string | null;
  payload: Record<string, unknown>;
  created_at: string;
  link: string | null;
}

export interface AttentionItem {
  kind: string;
  severity: string;
  title: string;
  detail: string;
  ref_id: string;
  link: string;
  created_at: string | null;
}

export interface NotificationItem {
  id: string;
  kind: string;
  severity: string;
  title: string;
  detail: string;
  link: string;
  dismissible: boolean;
  is_read: boolean;
  created_at: string | null;
}

export interface NotificationsData {
  items: NotificationItem[];
  unread: number;
  total: number;
  measured_at: string;
  note: string;
}

export interface Approval {
  id: string;
  requesting_principal_type: string;
  requesting_principal_id: string;
  action: string;
  resource: string | null;
  risk_classification: string;
  reason: string | null;
  requested_permissions: string[];
  parameters: Record<string, unknown>;
  parameters_hash: string;
  status: string;
  approver_id: string | null;
  decision_at: string | null;
  decision_notes: string | null;
  expires_at: string | null;
  created_at: string;
}

export interface Preferences {
  sidebar_collapsed: boolean;
  default_view: string;
  timezone: string;
  currency: string;
  density: "comfortable" | "compact";
  reduce_motion: boolean;
}

export interface SearchResults {
  query: string;
  total: number;
  results: Record<string, { kind: string; id: string; label: string; detail: string; link: string }[]>;
  note: string;
}
