import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuthStore } from "@/lib/store";
import { api } from "@/lib/api";
import { IconUserPlus } from "@/lib/icons";
import { toast } from "@/lib/store";

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
    <div className="flex min-h-screen items-center justify-center bg-[var(--vbase-bg)] px-4">
      <div className="w-full max-w-[420px]">
        <div className="flex flex-col gap-8 rounded-xl border border-[var(--vbase-border)] bg-[var(--vbase-bg)] p-8 shadow-lg">
          <div className="flex flex-col items-center gap-3 text-center">
            <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-[var(--vbase-indigo)] text-white shadow-sm">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M4 4h6v10H4z" />
                <path d="M14 4h6v6h-6z" />
                <path d="M14 12h6v2h-6z" />
              </svg>
            </div>
            <h1 className="text-xl font-semibold text-[var(--vbase-slate900)]">V-Base</h1>
            <p className="text-sm font-medium text-[var(--vbase-indigo)]">
              Your Business Data. One Powerful Base.
            </p>
            <p className="text-sm text-[var(--vbase-slate500)]">Create your account</p>
          </div>

          <form onSubmit={handleSubmit} className="flex flex-col gap-4">
            {error && (
              <div className="flex items-center gap-2 rounded-lg bg-[var(--vbase-red)]/5 border border-[var(--vbase-red)]/20 p-3 text-sm text-[var(--vbase-red)]">
                <svg className="flex-shrink-0 h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="10" /><path d="m15 9-6 6M9 9l6 6" /></svg>
                {error}
              </div>
            )}
            <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="Email address" className="vbase-input" required />
            <input type="text" value={username} onChange={(e) => setUsername(e.target.value)} placeholder="Username" className="vbase-input" required />
            <input type="text" value={fullName} onChange={(e) => setFullName(e.target.value)} placeholder="Full name (optional)" className="vbase-input" />
            <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="Password (min 8 characters)" className="vbase-input" required />
            <button type="submit" disabled={loading} className="vbase-btn-primary flex items-center justify-center gap-2">
              {loading ? <svg className="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 12a9 9 0 1 1-6.219-8.56" /></svg> : <><IconUserPlus className="h-4 w-4" /><span>Create account</span></>}
            </button>
          </form>

          <div className="flex items-center justify-center gap-4 text-sm text-[var(--vbase-slate500)]">
            <span>Already have an account?</span>
            <Link to="/login" className="text-[var(--vbase-indigo)] hover:underline font-medium">Sign in</Link>
          </div>
        </div>
      </div>
    </div>
  );
}
