import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { AppProviders } from "../lib/store";
import { ConfirmationDialog, DataTable, EmptyState, MetricCard } from "./ui";

describe("MetricCard (§21)", () => {
  it("formats money metrics from minor units", () => {
    render(
      <AppProviders>
        <MetricCard
          metric={{
            key: "collected_revenue", label: "Collected revenue", value: 100000,
            unit: "INR", period: "current", source: "P-07", note: null,
            state: "ok", measured_at: "2026-11-09T10:00:00Z",
          }}
        />
      </AppProviders>,
    );
    expect(screen.getByText("₹1,000.00")).toBeInTheDocument();
    expect(screen.getByText("P-07")).toBeInTheDocument();
  });

  it("shows an unavailable metric honestly, never as zero (§2 rule 3)", () => {
    render(
      <AppProviders>
        <MetricCard
          metric={{
            key: "available_cash", label: "Available cash", value: null,
            unit: "INR", period: "current", source: "P-07", note: "per-business only",
            state: "unavailable", measured_at: "2026-11-09T10:00:00Z",
          }}
        />
      </AppProviders>,
    );
    expect(screen.getByText("Unavailable")).toBeInTheDocument();
    expect(screen.queryByText("₹0.00")).not.toBeInTheDocument();
  });
});

describe("EmptyState / DataTable (§22 honest states)", () => {
  it("renders the empty state with its explanation", () => {
    render(<EmptyState title="No businesses yet" detail="Nothing has been created." />);
    expect(screen.getByText("No businesses yet")).toBeInTheDocument();
    expect(screen.getByText("Nothing has been created.")).toBeInTheDocument();
  });
  it("DataTable falls back to the empty state for zero rows", () => {
    render(
      <DataTable
        columns={[{ key: "a", label: "A" }]}
        rows={[]}
        emptyTitle="No rows"
        emptyDetail="There is nothing to show."
      />,
    );
    expect(screen.getByText("No rows")).toBeInTheDocument();
  });
  it("DataTable renders rows", () => {
    render(
      <DataTable
        columns={[{ key: "a", label: "Alpha" }]}
        rows={[{ a: "one" }, { a: "two" }]}
        emptyTitle="No rows"
        emptyDetail="—"
      />,
    );
    expect(screen.getByText("one")).toBeInTheDocument();
    expect(screen.getByText("two")).toBeInTheDocument();
  });
});

describe("ConfirmationDialog (§21)", () => {
  it("fires confirm and cancel, and renders nothing when closed", async () => {
    const onConfirm = vi.fn();
    const onCancel = vi.fn();
    const user = userEvent.setup();
    const { rerender } = render(
      <ConfirmationDialog
        open
        title="Do the thing?"
        body={<p>Body text</p>}
        confirmLabel="Do it"
        onConfirm={onConfirm}
        onCancel={onCancel}
      />,
    );
    await user.click(screen.getByRole("button", { name: "Do it" }));
    expect(onConfirm).toHaveBeenCalledTimes(1);
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(onCancel).toHaveBeenCalledTimes(1);
    rerender(
      <ConfirmationDialog
        open={false}
        title="Do the thing?"
        body={<p>Body text</p>}
        confirmLabel="Do it"
        onConfirm={onConfirm}
        onCancel={onCancel}
      />,
    );
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});
