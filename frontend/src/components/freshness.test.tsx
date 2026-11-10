import { render, screen, waitFor } from "@testing-library/react";
import React, { useEffect } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "../lib/api";
import { AppProviders } from "../lib/store";
import { FreshnessBar } from "./ui";

// Scenario 8 (§28.7): when the backend becomes unreachable, the UI must
// say so and mark the data as stale — never keep presenting it as live.
function Probe(): React.ReactElement {
  useEffect(() => {
    void api("/dashboard/overview").catch(() => undefined);
  }, []);
  return <FreshnessBar updatedAt={Date.now()} />;
}

afterEach(() => {
  vi.unstubAllGlobals();
  localStorage.clear();
});

describe("FreshnessBar (Scenario 8)", () => {
  it("shows the connection-lost stale warning after a failed request", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new TypeError("Failed to fetch");
      }),
    );
    render(
      <AppProviders>
        <Probe />
      </AppProviders>,
    );
    await waitFor(() =>
      expect(screen.getByText(/Connection lost\./)).toBeInTheDocument(),
    );
    expect(screen.getByText(/may be stale/)).toBeInTheDocument();
    expect(screen.queryByText(/Connected ·/)).not.toBeInTheDocument();
  });
});
