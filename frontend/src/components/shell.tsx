import React, { useEffect, useRef, useState } from "react";
import { api } from "../lib/api";
import { formatTime } from "../lib/format";
import { useApi, useDebounced, useNow } from "../lib/hooks";
import { navigate, type Route } from "../lib/router";
import { useAuth, useConnection, usePrefs, useShellSummary } from "../lib/store";
import type { NotificationsData, SearchResults } from "../lib/types";
import { StatusBadge } from "./ui";

export interface NavItem {
  name: string;
  label: string;
  section: string;
}

export const NAV_ITEMS: NavItem[] = [
  { name: "overview", label: "Overview", section: "Command" },
  { name: "intelligence", label: "Intelligence", section: "Command" },
  { name: "voice", label: "Voice", section: "Command" },
  { name: "knowledge", label: "Knowledge", section: "Command" },
  { name: "approvals", label: "Approvals", section: "Command" },
  { name: "opportunities", label: "Opportunities", section: "Operations" },
  { name: "agents", label: "Agents", section: "Operations" },
  { name: "execution", label: "Execution", section: "Operations" },
  { name: "autonomy", label: "Autonomous Ops", section: "Operations" },
  { name: "businesses", label: "Businesses", section: "Portfolio" },
  { name: "portfolio", label: "Business Portfolio", section: "Portfolio" },
  { name: "economy", label: "AI Economy & Expansion", section: "Portfolio" },
  { name: "growth", label: "Acquisition & Growth", section: "Portfolio" },
  { name: "experience", label: "Customer Experience", section: "Portfolio" },
  { name: "finance", label: "Finance", section: "Portfolio" },
  { name: "survival", label: "Survival & Scaling", section: "Portfolio" },
  { name: "memory", label: "Memory & Learning", section: "Intelligence" },
  { name: "security", label: "Security", section: "Governance" },
  { name: "integrations", label: "Integrations", section: "Governance" },
  { name: "operations", label: "Operations", section: "Governance" },
  { name: "performance", label: "Performance & Reliability", section: "Governance" },
  { name: "reports", label: "Reports", section: "Governance" },
  { name: "settings", label: "Settings", section: "Governance" },
];

const SECTIONS = ["Command", "Operations", "Portfolio", "Intelligence", "Governance"];

// ---------------------------------------------------------------- Sidebar
export function Sidebar({ route }: { route: Route }): React.ReactElement {
  const { prefs, save } = usePrefs();
  const summary = useShellSummary();
  const collapsed = prefs.sidebar_collapsed;
  const counters: Record<string, number | null> = {
    approvals: summary.pendingApprovals,
    security: summary.criticalAlerts,
  };
  return (
    <nav className={`sidebar ${collapsed ? "sidebar-collapsed" : ""}`} aria-label="Primary">
      <div className="sidebar-brand">
        <span className="brand-mark" aria-hidden="true">A</span>
        {!collapsed ? (
          <span className="brand-text">
            AUTONOMUS
            <small>Command Center</small>
          </span>
        ) : null}
      </div>
      {SECTIONS.map((section) => (
        <div className="nav-section" key={section}>
          {!collapsed ? <h2 className="nav-section-title">{section}</h2> : null}
          <ul>
            {NAV_ITEMS.filter((i) => i.section === section).map((item) => {
              const count = counters[item.name];
              const active = route.name === item.name;
              return (
                <li key={item.name}>
                  <button
                    type="button"
                    className={`nav-item ${active ? "nav-item-active" : ""}`}
                    aria-current={active ? "page" : undefined}
                    title={item.label}
                    onClick={() => navigate(item.name)}
                  >
                    <span className="nav-label">{collapsed ? item.label.slice(0, 2) : item.label}</span>
                    {/* §5.1: counters only when data exists and is > 0 */}
                    {count !== null && count !== undefined && count > 0 ? (
                      <span className="nav-count" aria-label={`${count} pending`}>
                        {count}
                      </span>
                    ) : null}
                  </button>
                </li>
              );
            })}
          </ul>
        </div>
      ))}
      <button
        type="button"
        className="sidebar-toggle"
        aria-expanded={!collapsed}
        onClick={() => void save({ sidebar_collapsed: !collapsed }).catch(() => undefined)}
      >
        {collapsed ? "Expand" : "Collapse"}
      </button>
    </nav>
  );
}

// ------------------------------------------------------------ TopStatusBar
export function TopStatusBar({ onOpenPalette, onOpenNotifications }: {
  onOpenPalette: () => void;
  onOpenNotifications: () => void;
}): React.ReactElement {
  const { principal, logout } = useAuth();
  const { prefs } = usePrefs();
  const summary = useShellSummary();
  const { online } = useConnection();
  const now = useNow(1000);
  const models = useApi<{ providers: Record<string, { available: boolean; detail: string }>; mode: string }>(
    "/models/status",
    60000,
  );
  const providerBits = models.data
    ? Object.entries(models.data.providers ?? {})
        .map(([name, p]) => `${name}: ${p.available ? "available" : "unavailable"}`)
        .join(" · ")
    : "provider status unknown";
  return (
    <header className="topbar">
      <div className="topbar-state">
        <StatusBadge value={online ? (summary.operatingState ?? "unknown") : "offline"} />
        <span className="topbar-mode">
          {summary.operatingState ? `state: ${summary.operatingState.replace(/_/g, " ")}` : "state: unknown"}
        </span>
      </div>
      <div className="topbar-clock num" title={`Timezone: ${prefs.timezone}`}>
        {formatTime(new Date(now).toISOString(), prefs.timezone)}
        <span className="topbar-tz"> {prefs.timezone}</span>
      </div>
      <div className="topbar-providers" title={providerBits}>
        AI: {providerBits}
      </div>
      <div className="topbar-counters num">
        <span>Approvals: {summary.pendingApprovals ?? "—"}</span>
        <span>Alerts: {summary.criticalAlerts ?? "—"}</span>
      </div>
      <div className="topbar-actions">
        <button type="button" className="btn btn-small" onClick={onOpenPalette} aria-label="Open command palette (Control K)">
          Search / Command <kbd>Ctrl K</kbd>
        </button>
        <button
          type="button"
          className="btn btn-small"
          onClick={onOpenNotifications}
          aria-label={`Notifications, ${summary.unreadNotifications ?? 0} unread`}
        >
          Notifications
          {summary.unreadNotifications !== null && summary.unreadNotifications > 0 ? (
            <span className="nav-count">{summary.unreadNotifications}</span>
          ) : null}
        </button>
        <span className="topbar-principal" title="Signed-in principal">
          {principal ?? "owner"}
        </span>
        <button type="button" className="btn btn-small" onClick={logout}>
          Sign out
        </button>
      </div>
    </header>
  );
}

// ------------------------------------------------------- NotificationCenter
export function NotificationCenter({ open, onClose }: { open: boolean; onClose: () => void }): React.ReactElement | null {
  const notes = useApi<NotificationsData>(open ? "/dashboard/notifications" : null);
  const [filter, setFilter] = useState<string>("all");
  const [actionError, setActionError] = useState<string | null>(null);
  if (!open) return null;
  const items = (notes.data?.items ?? []).filter(
    (n) => filter === "all" || (filter === "unread" ? !n.is_read : n.kind === filter),
  );
  const act = async (id: string, kind: "read" | "dismiss") => {
    setActionError(null);
    try {
      await api(`/dashboard/notifications/${id}/${kind}`, { method: "POST" });
      notes.reload();
    } catch (err) {
      // e.g. §5.4: critical alerts refuse dismissal — surface, never hide.
      setActionError(err instanceof Error ? err.message : String(err));
    }
  };
  return (
    <div className="drawer-overlay" role="presentation" onClick={onClose}>
      <aside
        className="drawer"
        role="dialog"
        aria-label="Notification centre"
        onClick={(e) => e.stopPropagation()}
        onKeyDown={(e) => {
          if (e.key === "Escape") onClose();
        }}
      >
        <header className="drawer-header">
          <h2>Notifications</h2>
          <button type="button" className="btn btn-small" onClick={onClose}>
            Close
          </button>
        </header>
        <div className="drawer-filters" role="group" aria-label="Filter notifications">
          {["all", "unread", "approval", "security_alert", "financial_alert", "task_failure", "system_event"].map((f) => (
            <button
              key={f}
              type="button"
              className={`chip ${filter === f ? "chip-active" : ""}`}
              onClick={() => setFilter(f)}
            >
              {f.replace(/_/g, " ")}
            </button>
          ))}
        </div>
        {actionError ? <p className="error-text" role="alert">{actionError}</p> : null}
        {notes.loading ? <p className="muted">Loading notifications…</p> : null}
        {notes.error ? <p className="error-text">{notes.error.message}</p> : null}
        {notes.data && items.length === 0 ? (
          <p className="muted">No notifications match. Notifications are derived live from approvals, alerts, failed tasks and system events.</p>
        ) : null}
        <ul className="notification-list">
          {items.map((n) => (
            <li key={n.id} className={`notification ${n.is_read ? "" : "notification-unread"}`}>
              <StatusBadge value={n.severity} />
              <div className="notification-body">
                <button
                  type="button"
                  className="notification-title"
                  onClick={() => {
                    onClose();
                    const target = n.link.replace(/^#\//, "");
                    navigate(target);
                  }}
                >
                  {n.title}
                </button>
                {n.detail ? <p className="notification-detail">{n.detail}</p> : null}
                <div className="notification-actions">
                  {!n.is_read ? (
                    <button type="button" className="btn btn-small" onClick={() => void act(n.id, "read")}>
                      Mark read
                    </button>
                  ) : null}
                  <button type="button" className="btn btn-small" onClick={() => void act(n.id, "dismiss")}>
                    Dismiss
                  </button>
                </div>
              </div>
            </li>
          ))}
        </ul>
        {notes.data ? <p className="muted drawer-note">{notes.data.note}</p> : null}
      </aside>
    </div>
  );
}

// ---------------------------------------------------------- CommandPalette
const PALETTE_COMMANDS: { label: string; run: () => void; sensitiveNote?: string }[] = [
  { label: "Open Overview", run: () => navigate("overview") },
  { label: "Open Businesses", run: () => navigate("businesses") },
  { label: "Open Agents", run: () => navigate("agents") },
  { label: "Search Opportunities", run: () => navigate("opportunities") },
  { label: "View Pending Approvals", run: () => navigate("approvals") },
  { label: "Open Finance", run: () => navigate("finance") },
  { label: "View Security Alerts", run: () => navigate("security") },
  { label: "Open System Health", run: () => navigate("operations") },
  {
    label: "Pause Autonomous Operations",
    run: () => navigate("security"),
    sensitiveNote: "opens Security — the emergency control itself requires P-10 confirmation there",
  },
];

export function CommandPalette({ open, onClose }: { open: boolean; onClose: () => void }): React.ReactElement | null {
  const [query, setQuery] = useState("");
  const debounced = useDebounced(query, 300);
  const inputRef = useRef<HTMLInputElement>(null);
  const search = useApi<SearchResults>(
    open && debounced.trim().length >= 2 ? `/dashboard/search?q=${encodeURIComponent(debounced.trim())}` : null,
  );
  useEffect(() => {
    if (open) {
      setQuery("");
      window.setTimeout(() => inputRef.current?.focus(), 30);
    }
  }, [open ]);
  if (!open) return null;
  const commands = PALETTE_COMMANDS.filter((c) =>
    c.label.toLowerCase().includes(query.toLowerCase()),
  );
  const go = (link: string) => {
    onClose();
    const [name, param] = link.replace(/^#\//, "").split("/");
    navigate(name, param ?? null);
  };
  return (
    <div className="palette-overlay" role="presentation" onClick={onClose}>
      <div
        className="palette"
        role="dialog"
        aria-modal="true"
        aria-label="Command palette"
        onClick={(e) => e.stopPropagation()}
        onKeyDown={(e) => {
          if (e.key === "Escape") onClose();
        }}
      >
        <input
          ref={inputRef}
          className="palette-input"
          type="search"
          placeholder="Search businesses, agents, tasks, memory… or type a command"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          aria-label="Search or command"
        />
        <div className="palette-results">
          {commands.length > 0 ? (
            <section>
              <h3>Commands</h3>
              <ul>
                {commands.map((c) => (
                  <li key={c.label}>
                    <button
                      type="button"
                      className="palette-item"
                      onClick={() => {
                        onClose();
                        c.run();
                      }}
                    >
                      {c.label}
                      {c.sensitiveNote ? <small>{c.sensitiveNote}</small> : null}
                    </button>
                  </li>
                ))}
              </ul>
            </section>
          ) : null}
          {debounced.trim().length >= 2 ? (
            <section>
              <h3>Search results {search.data ? `(${search.data.total})` : ""}</h3>
              {search.loading ? <p className="muted">Searching…</p> : null}
              {search.error ? <p className="error-text">{search.error.message}</p> : null}
              {search.data && search.data.total === 0 ? (
                <p className="muted">No results in any scope for “{debounced.trim()}”.</p>
              ) : null}
              {search.data
                ? Object.entries(search.data.results).map(([kind, hits]) =>
                    hits.length > 0 ? (
                      <div key={kind} className="palette-group">
                        <h4>{kind.replace(/_/g, " ")}</h4>
                        <ul>
                          {hits.map((hit) => (
                            <li key={`${kind}-${hit.id}`}>
                              <button type="button" className="palette-item" onClick={() => go(hit.link)}>
                                {hit.label}
                                <small className="mono">{hit.id}</small>
                              </button>
                            </li>
                          ))}
                        </ul>
                      </div>
                    ) : null,
                  )
                : null}
              {search.data ? <p className="muted palette-note">{search.data.note}</p> : null}
            </section>
          ) : null}
          <p className="muted palette-note">
            Search never executes actions. Sensitive operations are performed only in their
            own views, through P-10 authorization (§20.1). To give the Master Intelligence an
            instruction, open Intelligence and submit it there.
          </p>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- AppShell
export function AppShell({ route, children }: { route: Route; children: React.ReactNode }): React.ReactElement {
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [notesOpen, setNotesOpen] = useState(false);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPaletteOpen((v) => !v);
      }
      if (e.key === "Escape") {
        setPaletteOpen(false);
        setNotesOpen(false);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
  return (
    <div className="shell">
      <Sidebar route={route} />
      <div className="shell-main">
        <TopStatusBar
          onOpenPalette={() => setPaletteOpen(true)}
          onOpenNotifications={() => setNotesOpen(true)}
        />
        <main className="content" id="main-content">
          {children}
        </main>
      </div>
      <NotificationCenter open={notesOpen} onClose={() => setNotesOpen(false)} />
      <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} />
    </div>
  );
}
