import React, { useState } from "react";
import { ApiError } from "../lib/api";
import { useAuth } from "../lib/store";

/**
 * Login gate. Authentication is P-01's (scrypt-hashed owner account,
 * bearer session tokens, lockout + P-10 login guard). This page only
 * collects credentials and hands them to the backend — an unauthenticated
 * visitor sees nothing else (Scenario: protected pages are unreachable).
 */
export function LoginView(): React.ReactElement {
  const { login } = useAuth();
  const [username, setUsername] = useState("owner");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(username, password);
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.code === "connection_failed"
            ? "Cannot reach the AUTONOMUS backend. Is the server running?"
            : "Invalid username or password."
          : String(err),
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="login-wrap">
      <form className="login-card" onSubmit={submit} aria-label="Sign in">
        <div className="login-brand">
          <span className="brand-mark" aria-hidden="true">A</span>
          <div>
            <h1>AUTONOMUS</h1>
            <p>Command Center</p>
          </div>
        </div>
        <label className="field">
          <span>Username</span>
          <input
            type="text"
            autoComplete="username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            required
          />
        </label>
        <label className="field">
          <span>Password</span>
          <input
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </label>
        {error ? <p className="error-text" role="alert">{error}</p> : null}
        <button type="submit" className="btn btn-primary login-submit" disabled={busy}>
          {busy ? "Signing in…" : "Sign in"}
        </button>
        <p className="muted login-note">
          Access is enforced by the backend on every request. This page stores only your
          session token in this browser.
        </p>
      </form>
    </main>
  );
}
