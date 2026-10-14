import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuthStore } from "@/lib/store";
import { api } from "@/lib/api";
import { IconUserPlus } from "@/lib/icons";
import { toast } from "@/lib/store";
import { AuthShell } from "@/components/auth-shell";

export function SignupPage() {
  const navigate = useNavigate();
  const { setUser, setToken } = useAuthStore();
  const [email, setEmail] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [loading, setLocalLoading] = useState(false);
  const [error, setError] = useState("");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    if (!email || !username || !password) {
      setError("Please fill in all required fields.");
      return;
    }
    if (password.length < 8) {
      setError("Password must be at least 8 characters.");
      return;
    }
    if (username.length < 3) {
      setError("Username must be at least 3 characters.");
      return;
    }
    setLocalLoading(true);
    try {
      const data = await api.post<{ user_id: number; email: string; access_token: string }>("/auth/signup", { email, username, password, full_name: fullName || undefined });
      setUser({ id: data.user_id, email: data.email, username: data.email.split("@")[0], full_name: data.email.split("@")[0], is_active: true, is_superuser: false, preferences: {} });
      setToken(data.access_token);
      toast("Account created successfully", "success");
      navigate("/");
    } catch (err: any) {
      setError(err?.data?.detail || err?.message || "Signup failed");
    } finally {
      setLocalLoading(false);
    }
  };

  return (
    <AuthShell title="Create your account" subtitle="Start building your business base">
      <form onSubmit={handleSubmit} className="flex flex-col gap-4">
        {error && (
          <div className="flex items-center gap-2 rounded-lg bg-[var(--vbase-red)]/5 border border-[var(--vbase-red)]/20 p-3 text-sm text-[var(--vbase-red)]">
            <svg className="flex-shrink-0 h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="10" /><path d="m15 9-6 6M9 9l6 6" /></svg>
            {error}
          </div>
        )}
        <div className="flex flex-col gap-1.5">
          <label htmlFor="signup-email" className="text-sm font-medium text-[var(--vbase-slate700)]">Email address</label>
          <input
            id="signup-email"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@company.com"
            autoComplete="email"
            className="vbase-input"
            required
          />
        </div>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div className="flex flex-col gap-1.5">
            <label htmlFor="signup-username" className="text-sm font-medium text-[var(--vbase-slate700)]">Username</label>
            <input
              id="signup-username"
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="jane_d"
              autoComplete="username"
              minLength={3}
              className="vbase-input"
              required
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <label htmlFor="signup-fullname" className="text-sm font-medium text-[var(--vbase-slate700)]">
              Full name <span className="font-normal text-[var(--vbase-slate400)]">(optional)</span>
            </label>
            <input
              id="signup-fullname"
              type="text"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              placeholder="Jane Doe"
              autoComplete="name"
              className="vbase-input"
            />
          </div>
        </div>
        <div className="flex flex-col gap-1.5">
          <label htmlFor="signup-password" className="text-sm font-medium text-[var(--vbase-slate700)]">Password</label>
          <input
            id="signup-password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="At least 8 characters"
            autoComplete="new-password"
            minLength={8}
            className="vbase-input"
            required
          />
          <p className="text-xs text-[var(--vbase-slate500)]">Minimum 8 characters. Hashed with Argon2 before it is ever stored.</p>
        </div>
        <button type="submit" disabled={loading} data-loading={loading} className="vbase-btn-primary vbase-btn-lg mt-1 w-full">
          {loading ? (
            <svg className="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 12a9 9 0 1 1-6.219-8.56" /></svg>
          ) : (
            <>
              <IconUserPlus className="h-4 w-4" />
              <span>Create account</span>
            </>
          )}
        </button>
      </form>

      <p className="mt-6 text-center text-sm text-[var(--vbase-slate500)]">
        Already have an account?{" "}
        <Link to="/login" className="font-medium text-[var(--vbase-indigo)] hover:underline">Sign in</Link>
      </p>
    </AuthShell>
  );
}
