import React, { useState } from "react";
import { ApprovalCard } from "../components/cards";
import {
  EmptyState,
  ErrorState,
  FreshnessBar,
  LoadingState,
  PageHeader,
  Panel,
} from "../components/ui";
import { useApi } from "../lib/hooks";
import type { Approval } from "../lib/types";

interface ApprovalsSummary {
  core_pending: number;
  agent_creation_pending: number;
  agent_creation_requests_by_status: Record<string, number>;
  spending_pending: number;
  spending_requests_by_status: Record<string, number>;
  financial_open_alerts: number;
  source: string;
}

/**
 * §18 Unified Approval Inbox. Decisions are made ONLY through the owning
 * governed endpoints (here: P-01 approvals with P-10's service-level
 * enforcement). Other pending queues are shown with counts and their real
 * by-status breakdown; their decisions live in their own views — the inbox
 * never invents a decision path that the backend does not offer.
 */
export function ApprovalsView(): React.ReactElement {
  const [status, setStatus] = useState("pending");
  const list = useApi<Approval[]>(`/approvals?status=${status}&limit=100`);
  const summary = useApi<ApprovalsSummary>("/dashboard/approvals/summary", 30000);

  return (
    <div className="view">
      <PageHeader
        title="Approval Inbox"
        subtitle="One inbox for every decision that needs you — exact parameters, hash-bound, single-use"
        actions={<FreshnessBar updatedAt={list.updatedAt} />}
      />
      {summary.data ? (
        <Panel title="Pending across the system" meta={summary.data.source}>
          <dl className="stat-row num">
            <div><dt>Core approvals pending</dt><dd>{summary.data.core_pending}</dd></div>
            <div><dt>Agent creation requests pending</dt><dd>{summary.data.agent_creation_pending}</dd></div>
            <div><dt>Spending requests pending</dt><dd>{summary.data.spending_pending}</dd></div>
            <div><dt>Open financial alerts</dt><dd>{summary.data.financial_open_alerts}</dd></div>
          </dl>
          <p className="muted">
            Agent creation requests are decided in Agents → creation requests (P-04 endpoints);
            spending requests in Finance (P-07 endpoints). Core approvals below are decided
            here, through the P-01 decision endpoint with P-10 enforcement: replay, expiry,
            parameter drift and self-approval are refused by the backend.
          </p>
        </Panel>
      ) : null}

      <div className="filter-bar" role="group" aria-label="Approval status filter">
        {["pending", "approved", "rejected", "expired"].map((s) => (
          <button
            key={s}
            type="button"
            className={`chip ${status === s ? "chip-active" : ""}`}
            onClick={() => setStatus(s)}
          >
            {s}
          </button>
        ))}
      </div>

      {list.loading && !list.data ? <LoadingState label="Loading approvals…" /> : null}
      {list.error ? <ErrorState error={list.error} onRetry={list.reload} /> : null}
      {list.data && list.data.length === 0 ? (
        <EmptyState
          title={`No ${status} approvals`}
          detail={
            status === "pending"
              ? "Nothing is waiting for your decision. Requests appear here the moment an agent or engine asks — they are never auto-approved with age."
              : `No approvals with status “${status}” exist.`
          }
        />
      ) : null}
      <div className="card-grid">
        {(list.data ?? []).map((approval) => (
          <ApprovalCard key={approval.id} approval={approval} onDecided={list.reload} />
        ))}
      </div>
    </div>
  );
}
