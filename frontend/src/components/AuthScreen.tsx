import { FormEvent, useState } from "react";
import { useAuth } from "../hooks/useAuth";
import type { AuthChallenge } from "../types";

interface AuthScreenProps {
  challenge: AuthChallenge;
}

export function AuthScreen({ challenge }: AuthScreenProps) {
  const { login, setNewPassword, isLoading } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [newPassword, setNewPasswordValue] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const handleSignIn = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login(email, password);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sign in failed");
    } finally {
      setSubmitting(false);
    }
  };

  const handleNewPassword = async (event: FormEvent) => {
    event.preventDefault();
    if (newPassword !== confirmPassword) {
      setError("Passwords do not match");
      return;
    }
    if (newPassword.length < 8) {
      setError("Password must be at least 8 characters");
      return;
    }

    setError(null);
    setSubmitting(true);
    try {
      await setNewPassword(newPassword);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to set new password");
    } finally {
      setSubmitting(false);
    }
  };

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="h-6 w-6 animate-spin rounded-full border-2 border-cursor-border border-t-cursor-accent" />
      </div>
    );
  }

  return (
    <div className="flex h-full items-center justify-center px-4">
      <div className="w-full max-w-sm rounded-lg border border-cursor-border bg-cursor-sidebar p-6 shadow-xl">
        <div className="mb-6 text-center">
          <h1 className="text-lg font-semibold text-cursor-text">Spend Analytics Agent</h1>
          <p className="mt-1 text-sm text-cursor-subtle">
            {challenge ? "Set a new password to continue" : "Sign in with your account"}
          </p>
        </div>

        {challenge === "FORCE_CHANGE_PASSWORD" ? (
          <form onSubmit={handleNewPassword} className="space-y-4">
            <div>
              <label htmlFor="new-password" className="mb-1 block text-xs text-cursor-subtle">
                New password
              </label>
              <input
                id="new-password"
                type="password"
                autoComplete="new-password"
                value={newPassword}
                onChange={(e) => setNewPasswordValue(e.target.value)}
                className="w-full rounded-md border border-cursor-border bg-cursor-bg px-3 py-2 text-sm text-cursor-text outline-none focus:border-cursor-accent"
                required
              />
            </div>
            <div>
              <label htmlFor="confirm-password" className="mb-1 block text-xs text-cursor-subtle">
                Confirm password
              </label>
              <input
                id="confirm-password"
                type="password"
                autoComplete="new-password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                className="w-full rounded-md border border-cursor-border bg-cursor-bg px-3 py-2 text-sm text-cursor-text outline-none focus:border-cursor-accent"
                required
              />
            </div>
            {error && <p className="text-xs text-red-400">{error}</p>}
            <button
              type="submit"
              disabled={submitting}
              className="w-full rounded-md bg-cursor-accent py-2 text-sm font-medium text-white transition hover:bg-cursor-accent-hover disabled:opacity-50"
            >
              {submitting ? "Updating…" : "Set password"}
            </button>
          </form>
        ) : (
          <form onSubmit={handleSignIn} className="space-y-4">
            <div>
              <label htmlFor="email" className="mb-1 block text-xs text-cursor-subtle">
                Email
              </label>
              <input
                id="email"
                type="email"
                autoComplete="username"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full rounded-md border border-cursor-border bg-cursor-bg px-3 py-2 text-sm text-cursor-text outline-none focus:border-cursor-accent"
                required
              />
            </div>
            <div>
              <label htmlFor="password" className="mb-1 block text-xs text-cursor-subtle">
                Password
              </label>
              <input
                id="password"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full rounded-md border border-cursor-border bg-cursor-bg px-3 py-2 text-sm text-cursor-text outline-none focus:border-cursor-accent"
                required
              />
            </div>
            {error && <p className="text-xs text-red-400">{error}</p>}
            <button
              type="submit"
              disabled={submitting}
              className="w-full rounded-md bg-cursor-accent py-2 text-sm font-medium text-white transition hover:bg-cursor-accent-hover disabled:opacity-50"
            >
              {submitting ? "Signing in…" : "Sign in"}
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
