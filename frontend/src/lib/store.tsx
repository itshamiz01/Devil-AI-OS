import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { api, getToken, login as apiLogin, logout as apiLogout, onConnectionChange } from "./api";
import type { NotificationsData, Preferences } from "./types";

// ------------------------------------------------------------------ auth
interface AuthState {
  token: string | null;
  principal: string | null;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthState>({
  token: null,
  principal: null,
  login: async () => undefined,
  logout: () => undefined,
});

export function useAuth(): AuthState {
  return useContext(AuthContext);
}

// ------------------------------------------------------------ preferences
const DEFAULT_PREFS: Preferences = {
  sidebar_collapsed: false,
  default_view: "overview",
  timezone: "UTC",
  currency: "INR",
  density: "comfortable",
  reduce_motion: false,
};

interface PrefsState {
  prefs: Preferences;
  save: (patch: Partial<Preferences>) => Promise<void>;
}

const PrefsContext = createContext<PrefsState>({
  prefs: DEFAULT_PREFS,
  save: async () => undefined,
});

export function usePrefs(): PrefsState {
  return useContext(PrefsContext);
}

// ------------------------------------------------------------- connection
interface ConnectionState {
  online: boolean;
  lastOkAt: number | null;
}

const ConnectionContext = createContext<ConnectionState>({ online: true, lastOkAt: null });

export function useConnection(): ConnectionState {
  return useContext(ConnectionContext);
}

// ------------------------------------------------------- shell summaries
export interface ShellSummary {
  pendingApprovals: number | null;
  criticalAlerts: number | null;
  unreadNotifications: number | null;
  operatingState: string | null;
}

const ShellContext = createContext<ShellSummary>({
  pendingApprovals: null,
  criticalAlerts: null,
  unreadNotifications: null,
  operatingState: null,
});

export function useShellSummary(): ShellSummary {
  return useContext(ShellContext);
}

export function AppProviders({ children }: { children: React.ReactNode }): React.ReactElement {
  const [token, setToken] = useState<string | null>(() => getToken());
  const [principal, setPrincipal] = useState<string | null>(null);
  const [prefs, setPrefs] = useState<Preferences>(DEFAULT_PREFS);
  const [online, setOnline] = useState(true);
  const [lastOkAt, setLastOkAt] = useState<number | null>(null);
  const [summary, setSummary] = useState<ShellSummary>({
    pendingApprovals: null,
    criticalAlerts: null,
    unreadNotifications: null,
    operatingState: null,
  });

  useEffect(() => onConnectionChange((ok, at) => {
    setOnline(ok);
    if (ok) setLastOkAt(at);
  }), []);

  const login = useCallback(async (username: string, password: string) => {
    const issued = await apiLogin(username, password);
    setToken(issued);
    setPrincipal(`owner:${username}`);
  }, []);

  const logout = useCallback(() => {
    apiLogout();
    setToken(null);
    setPrincipal(null);
  }, []);

  // Who am I — confirms the stored token still resolves (Scenario: an
  // expired token must return the user to the login gate, never a
  // half-authenticated shell).
  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    api<{ principal_type: string; principal_id: string }>("/auth/me")
      .then((r) => {
        if (!cancelled) setPrincipal(`${r.data.principal_type}:${r.data.principal_id}`);
      })
      .catch(() => {
        if (!cancelled) logout();
      });
    return () => {
      cancelled = true;
    };
  }, [token, logout]);

  // Preferences are backend-owned per principal (P-11 dashboard API);
  // until loaded, honest defaults apply.
  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    api<{ preferences: Preferences }>("/dashboard/preferences")
      .then((r) => {
        if (!cancelled) setPrefs({ ...DEFAULT_PREFS, ...r.data.preferences });
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [token]);

  const save = useCallback(
    async (patch: Partial<Preferences>) => {
      const r = await api<{ preferences: Preferences }>("/dashboard/preferences", {
        method: "PUT",
        body: patch,
      });
      setPrefs({ ...DEFAULT_PREFS, ...r.data.preferences });
    },
    [],
  );

  // Shell counters: bounded polling, visible tab only (§27).
  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    const load = async () => {
      if (document.visibilityState !== "visible") return;
      try {
        const [overview, notes] = await Promise.all([
          api<{ counts: { pending_approvals: number; critical_alerts: number }; operating_state: string }>("/dashboard/overview"),
          api<NotificationsData>("/dashboard/notifications"),
        ]);
        if (cancelled) return;
        setSummary({
          pendingApprovals: overview.data.counts.pending_approvals,
          criticalAlerts: overview.data.counts.critical_alerts,
          unreadNotifications: notes.data.unread,
          operatingState: overview.data.operating_state,
        });
      } catch {
        if (!cancelled) {
          setSummary((s) => ({ ...s }));
        }
      }
    };
    void load();
    const timer = window.setInterval(load, 30000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [token]);

  const authValue = useMemo<AuthState>(
    () => ({ token, principal, login, logout }),
    [token, principal, login, logout],
  );
  const prefsValue = useMemo<PrefsState>(() => ({ prefs, save }), [prefs, save]);
  const connValue = useMemo<ConnectionState>(() => ({ online, lastOkAt }), [online, lastOkAt]);

  return (
    <AuthContext.Provider value={authValue}>
      <PrefsContext.Provider value={prefsValue}>
        <ConnectionContext.Provider value={connValue}>
          <ShellContext.Provider value={summary}>{children}</ShellContext.Provider>
        </ConnectionContext.Provider>
      </PrefsContext.Provider>
    </AuthContext.Provider>
  );
}
