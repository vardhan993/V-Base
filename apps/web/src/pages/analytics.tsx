import { useEffect, useState } from "react";
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, PieChart, Pie, Cell, AreaChart, Area } from "recharts";
import { IconMail, IconPhone, IconLink } from "@/lib/icons";
import { api } from "@/lib/api";


export function AnalyticsPage() {
  const [growth, setGrowth] = useState<any>(null);
  const [byIndustry, setByIndustry] = useState<any>(null);
  const [bySize, setBySize] = useState<any>(null);
  const [byDept, setByDept] = useState<any>(null);
  const [bySeniority, setBySeniority] = useState<any>(null);
  const [, setByCountry] = useState<any>(null);
  const [byCity, setByCity] = useState<any>(null);
  const [emailCov, setEmailCov] = useState<any>(null);
  const [phoneCov, setPhoneCov] = useState<any>(null);
  const [linkedinCov, setLinkedinCov] = useState<any>(null);
  const [verification, setVerification] = useState<any>(null);
  const [, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const [
          g, ind, sz, dep, sen, country, city, ec, pc, lc, ver
        ] = await Promise.all([
          api.get<any>("/analytics/growth?days=90"),
          api.get<any>("/analytics/companies-by-industry"),
          api.get<any>("/analytics/companies-by-size"),
          api.get<any>("/analytics/contacts-by-department"),
          api.get<any>("/analytics/contacts-by-seniority"),
          api.get<any>("/analytics/contacts-by-country"),
          api.get<any>("/analytics/contacts-by-city"),
          api.get<any>("/analytics/email-coverage"),
          api.get<any>("/analytics/phone-coverage"),
          api.get<any>("/analytics/linkedin-coverage"),
          api.get<any>("/analytics/verification-status"),
        ]);
        if (!cancelled) {
          setGrowth(g);
          setByIndustry(ind);
          setBySize(sz);
          setByDept(dep);
          setBySeniority(sen);
          setByCountry(country);
          setByCity(city);
          setEmailCov(ec);
          setPhoneCov(pc);
          setLinkedinCov(lc);
          setVerification(ver);
        }
      } catch (e) { console.error(e); } finally { if (!cancelled) setLoading(false); }
    };
    load();
    return () => { cancelled = true; };
  }, []);

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-xl font-semibold text-[var(--vbase-slate900)]">Analytics</h1>
      <p className="text-sm text-[var(--vbase-slate500)]">All metrics are computed from the current database.</p>

      <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-4">
        <CoverageMini label="Email coverage" value={emailCov?.coverage_pct ?? 0} color="var(--vbase-indigo)" icon={<IconMail className="h-4 w-4" />} />
        <CoverageMini label="Phone coverage" value={phoneCov?.coverage_pct ?? 0} color="var(--vbase-cyan)" icon={<IconPhone className="h-4 w-4" />} />
        <CoverageMini label="LinkedIn coverage" value={linkedinCov?.coverage_pct ?? 0} color="var(--vbase-amber)" icon={<IconLink className="h-4 w-4" />} />
        <CoverageMini label="Verified contacts" value={verification ? Math.round((verification.verified / Math.max(1, verification.total)) * 100) : 0} color="var(--vbase-green)" icon={<IconLink className="h-4 w-4" />} />
      </div>

      <div className="grid gap-6 md:grid-cols-2">
        <ChartPanel title="Database growth" subtitle="Companies and contacts added over time">
          <div className="h-[260px]">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={(growth?.company_series || []).slice(-60)}>
                <defs>
                  <linearGradient id="growCompany" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="var(--vbase-indigo)" stopOpacity={0.2} />
                    <stop offset="95%" stopColor="var(--vbase-indigo)" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--vbase-border)" />
                <XAxis dataKey="date" stroke="var(--vbase-slate400)" tick={{ fontSize: 10 }} />
                <YAxis stroke="var(--vbase-slate400)" tick={{ fontSize: 10 }} width={32} />
                <Tooltip contentStyle={{ borderRadius: 8, border: "1px solid var(--vbase-border)", background: "var(--vbase-bg)" }} />
                <Area type="monotone" dataKey="companies" stroke="var(--vbase-indigo)" strokeWidth={2} fill="url(#growCompany)" name="companies" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </ChartPanel>

        <ChartPanel title="Contacts by seniority" subtitle="Distribution by seniority level">
          <div className="h-[260px]">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={(bySeniority || []).slice(0, 8)}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--vbase-border)" />
                <XAxis dataKey="seniority" stroke="var(--vbase-slate400)" tick={{ fontSize: 10 }} />
                <YAxis stroke="var(--vbase-slate400)" tick={{ fontSize: 10 }} width={32} />
                <Tooltip contentStyle={{ borderRadius: 8, border: "1px solid var(--vbase-border)", background: "var(--vbase-bg)" }} />
                <Bar dataKey="count" fill="var(--vbase-cyan)" radius={[4, 4, 0, 0]} name="contacts" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </ChartPanel>

        <ChartPanel title="Companies by industry" subtitle="Top industries">
          <div className="h-[260px]">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={(byIndustry || []).slice(0, 8)} layout="vertical">
                <CartesianGrid strokeDasharray="3 3" stroke="var(--vbase-border)" />
                <XAxis type="number" stroke="var(--vbase-slate400)" tick={{ fontSize: 10 }} />
                <YAxis dataKey="industry" type="category" stroke="var(--vbase-slate400)" tick={{ fontSize: 11 }} width={100} />
                <Tooltip contentStyle={{ borderRadius: 8, border: "1px solid var(--vbase-border)", background: "var(--vbase-bg)" }} />
                <Bar dataKey="count" fill="var(--vbase-indigo)" radius={[0, 4, 4, 0]} name="companies" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </ChartPanel>

        <ChartPanel title="Contacts by department" subtitle="Top departments">
          <div className="h-[260px]">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={(byDept || []).slice(0, 8)} layout="vertical">
                <CartesianGrid strokeDasharray="3 3" stroke="var(--vbase-border)" />
                <XAxis type="number" stroke="var(--vbase-slate400)" tick={{ fontSize: 10 }} />
                <YAxis dataKey="department" type="category" stroke="var(--vbase-slate400)" tick={{ fontSize: 11 }} width={100} />
                <Tooltip contentStyle={{ borderRadius: 8, border: "1px solid var(--vbase-border)", background: "var(--vbase-bg)" }} />
                <Bar dataKey="count" fill="var(--vbase-cyan)" radius={[0, 4, 4, 0]} name="contacts" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </ChartPanel>

        <ChartPanel title="Contacts by city" subtitle="Top cities">
          <div className="h-[260px]">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={(byCity || []).slice(0, 8)}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--vbase-border)" />
                <XAxis dataKey="city" stroke="var(--vbase-slate400)" tick={{ fontSize: 10 }} />
                <YAxis stroke="var(--vbase-slate400)" tick={{ fontSize: 10 }} width={32} />
                <Tooltip contentStyle={{ borderRadius: 8, border: "1px solid var(--vbase-border)", background: "var(--vbase-bg)" }} />
                <Bar dataKey="count" fill="var(--vbase-amber)" radius={[4, 4, 0, 0]} name="contacts" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </ChartPanel>

        <ChartPanel title="Companies by size" subtitle="Company size distribution">
          <div className="h-[260px]">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={(bySize || []).slice(0, 8)}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--vbase-border)" />
                <XAxis dataKey="size" stroke="var(--vbase-slate400)" tick={{ fontSize: 10 }} />
                <YAxis stroke="var(--vbase-slate400)" tick={{ fontSize: 10 }} width={32} />
                <Tooltip contentStyle={{ borderRadius: 8, border: "1px solid var(--vbase-border)", background: "var(--vbase-bg)" }} />
                <Bar dataKey="count" fill="var(--vbase-green)" radius={[4, 4, 0, 0]} name="companies" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </ChartPanel>
      </div>

      <div className="grid gap-6 md:grid-cols-3">
        <PiePanel data={emailCov} title="Email coverage" value="with_email" total="total_contacts" color="var(--vbase-indigo)" />
        <PiePanel data={phoneCov} title="Phone coverage" value="with_phone" total="total_contacts" color="var(--vbase-cyan)" />
        <PiePanel data={linkedinCov} title="LinkedIn coverage" value="with_linkedin" total="total_contacts" color="var(--vbase-amber)" />
      </div>
    </div>
  );
}

function CoverageMini({ label, value, color, icon }: any) {
  return (
    <div className="vbase-card p-4">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-xs text-[var(--vbase-slate500)] uppercase tracking-wider">{label}</p>
          <div className="mt-1 flex items-baseline gap-1">
            <p className="text-2xl font-semibold text-[var(--vbase-slate900)]">{value}%</p>
          </div>
        </div>
        <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-[var(--vbase-bg-alt)]">
          <span style={{ color }}>{icon}</span>
        </div>
      </div>
      <div className="mt-3 h-1.5 w-full rounded-full bg-[var(--vbase-slate200)]">
        <div className={`h-full rounded-full ${color ? `bg-[${color}]` : "bg-[var(--vbase-indigo)]"}`} style={{ width: `${value}%` }} />
      </div>
    </div>
  );
}

function ChartPanel({ title, subtitle, children }: any) {
  return (
    <div className="vbase-card p-5">
      <div className="mb-3 flex items-center justify-between">
        <div>
          <h3 className="font-semibold text-[var(--vbase-slate800)]">{title}</h3>
          <p className="text-xs text-[var(--vbase-slate500)]">{subtitle}</p>
        </div>
      </div>
      {children}
    </div>
  );
}

function PiePanel({ data, title, value, total, color }: any) {
  const pieData = [
    { name: "covered", value: data?.[value] ?? 0 },
    { name: "missing", value: (data?.[total] ?? 0) - (data?.[value] ?? 0) },
  ];
  const hasData = pieData.some((d) => d.value > 0);
  if (!hasData) {
    return (
      <div className="vbase-card p-5 text-center text-sm text-[var(--vbase-slate500)]">{title} · no data</div>
    );
  }
  return (
    <div className="vbase-card p-5">
      <h3 className="mb-3 font-semibold text-[var(--vbase-slate800)]">{title}</h3>
      <div className="h-[200px]">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie data={pieData} cx="50%" cy="50%" innerRadius={40} outerRadius={70} dataKey="value">
              {pieData.map((entry, i) => (
                <Cell key={i} fill={entry.name === "covered" ? color : "var(--vbase-slate300)"} />
              ))}
            </Pie>
            <Tooltip contentStyle={{ borderRadius: 8, border: "1px solid var(--vbase-border)", background: "var(--vbase-bg)" }} />
          </PieChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
