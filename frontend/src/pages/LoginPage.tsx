import { useState, type FormEvent } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { loginUser } from "../lib/api";
import { useAuth } from "../lib/auth";

export function LoginPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const { refresh } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const redirectTo = (location.state as { from?: string } | null)?.from || "/";

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    if (!username.trim() || !password) return;
    setSubmitting(true);
    setError(null);
    try {
      await loginUser(username.trim(), password);
      await refresh();
      navigate(redirectTo, { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div
      style={{
        minHeight: "100vh",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: "var(--color-bg, #0b1120)",
        padding: "1.5rem",
      }}
    >
      <div
        style={{
          width: "100%",
          maxWidth: "380px",
          background: "var(--color-surface, #111827)",
          border: "1px solid var(--color-border, #1f2937)",
          borderRadius: "0.6rem",
          padding: "2rem 2rem 1.75rem",
          boxShadow: "0 12px 32px rgba(0,0,0,0.35)",
        }}
      >
        <div style={{ textAlign: "center", marginBottom: "1.5rem" }}>
          <div
            style={{
              display: "inline-flex",
              alignItems: "center",
              justifyContent: "center",
              width: "44px",
              height: "44px",
              borderRadius: "0.5rem",
              background: "var(--color-accent, #2563eb)",
              color: "#fff",
              fontWeight: 700,
              letterSpacing: "0.04em",
              fontSize: "0.85rem",
              marginBottom: "0.85rem",
            }}
          >
            OM
          </div>
          <h1 style={{ fontSize: "1.15rem", margin: 0, color: "var(--color-text, #e5e7eb)" }}>
            Sign in to OpsMitra
          </h1>
          <p style={{ fontSize: "0.78rem", margin: "0.5rem 0 0", color: "var(--color-muted, #9ca3af)" }}>
            AI Incident Control Plane
          </p>
        </div>

        <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: "0.85rem" }}>
          <label style={{ display: "flex", flexDirection: "column", gap: "0.35rem", fontSize: "0.78rem" }}>
            Username
            <input
              type="text"
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              autoComplete="username"
              autoFocus
              required
              style={{
                padding: "0.55rem 0.7rem",
                background: "var(--color-bg, #0b1120)",
                border: "1px solid var(--color-border, #1f2937)",
                borderRadius: "0.35rem",
                color: "var(--color-text, #e5e7eb)",
                fontSize: "0.88rem",
              }}
            />
          </label>

          <label style={{ display: "flex", flexDirection: "column", gap: "0.35rem", fontSize: "0.78rem" }}>
            Password
            <input
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              autoComplete="current-password"
              required
              style={{
                padding: "0.55rem 0.7rem",
                background: "var(--color-bg, #0b1120)",
                border: "1px solid var(--color-border, #1f2937)",
                borderRadius: "0.35rem",
                color: "var(--color-text, #e5e7eb)",
                fontSize: "0.88rem",
              }}
            />
          </label>

          {error ? (
            <div
              style={{
                fontSize: "0.78rem",
                color: "var(--color-status-down, #ef4444)",
                padding: "0.5rem 0.7rem",
                background: "rgba(239,68,68,0.08)",
                border: "1px solid rgba(239,68,68,0.25)",
                borderRadius: "0.35rem",
              }}
            >
              {error}
            </div>
          ) : null}

          <button
            type="submit"
            disabled={submitting || !username.trim() || !password}
            style={{
              padding: "0.6rem 0.8rem",
              background: "var(--color-accent, #2563eb)",
              color: "#fff",
              border: "none",
              borderRadius: "0.35rem",
              fontSize: "0.85rem",
              fontWeight: 600,
              cursor: submitting ? "wait" : "pointer",
              opacity: submitting || !username.trim() || !password ? 0.6 : 1,
              marginTop: "0.25rem",
            }}
          >
            {submitting ? "Signing in..." : "Sign in"}
          </button>
        </form>

        <p style={{ fontSize: "0.7rem", textAlign: "center", marginTop: "1.25rem", color: "var(--color-muted, #6b7280)" }}>
          Need an account? Ask your administrator.
        </p>
      </div>
    </div>
  );
}
