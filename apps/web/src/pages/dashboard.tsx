import { useEffect, useState } from "react";
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, AreaChart, Area } from "recharts";
import { useAuthStore } from "@/lib/store";
import { api } from "@/lib/api";
import { IconBuilding2, IconUsers, IconMail, IconPhone, IconLink, IconCheckCircle2, IconAlertTriangle, IconActivity, IconSparkles } from "@/lib/icons";

export function DashboardPage() {
  const { user } = useAuthStore();
  const [metrics, setMetrics] = useState<any>(null);
  const [growth, setGrowth] = useState<any>(null);
  const [byIndustry, setByIndustry] = useState<any>(null);
  const [byDepartment, setByDepartment] = useState<any>(null);
  const [byLocation, setByLocation] = useState<any>(null);
  const [coverage, setCoverage] = useState<any>(null);
  const [activity, setActivity] = useState<any>(null);
  const [, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const [m, g, ind, dep, loc, cov, act] = await Promise.all([
          api.get<any>("/analytics/overview"),
          api.get<any>("/analytics/growth?days=90"),
          api.get<any>("/analytics/companies-by-industry"),
          api.get<any>("/analytics/contacts-by-department"),
          api.get<any>("/analytics/contacts-by-city"),
          api.get<any>("/analytics/email-coverage"),
          api.get<any>("/analytics/activity-narrative"),
        ]);
        if (!cancelled) {
          setMetrics(m);
          setGrowth(g);
          setByIndustry(ind);
          setByDepartment(dep);
          setByLocation(loc);
          setCoverage(cov);
          setActivity(act);
        }
      } catch (e) {
        console.error(e);
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    load();
    return () => { cancelled = true; };
  }, []);

  const empty = !metrics || (!metrics.companies && !metrics.contacts);

  return (
    <div className="animation-fade-in">
      <div className="mb-6 flex flex-wrap items-baseline gap-3">
        <h1 className="text-2xl font-semibold text-[var(--vbase-slate900)]">Overview</h1>
        <span className="text-sm text-[var(--vbase-slate500)]">{user?.email}</span>
      </div>

      {empty ? (
        <OnboardingCard />
      ) : (
        <>
          <MetricsGrid metrics={metrics} />
          <div className="grid gap-6 md:grid-cols-2">
            <GrowthCard growth={growth} />
            <CoverageCard coverage={coverage} />
          </div>
          <div className="grid gap-6 md:grid-cols-3">
            <IndustryCard data={byIndustry} />
            <DepartmentCard data={byDepartment} />
            <LocationCard data={byLocation} />
          </div>
          <RecentActivityCard data={activity} />
        </>
      )}
    </div>
  );
}

function MetricsGrid({ metrics }: { metrics: any }) {
  const items = [
    { label: "Companies", value: metrics.companies, icon: IconBuilding2, color: "var(--vbase-indigo)" },
    { label: "Contacts", value: metrics.contacts, icon: IconUsers, color: "var(--vbase-cyan)" },
    { label: "Emails available", value: metrics.emails_available, icon: IconMail, color: "var(--vbase-green)" },
    { label: "Phones available", value: metrics.phones_available, icon: IconPhone, color: "var(--vbase-amber)" },
    { label: "LinkedIn profiles", value: metrics.linkedin_profiles, icon: IconLink, color: "var(--vbase-purple)" },
    { label: "Verified emails", value: metrics.verified_emails, icon: IconCheckCircle2, color: "var(--vbase-green)" },
    { label: "Records needing review", value: metrics.records_needing_review, icon: IconAlertTriangle, color: "var(--vbase-red)" },
  ];

  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
      {items.map((item) => (
        <div key={item.label} className="vbase-card p-4">
          <div className="flex items-start justify-between">
            <div>
              <p className="text-xs font-medium text-[var(--vbase-slate500)] uppercase tracking-wider">{item.label}</p>
              <p className="mt-1 text-2xl font-semibold text-[var(--vbase-slate900)]">{item.value ?? 0}</p>
            </div>
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-[var(--vbase-bg-alt)] text-[13px]">
              <item.icon className="h-5 w-5" style={{ color: item.color }} />
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

function GrowthCard({ growth }: { growth: any }) {
  const data = growth?.company_series?.slice(-60) || [];
  if (!data.length) {
    return (
      <div className="vbase-card p-5">
        <h3 className="mb-1 text-base font-semibold text-[var(--vbase-slate800)]">Database growth</h3>
        <p className="text-sm text-[var(--vbase-slate500)]">No growth data yet.</p>
      </div>
    );
  }
  return (
    <div className="vbase-card p-5">
      <h3 className="mb-1 text-base font-semibold text-[var(--vbase-slate800)]">Database growth</h3>
      <p className="text-sm text-[var(--vbase-slate500)]">Companies and contacts added over time</p>
      <div className="mt-3 h-40">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={data}>
            <defs>
              <linearGradient id="colorCompanies" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="var(--vbase-indigo)" stopOpacity={0.2} />
                <stop offset="95%" stopColor="var(--vbase-indigo)" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--vbase-border)" />
            <XAxis dataKey="date" stroke="var(--vbase-slate400)" tick={{ fontSize: 10 }} tickLine={false} axisLine={false} />
            <YAxis stroke="var(--vbase-slate400)" tick={{ fontSize: 10 }} tickLine={false} axisLine={false} width={32} />
            <Tooltip contentStyle={{ borderRadius: 8, border: "1px solid var(--vbase-border)", background: "var(--vbase-bg)" }} />
            <Area type="monotone" dataKey="companies" stroke="var(--vbase-indigo)" strokeWidth={2} fillOpacity={1} fill="url(#colorCompanies)" name="companies" />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

function CoverageCard({ coverage }: { coverage: any }) {
  const pct = coverage?.coverage_pct ?? 0;
  return (
    <div className="vbase-card p-5">
      <h3 className="mb-1 text-base font-semibold text-[var(--vbase-slate800)]">Email coverage</h3>
      <p className="text-sm text-[var(--vbase-slate500)]">Contacts with an email address</p>
      <div className="mt-4 grid grid-cols-2 gap-4">
        <div className="h-2 w-full rounded-full bg-[var(--vbase-slate200)]">
          <div className="h-full rounded-full bg-[var(--vbase-indigo)]" style={{ width: `${pct}%` }} />
        </div>
        <div className="text-sm">
          <span className="font-semibold text-[var(--vbase-slate800)]">{pct}%</span>
          <span className="text-[var(--vbase-slate500)]"> covered</span>
        </div>
      </div>
      <div className="mt-4 grid grid-cols-3 gap-3 text-center text-sm">
        <div><p className="font-semibold text-[var(--vbase-slate800)]">{coverage?.with_email ?? 0}</p><p className="text-[var(--vbase-slate500)]">With email</p></div>
        <div><p className="font-semibold text-[var(--vbase-slate800)]">{coverage?.verified ?? 0}</p><p className="text-[var(--vbase-slate500)]">Verified</p></div>
        <div><p className="font-semibold text-[var(--vbase-slate800)]">{coverage?.missing ?? 0}</p><p className="text-[var(--vbase-slate500)]">Missing</p></div>
      </div>
    </div>
  );
}

function IndustryCard({ data }: { data: any }) {
  const chartData = (data || []).slice(0, 6).map((d: any, i: number) => ({ name: d.industry || `Industry ${i + 1}`, count: d.count }));
  if (!chartData.length) {
    return (
      <div className="vbase-card p-5">
        <h3 className="mb-1 text-base font-semibold text-[var(--vbase-slate800)]">Companies by industry</h3>
        <p className="text-sm text-[var(--vbase-slate500)]">No data yet.</p>
      </div>
    );
  }
  return (
    <div className="vbase-card p-5">
      <h3 className="mb-1 text-base font-semibold text-[var(--vbase-slate800)]">Companies by industry</h3>
      <div className="mt-3 h-44">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={chartData} layout="vertical">
            <CartesianGrid strokeDasharray="3 3" stroke="var(--vbase-border)" />
            <XAxis type="number" stroke="var(--vbase-slate400)" tick={{ fontSize: 10 }} />
            <YAxis dataKey="name" type="category" stroke="var(--vbase-slate400)" tick={{ fontSize: 11 }} width={110} />
            <Tooltip contentStyle={{ borderRadius: 8, border: "1px solid var(--vbase-border)", background: "var(--vbase-bg)" }} />
            <Bar dataKey="count" fill="var(--vbase-indigo)" radius={[0, 4, 4, 0]} name="companies" />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

function DepartmentCard({ data }: { data: any }) {
  const chartData = (data || []).slice(0, 6).map((d: any, i: number) => ({ name: d.department || `Dept ${i + 1}`, count: d.count }));
  if (!chartData.length) {
    return (
      <div className="vbase-card p-5">
        <h3 className="mb-1 text-base font-semibold text-[var(--vbase-slate800)]">Contacts by department</h3>
        <p className="text-sm text-[var(--vbase-slate500)]">No data yet.</p>
      </div>
    );
  }
  return (
    <div className="vbase-card p-5">
      <h3 className="mb-1 text-base font-semibold text-[var(--vbase-slate800)]">Contacts by department</h3>
      <div className="mt-3 h-44">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={chartData} layout="vertical">
            <CartesianGrid strokeDasharray="3 3" stroke="var(--vbase-border)" />
            <XAxis type="number" stroke="var(--vbase-slate400)" tick={{ fontSize: 10 }} />
            <YAxis dataKey="name" type="category" stroke="var(--vbase-slate400)" tick={{ fontSize: 11 }} width={110} />
            <Tooltip contentStyle={{ borderRadius: 8, border: "1px solid var(--vbase-border)", background: "var(--vbase-bg)" }} />
            <Bar dataKey="count" fill="var(--vbase-cyan)" radius={[0, 4, 4, 0]} name="contacts" />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

function LocationCard({ data }: { data: any }) {
  const chartData = (data || []).slice(0, 6).map((d: any, i: number) => ({ name: d.city || `City ${i + 1}`, count: d.count }));
  if (!chartData.length) {
    return (
      <div className="vbase-card p-5">
        <h3 className="mb-1 text-base font-semibold text-[var(--vbase-slate800)]">Contacts by location</h3>
        <p className="text-sm text-[var(--vbase-slate500)]">No data yet.</p>
      </div>
    );
  }
  return (
    <div className="vbase-card p-5">
      <h3 className="mb-1 text-base font-semibold text-[var(--vbase-slate800)]">Contacts by location</h3>
      <div className="mt-3 h-44">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--vbase-border)" />
            <XAxis dataKey="name" stroke="var(--vbase-slate400)" tick={{ fontSize: 10 }} />
            <YAxis stroke="var(--vbase-slate400)" tick={{ fontSize: 10 }} />
            <Tooltip contentStyle={{ borderRadius: 8, border: "1px solid var(--vbase-border)", background: "var(--vbase-bg)" }} />
            <Bar dataKey="count" fill="var(--vbase-amber)" radius={[4, 4, 0, 0]} name="contacts" />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

function RecentActivityCard({ data }: { data: any }) {
  const items = (data || []).slice(0, 8);
  return (
    <div className="vbase-card p-5">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-base font-semibold text-[var(--vbase-slate800)]">Recent activity</h3>
        <span className="text-xs text-[var(--vbase-slate500)]">Last 7 days</span>
      </div>
      {!items.length ? (
        <p className="text-sm text-[var(--vbase-slate500)]">No recent activity.</p>
      ) : (
        <ul className="flex flex-col gap-2">
          {items.map((item: any) => (
            <li key={item.id} className="flex items-start gap-3 rounded-md px-3 py-2">
              <div className="mt-0.5 flex h-6 w-6 items-center justify-center rounded-full bg-[var(--vbase-indigo)]/10 text-[var(--vbase-indigo)]">
                <IconActivity className="h-3.5 w-3.5" />
              </div>
              <div className="min-w-0 flex-1">
                <p className="text-sm text-[var(--vbase-slate800)]">{item.description || item.action}</p>
                <p className="text-xs text-[var(--vbase-slate500)]">{item.entity_type} · {item.entity_id}</p>
              </div>
              <span className="text-xs text-[var(--vbase-slate400)]">{item.created_at ? new Date(item.created_at).toLocaleString() : ""}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function OnboardingCard() {
  return (
    <div className="vbase-card flex flex-col items-center justify-center gap-5 p-12 text-center">
      <div className="flex h-16 w-16 items-center justify-center rounded-full bg-[var(--vbase-indigo)]/10 text-[var(--vbase-indigo)]">
        <IconSparkles className="h-8 w-8" />
      </div>
      <div>
        <h2 className="text-lg font-semibold text-[var(--vbase-slate800)]">Import your first spreadsheet</h2>
        <p className="mt-1 text-sm text-[var(--vbase-slate500)] max-w-sm">
          Add a CSV or Excel file with company or contact data to start building your B2B database.
        </p>
      </div>
      <a href="#/import" className="vbase-btn-primary">
        <IconBuilding2 className="mr-2 h-4 w-4" />
        Open Import Center
      </a>
    </div>
  );
}
