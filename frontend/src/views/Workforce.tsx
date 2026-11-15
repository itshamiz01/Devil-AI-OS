import React, { useState } from "react";
import {
  EmptyState,
  ErrorState,
  FreshnessBar,
  LoadingState,
  PageHeader,
  Panel,
} from "../components/ui";
import { ShinyText } from "../components/ShinyText";
import { useApi } from "../lib/hooks";

interface WorkforceOverview {
  total_employees: number;
  ceo: number;
  managers: number;
  employees: number;
  departments: number;
  work_orders_total: number;
  available: number;
  busy: number;
  blocked: number;
  suspended: number;
  disabled: number;
}

interface Department {
  code: string;
  name: string;
  mission: string;
  manager_code: string | null;
  manager_title: string | null;
  employee_count: number;
}

interface ObjectiveRow {
  id: string;
  title: string;
  status: string;
  plan: { department_code: string; manager_code: string }[];
  restricted_actions: string[];
  created_at: string | null;
}

interface EmployeeRow {
  employee_code: string;
  job_title: string;
  level: string;
  department_code: string | null;
  manager_code: string | null;
  workforce_status: string;
}

/**
 * Agentic Workforce (111 baseline employees): read-only organization
 * view over the /workforce API. Seeding and lifecycle control are
 * owner actions exercised through the API; this view never invents
 * counts — everything comes from the database via the service.
 */
export function WorkforceView(): React.ReactElement {
  const [department, setDepartment] = useState("");
  const overview = useApi<WorkforceOverview>("/workforce/overview", 30000);
  const ceo = useApi<EmployeeRow[]>("/workforce/employees?level=ceo");
  const objectives = useApi<ObjectiveRow[]>("/workforce/objectives?limit=10");
  const departments = useApi<Department[]>("/workforce/departments");
  const employees = useApi<EmployeeRow[]>(
    `/workforce/employees?limit=200${department ? `&department_code=${department}` : ""}`,
  );

  return (
    <div className="view">
      <PageHeader
        title="Workforce"
        subtitle="The 111-employee organization: 1 CEO, 10 department managers, 100 specialized employees"
        actions={<FreshnessBar updatedAt={overview.updatedAt} />}
      />
      {overview.loading && !overview.data ? <LoadingState label="Loading workforce…" /> : null}
      {overview.error ? <ErrorState error={overview.error} onRetry={overview.reload} /> : null}
      {overview.data ? (
        <Panel title="Organization" meta="counts from the database">
          <dl className="stat-row num">
            <div><dt>Total employees</dt><dd>{overview.data.total_employees}</dd></div>
            <div><dt>CEO</dt><dd>{overview.data.ceo}</dd></div>
            <div><dt>Managers</dt><dd>{overview.data.managers}</dd></div>
            <div><dt>Employees</dt><dd>{overview.data.employees}</dd></div>
            <div><dt>Departments</dt><dd>{overview.data.departments}</dd></div>
            <div><dt>Work orders</dt><dd>{overview.data.work_orders_total}</dd></div>
          </dl>
          <p className="muted">
            Available {overview.data.available} · Busy {overview.data.busy} · Blocked{" "}
            {overview.data.blocked} · Suspended {overview.data.suspended} · Disabled{" "}
            {overview.data.disabled}
          </p>
        </Panel>
      ) : null}

      {ceo.data && ceo.data.length > 0 ? (
        <Panel title="CEO Office" meta="DEV-CEO-001 · reports to the Owner">
          <h3>
            <ShinyText text={ceo.data[0].job_title} />
          </h3>
          <p className="muted">
            Status: {ceo.data[0].workforce_status}. The CEO plans and coordinates;
            restricted actions escalate to owner approval — the CEO cannot approve them.
          </p>
          {objectives.data && objectives.data.length > 0 ? (
            <table className="table">
              <thead>
                <tr><th>Objective</th><th>Status</th><th>Departments</th><th>Restricted</th></tr>
              </thead>
              <tbody>
                {objectives.data.map((o) => (
                  <tr key={o.id}>
                    <td>{o.title}</td>
                    <td>{o.status}</td>
                    <td>{o.plan.map((p) => p.department_code).join(", ") || "—"}</td>
                    <td>{o.restricted_actions.length > 0 ? "owner approval" : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p className="muted">No objectives submitted yet.</p>
          )}
        </Panel>
      ) : null}

      {departments.data ? (
        <Panel title="Departments">
          <div className="card-grid">
            {departments.data.map((d) => (
              <article key={d.code} className="card">
                <h3>{d.name}</h3>
                <p className="muted">{d.mission}</p>
                <p>
                  {d.manager_title ?? "—"} ({d.manager_code ?? "—"}) · manager +{" "}
                  {d.employee_count} employees
                </p>
              </article>
            ))}
          </div>
        </Panel>
      ) : null}

      <div className="filter-bar" role="group" aria-label="Department filter">
        <button
          type="button"
          className={`chip ${department === "" ? "chip-active" : ""}`}
          onClick={() => setDepartment("")}
        >
          All departments
        </button>
        {(departments.data ?? []).map((d) => (
          <button
            key={d.code}
            type="button"
            className={`chip ${department === d.code ? "chip-active" : ""}`}
            onClick={() => setDepartment(d.code)}
          >
            {d.code}
          </button>
        ))}
      </div>

      {employees.data && employees.data.length === 0 ? (
        <EmptyState
          title="No employees yet"
          detail="The workforce has not been seeded. Seed it once via POST /workforce/seed (owner) — it is idempotent."
        />
      ) : null}
      {employees.data ? (
        <Panel title={`Employees (${employees.data.length})`}>
          <table className="table">
            <thead>
              <tr><th>Code</th><th>Title</th><th>Level</th><th>Dept</th><th>Reports to</th><th>Status</th></tr>
            </thead>
            <tbody>
              {employees.data.map((e) => (
                <tr key={e.employee_code}>
                  <td>{e.employee_code}</td>
                  <td>{e.job_title}</td>
                  <td>{e.level}</td>
                  <td>{e.department_code ?? "—"}</td>
                  <td>{e.manager_code ?? "Owner"}</td>
                  <td>{e.workforce_status}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Panel>
      ) : null}
    </div>
  );
}
