import { useState, useEffect } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuthStore } from "@/lib/store";
import { api } from "@/lib/api";
import { IconLogIn } from "@/lib/icons";
import { toast } from "@/lib/store";
import { AuthShell } from "@/components/auth-shell";

export function LoginPage() {
  const navigate = useNavigate();
  const { user, setUser, setToken } = useAuthStore();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLocalLoading] = useState(false);
  const [error, setError] = useState("");

  // Send an already-signed-in visitor to their landing page. This must only
  // fire when a session exists: redirecting while signed out bounces between
  // "/" (which redirects here) and "/login" forever.
  useEffect(() => {
    if (!user) return;
    const landing = (user.preferences?.landing_page as string | undefined) || "/dashboard";
    navigate(landing, { replace: true });
  }, [user, navigate]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    if (!email || !password) {
      setError("Please enter email and password.");
      return;
    }
    setLocalLoading(true);
    try {
      const data = await api.post<{ user_id: number; email: string; access_token: string }>("/auth/login", { email, password });
      setUser({ id: data.user_id, email: data.email, username: data.email.split("@")[0], full_name: data.email.split("@")[0], is_active: true, is_superuser: false, preferences: {} });
      setToken(data.access_token);
      toast("Signed in successfully", "success");
      navigate("/");
    } catch (err: any) {
      setError(err?.data?.detail || err?.message || "Login failed");
    } finally {
      setLocalLoading(false);
    }
  };

  return (
    <AuthShell title="Welcome back" subtitle="Sign in to your workspace">
      <form onSubmit={handleSubmit} className="flex flex-col gap-4">
        {error && (
          <div className="flex items-center gap-2 rounded-lg bg-[var(--vbase-red)]/5 border border-[var(--vbase-red)]/20 p-3 text-sm text-[var(--vbase-red)]">
            <svg className="flex-shrink-0 h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="10" /><path d="m15 9-6 6M9 9l6 6" /></svg>
            {error}
          </div>
        )}
        <div className="flex flex-col gap-1.5">
          <label htmlFor="login-email" className="text-sm font-medium text-[var(--vbase-slate700)]">Email address</label>
          <input
            id="login-email"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@company.com"
            autoComplete="email"
            className="vbase-input"
            required
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <label htmlFor="login-password" className="text-sm font-medium text-[var(--vbase-slate700)]">Password</label>
          <input
            id="login-password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="Your password"
            autoComplete="current-password"
            className="vbase-input"
            required
          />
        </div>
        <button type="submit" disabled={loading} data-loading={loading} className="vbase-btn-primary vbase-btn-lg mt-1 w-full">
          {loading ? (
            <svg className="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 12a9 9 0 1 1-6.219-8.56" /></svg>
          ) : (
            <>
              <IconLogIn className="h-4 w-4" />
              <span>Sign in</span>
            </>
          )}
        </button>
      </form>

      <p className="mt-6 text-center text-sm text-[var(--vbase-slate500)]">
        No account?{" "}
        <Link to="/signup" className="font-medium text-[var(--vbase-indigo)] hover:underline">Create one</Link>
      </p>
    </AuthShell>
  );
}
