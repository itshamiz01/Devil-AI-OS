import React, { useState } from "react";
import { PageHeader, Panel } from "../components/ui";
import { useApi } from "../lib/hooks";
import { useAuth, usePrefs } from "../lib/store";
import type { Preferences } from "../lib/types";

const TIMEZONES = ["UTC", "Asia/Kolkata", "Europe/London", "America/New_York", "Asia/Singapore"];
const VIEWS = ["overview", "intelligence", "approvals", "businesses", "finance", "security"];

/**
 * §24 Settings. Interface preferences persist through the P-11 dashboard
 * preferences API (principal-scoped). Security-relevant configuration is
 * NOT here: it is governed by P-10 and shown read-only with a pointer.
 */
export function SettingsView(): React.ReactElement {
  const { prefs, save } = usePrefs();
  const { principal } = useAuth();
  const security = useApi<{ settings?: Record<string, unknown> }>("/security/policies");
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const update = async (patch: Partial<Preferences>) => {
    setNotice(null);
    setError(null);
    try {
      await save(patch);
      setNotice("Preferences saved to the backend (scoped to your principal).");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  return (
    <div className="view">
      <PageHeader title="Settings" subtitle={`Preferences for ${principal ?? "owner"} — stored server-side, per principal`} />
      {notice ? <p className="ok-text" role="status">{notice}</p> : null}
      {error ? <p className="error-text" role="alert">{error}</p> : null}

      <div className="two-col">
        <Panel title="General">
          <label className="field">
            <span>Timezone (display)</span>
            <select
              value={prefs.timezone}
              onChange={(e) => void update({ timezone: e.target.value })}
              aria-label="Timezone"
            >
              {TIMEZONES.map((tz) => (
                <option key={tz} value={tz}>{tz}</option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>Currency (consolidated finance views)</span>
            <select
              value={prefs.currency}
              onChange={(e) => void update({ currency: e.target.value })}
              aria-label="Currency"
            >
              {["INR", "USD", "EUR", "GBP"].map((c) => (
                <option key={c} value={c}>{c}</option>
              ))}
            </select>
          </label>
          <p className="muted">
            Currency selects which same-currency consolidation P-07 returns; amounts in
            other currencies are never converted or summed by this console (P-07 §14).
            Language and date/number formats follow the en-GB locale of this build.
          </p>
        </Panel>

        <Panel title="Interface">
          <label className="field checkbox">
            <input
              type="checkbox"
              checked={prefs.sidebar_collapsed}
              onChange={(e) => void update({ sidebar_collapsed: e.target.checked })}
            />
            <span>Sidebar collapsed</span>
          </label>
          <label className="field checkbox">
            <input
              type="checkbox"
              checked={prefs.reduce_motion}
              onChange={(e) => void update({ reduce_motion: e.target.checked })}
            />
            <span>Reduce motion (also honours your OS preference)</span>
          </label>
          <label className="field">
            <span>Density</span>
            <select
              value={prefs.density}
              onChange={(e) => void update({ density: e.target.value as Preferences["density"] })}
              aria-label="Density"
            >
              <option value="comfortable">Comfortable</option>
              <option value="compact">Compact</option>
            </select>
          </label>
          <label className="field">
            <span>Default landing view</span>
            <select
              value={prefs.default_view}
              onChange={(e) => void update({ default_view: e.target.value })}
              aria-label="Default landing view"
            >
              {VIEWS.map((v) => (
                <option key={v} value={v}>{v}</option>
              ))}
            </select>
          </label>
        </Panel>
      </div>

      <Panel title="AI configuration" meta="read-only here — changes are owner-governed backend operations">
        <p className="muted">
          Provider and model selection live in P-02 model profiles (Intelligence view shows
          live provider status). Changing the default provider or local/cloud preference is
          a backend configuration change under P-10 policy, so this page deliberately does
          not offer toggles for it. API keys are never displayed anywhere in this console.
        </p>
      </Panel>

      <Panel title="Security settings" meta="governed by P-10 — read-only summary">
        {security.data?.settings ? (
          <pre className="params-json">{JSON.stringify(security.data.settings, null, 2)}</pre>
        ) : (
          <p className="muted">Security policy summary unavailable.</p>
        )}
        <p className="muted">
          Session controls, policy changes and approval policies execute only through
          P-10's governed endpoints (Security view). Ordinary agents cannot see or change
          restricted configuration (§24).
        </p>
      </Panel>

      <Panel title="Notifications">
        <p className="muted">
          Notification categories follow the derived sources (approvals, security alerts,
          financial alerts, task failures, system events). Critical security and financial
          alerts cannot be dismissed from the notification centre (§5.4) — there is no
          setting that changes that rule.
        </p>
      </Panel>
    </div>
  );
}
