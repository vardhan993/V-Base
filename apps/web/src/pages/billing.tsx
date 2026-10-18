import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { toast } from "@/lib/store";
import { useAuthStore } from "@/lib/store";

interface Plan {
  key: string;
  name: string;
  price_inr: number;
  period: string;
  record_cap: number | null;
  tagline: string;
  features: string[];
}

interface MeUpdate {
  plan?: string;
}

const fmtINR = (n: number) =>
  "₹" + n.toLocaleString("en-IN");

export function BillingPage() {
  const user = useAuthStore((s) => s.user);
  const setUser = useAuthStore((s) => s.setUser);
  const [plans, setPlans] = useState<Plan[]>([]);
  const [current, setCurrent] = useState<string>("starter");
  const [isAdmin, setIsAdmin] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const data = await api.get<{ plans: Plan[]; current_plan_key: string; is_admin_plan: boolean }>(
        "/billing/plans"
      );
      setPlans(data.plans);
      setCurrent(data.current_plan_key);
      setIsAdmin(data.is_admin_plan);
    } catch (e: any) {
      toast(e?.message || "Could not load plans", "error");
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const choose = async (plan: Plan) => {
    if (isAdmin) {
      toast("Admin accounts are always unlimited and free — nothing to change", "info");
      return;
    }
    setBusy(plan.key);
    try {
      await api.post("/billing/plan", { plan: plan.key });
      const me: MeUpdate = { plan: plan.key };
      if (user) setUser({ ...user, ...me });
      await load();
      toast(`Switched to ${plan.name} (${fmtINR(plan.price_inr)}/mo)`, "success");
    } catch (e: any) {
      toast(e?.data?.detail || e?.message || "Could not change plan", "error");
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-xl font-semibold text-[var(--vbase-slate800)]">Plan & billing</h1>
        <p className="mt-1 text-sm text-[var(--vbase-slate500)]">
          Every plan has the full CRM — plans differ only by record capacity. Prices in Indian Rupees.
        </p>
      </div>

      {isAdmin && (
        <div className="vbase-card border-[var(--vbase-green)]/30 bg-[var(--vbase-green)]/5 p-5">
          <p className="text-sm font-medium text-[var(--vbase-green)]">
            Admin plan — unlimited records, every feature, free forever. This account is the product
            owner's and cannot be downgraded.
          </p>
        </div>
      )}

      <div className="grid gap-4 md:grid-cols-3">
        {plans.map((p) => {
          const isActive = p.key === current;
          return (
            <div
              key={p.key}
              className={`vbase-card flex flex-col p-5 ${isActive ? "border-2 border-[var(--vbase-indigo)]" : ""}`}
            >
              <div className="flex items-baseline justify-between">
                <h3 className="font-semibold text-[var(--vbase-slate800)]">{p.name}</h3>
                <span className="text-[var(--vbase-slate500)]">
                  {p.price_inr === 0 ? "Free" : `${fmtINR(p.price_inr)}/${p.period}`}
                </span>
              </div>
              <p className="mt-1 text-xs text-[var(--vbase-slate500)]">{p.tagline}</p>
              <p className="mt-3 text-sm font-medium text-[var(--vbase-slate700)]">
                {p.record_cap ? `${p.record_cap.toLocaleString("en-IN")} records` : "Unlimited records"}
              </p>
              <ul className="mt-3 flex-1 space-y-1.5 text-sm text-[var(--vbase-slate600)]">
                {p.features.map((f) => (
                  <li key={f}>· {f}</li>
                ))}
              </ul>
              <button
                onClick={() => choose(p)}
                disabled={isActive || busy === p.key || (isAdmin && p.key !== "admin")}
                className={`mt-4 ${
                  isActive ? "vbase-btn-ghost" : "vbase-btn-primary"
                }`}
              >
                {isActive ? "Current plan" : isAdmin ? "Not available" : "Choose plan"}
              </button>
            </div>
          );
        })}
      </div>
    </div>
  );
}
