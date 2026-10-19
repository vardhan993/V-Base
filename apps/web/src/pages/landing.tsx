import { Link } from "react-router-dom";
import { useState } from "react";
import { api } from "@/lib/api";
import {
  IconArrowRight,
  IconBarChart3,
  IconBuilding2,
  IconCheckIcon,
  IconCheckCircle2,
  IconCloudUpload,
  IconFilter,
  IconGauge,
  IconGlobe,
  IconInbox,
  IconLayers,
  IconListChecks,
  IconMailPlus,
  IconMergeIcon,
  IconShieldCheck,
  IconStarIcon,
  IconTagsIcon,
  IconUsers,
  IconWandSparkles,
} from "@/lib/icons";
import { useAuthStore } from "@/lib/store";

// ---------------------------------------------------------------------------
// Landing page — the public marketing surface for V-Base CRM.
//
// Lives outside the auth-guarded app shell (see App.tsx routes): anyone can
// read it signed-out, and a signed-in user gets an "Open app" shortcut that
// jumps straight to /dashboard. It reuses the app's CSS design tokens
// (--vbase-*), so dark mode and theming work without extra code.
//
// HashRouter means plain <a href="#features"> anchors would collide with the
// router's hash. Section links therefore scroll via scrollIntoView instead.
// ---------------------------------------------------------------------------

function Logo() {
  return (
    <div className="flex items-center gap-2.5">
      <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-[var(--vbase-brand-a)] to-[var(--vbase-brand-b)] text-sm font-black text-white">
        V
      </span>
      <span className="text-lg font-bold text-[var(--vbase-slate900)]">
        V-Base<span className="text-[var(--vbase-indigo)]"> CRM</span>
      </span>
    </div>
  );
}

function scrollTo(id: string) {
  document.getElementById(id)?.scrollIntoView({ behavior: "smooth" });
}

function scrollToTop() {
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function SectionHeading({
  eyebrow,
  title,
  body,
}: {
  eyebrow: string;
  title: string;
  body?: string;
}) {
  return (
    <div className="mx-auto max-w-2xl text-center">
      <p className="text-xs font-bold uppercase tracking-[0.2em] text-[var(--vbase-indigo)]">{eyebrow}</p>
      <h2 className="mt-2 text-3xl font-bold text-[var(--vbase-slate900)] sm:text-4xl">{title}</h2>
      {body && <p className="mt-3 text-base leading-relaxed text-[var(--vbase-muted)]">{body}</p>}
    </div>
  );
}

function Navbar({ signedIn }: { signedIn: boolean }) {
  return (
    <header className="sticky top-0 z-40 border-b border-[var(--vbase-border)] bg-[var(--vbase-bg)]/90 backdrop-blur">
      <div className="mx-auto flex h-16 max-w-6xl items-center justify-between gap-4 px-4 sm:px-6">
        <button onClick={scrollToTop} className="focus:outline-none">
          <Logo />
        </button>
        <nav className="hidden items-center gap-7 text-sm font-medium text-[var(--vbase-muted)] md:flex">
          <button onClick={() => scrollTo("features")} className="transition-colors hover:text-[var(--vbase-indigo)]">
            Features
          </button>
          <button onClick={() => scrollTo("testimonials")} className="transition-colors hover:text-[var(--vbase-indigo)]">
            Testimonials
          </button>
          <button onClick={() => scrollTo("pricing")} className="transition-colors hover:text-[var(--vbase-indigo)]">
            Pricing
          </button>
          <button onClick={() => scrollTo("contact")} className="transition-colors hover:text-[var(--vbase-indigo)]">
            Contact
          </button>
        </nav>
        <div className="flex items-center gap-3">
          {signedIn ? (
            <Link
              to="/dashboard"
              className="rounded-lg bg-[var(--vbase-indigo)] px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-[var(--vbase-indigo-hover)]"
            >
              Open app
            </Link>
          ) : (
            <>
              <Link
                to="/login"
                className="rounded-lg px-3 py-2 text-sm font-medium text-[var(--vbase-muted)] transition-colors hover:text-[var(--vbase-slate900)]"
              >
                Log in
              </Link>
              <Link
                to="/signup"
                className="rounded-lg bg-[var(--vbase-indigo)] px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-[var(--vbase-indigo-hover)]"
              >
                Get started
              </Link>
            </>
          )}
        </div>
      </div>
    </header>
  );
}

function Hero({ signedIn }: { signedIn: boolean }) {
  return (
    <section className="relative overflow-hidden px-4 py-20 sm:px-6 sm:py-28">
      <div
        aria-hidden
        className="pointer-events-none absolute inset-x-0 -top-40 mx-auto h-96 max-w-4xl rounded-full bg-gradient-to-r from-[var(--vbase-brand-a)]/15 via-[var(--vbase-brand-via)]/15 to-[var(--vbase-indigo)]/10 blur-3xl"
      />
      <div className="relative mx-auto max-w-4xl text-center">
        <p className="mx-auto w-fit rounded-full border border-[var(--vbase-border)] bg-[var(--vbase-muted-bg)] px-3 py-1 text-xs font-semibold text-[var(--vbase-muted)]">
          The CRM outgrew spreadsheets — not teams
        </p>
        <h1 className="mt-6 text-4xl font-black leading-tight text-[var(--vbase-slate900)] sm:text-6xl">
          All your customers.
          <br />
          <span className="bg-gradient-to-r from-[var(--vbase-brand-a)] to-[var(--vbase-brand-b)] bg-clip-text text-transparent">
            One clean CRM.
          </span>
        </h1>
        <p className="mx-auto mt-5 max-w-2xl text-lg leading-relaxed text-[var(--vbase-muted)]">
          V-Base keeps contacts, companies, pipeline, tasks and outreach in one fast workspace.
          Import from a spreadsheet in minutes — bad rows are flagged, good ones are kept — keep data quality
          high automatically, and never lose a follow-up again.
        </p>
        <div className="mt-9 flex flex-wrap items-center justify-center gap-3">
          <Link
            to={signedIn ? "/dashboard" : "/signup"}
            className="inline-flex items-center gap-2 rounded-xl bg-[var(--vbase-indigo)] px-6 py-3.5 text-base font-semibold text-white shadow-lg shadow-[var(--vbase-indigo)]/20 transition-colors hover:bg-[var(--vbase-indigo-hover)]"
          >
            {signedIn ? "Go to dashboard" : "Start free"}
            <IconArrowRight className="h-4 w-4" />
          </Link>
          <button
            onClick={() => scrollTo("features")}
            className="rounded-xl border border-[var(--vbase-border)] px-6 py-3.5 text-base font-semibold text-[var(--vbase-slate800)] transition-colors hover:bg-[var(--vbase-bg-alt)]"
          >
            See the features
          </button>
        </div>
        <dl className="mx-auto mt-14 grid max-w-3xl grid-cols-2 gap-6 sm:grid-cols-4">
          {[
            ["40+", "CRM & data tools"],
            ["10s", "to import 1,000 rows"],
            ["99.9%", "targeted uptime"],
            ["No lock-in", "CSV/XLSX export"],
          ].map(([value, label]) => (
            <div key={label}>
              <dt className="text-2xl font-bold text-[var(--vbase-slate900)]">{value}</dt>
              <dd className="mt-1 text-xs font-medium uppercase tracking-wider text-[var(--vbase-muted)]">{label}</dd>
            </div>
          ))}
        </dl>
      </div>
    </section>
  );
}

const FEATURES = [
  {
    icon: <IconUsers className="h-5 w-5" />,
    title: "Contacts & companies",
    body: "Rich profiles with emails, phones, skills, employment history and custom fields — all deduplicated automatically.",
  },
  {
    icon: <IconInbox className="h-5 w-5" />,
    title: "Pipeline & stages",
    body: "A drag-friendly deal pipeline with CRM stages, so every opportunity has a clear next step.",
  },
  {
    icon: <IconListChecks className="h-5 w-5" />,
    title: "Tasks that don't slip",
    body: "Type-specific actions per stage with due dates, owners and activity history on every record.",
  },
  {
    icon: <IconMailPlus className="h-5 w-5" />,
    title: "Email sequences",
    body: "Multi-step outreach that dispatches on a schedule, tracking opens, replies and bounces.",
  },
  {
    icon: <IconWandSparkles className="h-5 w-5" />,
    title: "Smart import",
    body: "Drop in a spreadsheet: columns map automatically, nothing is written before you preview, and bad rows are flagged in an error report.",
  },
  {
    icon: <IconMergeIcon className="h-5 w-5" />,
    title: "Duplicate protection",
    body: "In-file and cross-file dedupe with merge candidates — imports never create the same company twice.",
  },
  {
    icon: <IconGauge className="h-5 w-5" />,
    title: "Data quality score",
    body: "Every record is scored for completeness and freshness, with a queue of exactly what to fix.",
  },
  {
    icon: <IconFilter className="h-5 w-5" />,
    title: "Saved views & searches",
    body: "Slice your data once — by country, stage, quality or tags — and come back to it every day.",
  },
  {
    icon: <IconBarChart3 className="h-5 w-5" />,
    title: "Analytics",
    body: "Stage conversion, growth over time and quality trends, computed from your real records.",
  },
  {
    icon: <IconTagsIcon className="h-5 w-5" />,
    title: "Lists & tags",
    body: "Group records into campaign-ready segments and attach unlimited tags.",
  },
  {
    icon: <IconShieldCheck className="h-5 w-5" />,
    title: "Roles & privacy",
    body: "Session auth, hashed passwords and scoped exports. Your data is yours — export it anytime.",
  },
  {
    icon: <IconLayers className="h-5 w-5" />,
    title: "Teams built in",
    body: "Record ownership, shared lists and an activity feed that shows who changed what, when.",
  },
];


function FeatureGrid() {
  return (
    <section id="features" className="px-4 py-20 sm:px-6">
      <SectionHeading
        eyebrow="Features"
        title="Everything a small team needs to run CRM"
        body="From spreadsheet cleanup to outreach sequences — without juggling five tools or paying per-seat surprises."
      />
      <div className="mx-auto mt-12 grid max-w-6xl gap-5 sm:grid-cols-2 lg:grid-cols-3">
        {FEATURES.map((f) => (
          <div key={f.title} className="vbase-card rounded-2xl p-6">
            <span className="flex h-10 w-10 items-center justify-center rounded-lg bg-[var(--vbase-indigo)]/10 text-[var(--vbase-indigo)]">
              {f.icon}
            </span>
            <h3 className="mt-4 text-base font-semibold text-[var(--vbase-slate900)]">{f.title}</h3>
            <p className="mt-2 text-sm leading-relaxed text-[var(--vbase-muted)]">{f.body}</p>
          </div>
        ))}
      </div>
      <div className="mx-auto mt-10 flex max-w-4xl flex-wrap items-center justify-center gap-x-8 gap-y-3 text-sm text-[var(--vbase-muted)]">
        {[
          <><IconCloudUpload className="h-4 w-4" /> CSV & Excel import</>,
          <><IconGlobe className="h-4 w-4" /> Country & region cards</>,
          <><IconBuilding2 className="h-4 w-4" /> Company domains & tech stack</>,
          <><IconCheckIcon className="h-4 w-4" /> Custom fields</>,
        ].map((item, i) => (
          <span key={i} className="flex items-center gap-2">
            {item}
          </span>
        ))}
      </div>
    </section>
  );
}

const TESTIMONIALS = [
  {
    quote:
      "We moved 9,000 rows off three spreadsheets in an afternoon. The import flagged 40 duplicates for review instead of creating them — that alone paid for the switch.",
    name: "Marta Reyes",
    role: "Head of Sales, Nordwind Recruiting",
    stars: 5,
  },
  {
    quote:
      "Stages, tasks and follow-up sequences finally live in the same place. Our response time to new leads went from days to hours.",
    name: "Tomás Herrera",
    role: "Founder, Copa Media",
    stars: 5,
  },
  {
    quote:
      "The data-quality queue is the feature I didn't know I needed. It tells the team exactly which records to fix next — quality score went from 62% to 91%.",
    name: "Amaraersen Okafor",
    role: "RevOps Lead, Sablyon SaaS",
    stars: 5,
  },
  {
    quote:
      "Exports are one click, no support ticket required. That's how a CRM should respect your data.",
    name: "Piotr Kowalski",
    role: "Ops Manager, Fabrikat AI",
    stars: 5,
  },
  {
    quote:
      "Saved views are how I run our weekly pipeline review the same way, every week. Total time to meeting ready: zero.",
    name: "Dana Whitfield",
    role: "Sales Director, Meridian Logistics",
    stars: 4,
  },
  {
    quote:
      "Custom fields meant we didn't have to bend to someone else's schema. We model exactly what we sell.",
    name: "Sanjay Patel",
    role: "CRM Admin, Orionet Technologies",
    stars: 5,
  },
];

function Testimonials() {
  return (
    <section id="testimonials" className="bg-[var(--vbase-bg-alt)] px-4 py-20 sm:px-6">
      <SectionHeading
        eyebrow="Testimonials"
        title="Teams that stopped fighting their CRM"
        body="From recruiting agencies to SaaS ops — here is what changes in week one."
      />
      <div className="mx-auto mt-12 grid max-w-6xl gap-5 sm:grid-cols-2 lg:grid-cols-3">
        {TESTIMONIALS.map((t) => (
          <figure key={t.name} className="vbase-card rounded-2xl p-6">
            <div className="flex gap-0.5 text-[var(--vbase-amber)]">
              {Array.from({ length: t.stars }).map((_, i) => (
                <IconStarIcon key={i} className="h-4 w-4 fill-current" />
              ))}
            </div>
            <blockquote className="mt-4 text-sm leading-relaxed text-[var(--vbase-slate700)]">
              “{t.quote}”
            </blockquote>
            <figcaption className="mt-5 flex items-center gap-3">
              <span className="flex h-9 w-9 items-center justify-center rounded-full bg-[var(--vbase-brand-a)] text-xs font-bold text-white">
                {t.name.split(" ").map((p) => p[0]).slice(0, 2).join("")}
              </span>
              <span>
                <span className="block text-sm font-semibold text-[var(--vbase-slate900)]">{t.name}</span>
                <span className="block text-xs text-[var(--vbase-muted)]">{t.role}</span>
              </span>
            </figcaption>
          </figure>
        ))}
      </div>
    </section>
  );
}

// Mirrors backend/src/nexus/core/plans.py exactly — the app's Settings →
// Billing page renders the same three plans from the same source. Prices are
// in INR, per user, monthly; every plan includes all CRM features and differs
// only by record capacity.
const PRICING_TIERS = [
  {
    name: "Starter",
    priceInr: 499,
    tagline: "For small teams getting organised.",
    cta: "Start on Starter",
    highlight: false,
    features: [
      "Up to 5,000 records (contacts + companies)",
      "Every CRM feature included",
      "CSV / XLSX imports",
      "Email support",
    ],
  },
  {
    name: "Growth",
    priceInr: 1499,
    tagline: "For growing pipelines — the most popular plan.",
    cta: "Get started",
    highlight: true,
    features: [
      "Up to 25,000 records",
      "Bulk import (100k+ rows per file)",
      "Sequences & campaigns",
      "Priority email support",
    ],
  },
  {
    name: "Scale",
    priceInr: 3999,
    tagline: "For high-volume data teams.",
    cta: "Go Scale",
    highlight: false,
    features: [
      "Up to 200,000 records",
      "Custom fields & advanced analytics",
      "Priority support",
    ],
  },
];

function ContactSection() {
  return (
    <section id="contact" className="bg-[var(--vbase-bg-alt)] px-4 py-20 sm:px-6">
      <SectionHeading
        eyebrow="Contact"
        title="Talk to a human"
        body="Ask about plans, migrations or security. Messages land in our inbox and in our CRM — we answer within two business days."
      />
      <ContactForm />
    </section>
  );
}

function Pricing({ signedIn }: { signedIn: boolean }) {
  return (
    <section id="pricing" className="px-4 py-20 sm:px-6">
      <SectionHeading
        eyebrow="Pricing"
        title="Simple plans, no seat-count ambushes"
        body="Every plan includes the full CRM — plans differ only by capacity. Billed per work­space, monthly, in Indian rupees."
      />
      <div className="mx-auto mt-12 grid max-w-5xl gap-6 lg:grid-cols-3">
        {PRICING_TIERS.map((tier) => (
          <div
            key={tier.name}
            className={`vbase-card relative flex flex-col rounded-2xl p-7 ${
              tier.highlight ? "border-2 border-[var(--vbase-indigo)] shadow-xl shadow-[var(--vbase-indigo)]/10" : ""
            }`}
          >
            {tier.highlight && (
              <span className="absolute -top-3 left-1/2 -translate-x-1/2 rounded-full bg-[var(--vbase-indigo)] px-3 py-1 text-xs font-semibold text-white">
                Most popular
              </span>
            )}
            <h3 className="text-sm font-bold uppercase tracking-wider text-[var(--vbase-muted)]">{tier.name}</h3>
            <p className="mt-3 text-4xl font-black text-[var(--vbase-slate900)]">
              <span className="text-2xl align-top text-[var(--vbase-muted)]">₹</span>
              {tier.priceInr.toLocaleString("en-IN")}
              <span className="ml-1 text-sm font-normal text-[var(--vbase-muted)]">/month</span>
            </p>
            <p className="mt-2 text-sm text-[var(--vbase-muted)]">{tier.tagline}</p>
            <ul className="mt-6 flex-1 space-y-2.5">
              {tier.features.map((f) => (
                <li key={f} className="flex items-start gap-2 text-sm text-[var(--vbase-slate700)]">
                  <IconCheckCircle2 className="mt-0.5 h-4 w-4 flex-shrink-0 text-[var(--vbase-green)]" />
                  {f}
                </li>
              ))}
            </ul>
            <Link
              to={signedIn ? "/billing" : "/signup"}
              className={`mt-7 rounded-xl px-4 py-3 text-center text-sm font-semibold transition-colors ${
                tier.highlight
                  ? "bg-[var(--vbase-indigo)] text-white hover:bg-[var(--vbase-indigo-hover)]"
                  : "border border-[var(--vbase-border)] text-[var(--vbase-slate800)] hover:bg-[var(--vbase-bg-alt)]"
              }`}
            >
              {tier.cta}
            </Link>
          </div>
        ))}
      </div>
      <p className="mx-auto mt-8 max-w-xl text-center text-xs text-[var(--vbase-muted)]">
        Prices in Indian rupees (₹), exclusive of GST. The same plans are shown in the app's Settings → Billing, so what you see here is exactly what your workspace is billed.
      </p>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Contact form — posts to the public /api/v1/contact endpoint.
// ---------------------------------------------------------------------------

interface ContactFormState {
  name: string;
  email: string;
  company: string;
  message: string;
  // Hidden honeypot: rendered off-screen, real visitors never fill it.
  website: string;
}

const CONTACT_FORM_INITIAL: ContactFormState = {
  name: "",
  email: "",
  company: "",
  message: "",
  website: "",
};

function ContactForm() {
  const [form, setForm] = useState<ContactFormState>(CONTACT_FORM_INITIAL);
  const [sending, setSending] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const set = (key: keyof ContactFormState) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
    setForm((f) => ({ ...f, [key]: e.target.value }));

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSending(true);
    try {
      await api.post("/contact", {
        name: form.name.trim(),
        email: form.email,
        company: form.company || undefined,
        message: form.message,
        website: form.website,
      });
      setDone(true);
      setForm(CONTACT_FORM_INITIAL);
    } catch (err) {
      const data =
        err && typeof err === "object" && "data" in err && err.data && typeof err.data === "object"
          ? (err.data as Record<string, unknown>)
          : null;
      const detail = typeof data?.detail === "string" ? data.detail : null;
      setError(detail || "Something went wrong. Email us at support@vbase.example.");
    } finally {
      setSending(false);
    }
  };

  if (done) {
    return (
      <div className="mx-auto mt-12 max-w-2xl rounded-2xl border border-[var(--vbase-border)] bg-[var(--vbase-bg-alt)] p-10 text-center">
        <span className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-[var(--vbase-green)]/10 text-[var(--vbase-green)]">
          <IconCheckCircle2 className="h-6 w-6" />
        </span>
        <h3 className="mt-4 text-xl font-bold text-[var(--vbase-slate900)]">Message received</h3>
        <p className="mt-2 text-sm text-[var(--vbase-muted)]">
          Thanks for reaching out — we will reply within two business days.
        </p>
      </div>
    );
  }

  return (
    <form
      onSubmit={(e) => {
        void submit(e);
      }}
      className="mx-auto mt-12 grid max-w-2xl gap-4 rounded-2xl border border-[var(--vbase-border)] bg-[var(--vbase-bg)] p-6 sm:p-8"
    >
      <div className="grid gap-4 sm:grid-cols-2">
        <label className="block">
          <span className="mb-1.5 block text-sm font-medium text-[var(--vbase-slate700)]">Name *</span>
          <input
            required
            minLength={2}
            value={form.name}
            onChange={set("name")}
            className="w-full rounded-lg border border-[var(--vbase-border)] bg-[var(--vbase-bg)] px-3 py-2.5 text-sm text-[var(--vbase-slate900)] outline-none focus:border-[var(--vbase-indigo)] focus:ring-2 focus:ring-[var(--vbase-indigo)]/20"
            placeholder="Jane Cooper"
          />
        </label>
        <label className="block">
          <span className="mb-1.5 block text-sm font-medium text-[var(--vbase-slate700)]">Work email *</span>
          <input
            required
            type="email"
            value={form.email}
            onChange={set("email")}
            className="w-full rounded-lg border border-[var(--vbase-border)] bg-[var(--vbase-bg)] px-3 py-2.5 text-sm text-[var(--vbase-slate900)] outline-none focus:border-[var(--vbase-indigo)] focus:ring-2 focus:ring-[var(--vbase-indigo)]/20"
            placeholder="jane@company.com"
          />
        </label>
      </div>
      <label className="block">
        <span className="mb-1.5 block text-sm font-medium text-[var(--vbase-slate700)]">Company</span>
        <input
          value={form.company}
          onChange={set("company")}
          className="w-full rounded-lg border border-[var(--vbase-border)] bg-[var(--vbase-bg)] px-3 py-2.5 text-sm text-[var(--vbase-slate900)] outline-none focus:border-[var(--vbase-indigo)] focus:ring-2 focus:ring-[var(--vbase-indigo)]/20"
          placeholder="Company Ltd. (optional)"
        />
      </label>
      <label className="block">
        <span className="mb-1.5 block text-sm font-medium text-[var(--vbase-slate700)]">Message *</span>
        <textarea
          required
          minLength={10}
          rows={5}
          value={form.message}
          onChange={set("message")}
          className="w-full resize-y rounded-lg border border-[var(--vbase-border)] bg-[var(--vbase-bg)] px-3 py-2.5 text-sm text-[var(--vbase-slate900)] outline-none focus:border-[var(--vbase-indigo)] focus:ring-2 focus:ring-[var(--vbase-indigo)]/20"
          placeholder="Tell us about your team and what you would like V-Base to do…"
        />
      </label>
      {/* Honeypot: visually hidden and unfocusable, but bots auto-filling every
          input land here — the API rejects any submission that fills it. */}
      <div aria-hidden="true" className="absolute left-[-9999px] top-[-9999px] h-0 w-0 overflow-hidden">
        <label>
          Website
          <input tabIndex={-1} autoComplete="off" value={form.website} onChange={set("website")} />
        </label>
      </div>

      {error && (
        <p className="flex items-center gap-1.5 text-sm text-[var(--vbase-red)]">
          <IconCheckIcon className="h-4 w-4 rotate-45" />
          {error}
        </p>
      )}

      <button
        type="submit"
        disabled={sending}
        className="inline-flex items-center justify-center gap-2 rounded-xl bg-[var(--vbase-indigo)] px-6 py-3.5 text-base font-semibold text-white transition-colors hover:bg-[var(--vbase-indigo-hover)] disabled:cursor-not-allowed disabled:opacity-60"
      >
        {sending ? "Sending…" : "Send message"}
        {!sending && <IconArrowRight className="h-4 w-4" />}
      </button>
    </form>
  );
}

function CtaBand({ signedIn }: { signedIn: boolean }) {
  return (
    <section className="px-4 pb-20 sm:px-6">
      <div className="mx-auto max-w-5xl rounded-3xl bg-gradient-to-r from-[var(--vbase-brand-a)] to-[var(--vbase-brand-b)] px-8 py-14 text-center">
        <h2 className="text-3xl font-bold text-white">Bring the spreadsheet. Keep the customers.</h2>
        <p className="mx-auto mt-3 max-w-xl text-white/80">
          Import your contacts today and see every row counted — added, updated or flagged — before you commit.
        </p>
        <Link
          to={signedIn ? "/dashboard" : "/signup"}
          className="mt-8 inline-flex items-center gap-2 rounded-xl bg-white px-6 py-3.5 text-base font-semibold text-[var(--vbase-brand-a)] transition-colors hover:bg-white/90"
        >
          {signedIn ? "Open app" : "Create your free account"}
          <IconArrowRight className="h-4 w-4" />
        </Link>
      </div>
    </section>
  );
}

function Footer() {
  return (
    <footer className="border-t border-[var(--vbase-border)] bg-[var(--vbase-bg)] px-4 py-12 sm:px-6">
      <div className="mx-auto grid max-w-6xl gap-8 sm:grid-cols-2 lg:grid-cols-4">
        <div className="space-y-4">
          <Logo />
          <p className="max-w-xs text-sm text-[var(--vbase-muted)]">
            The practical CRM for small teams: import, clean, pipeline and outreach — in one place.
          </p>
        </div>
        <div>
          <h4 className="text-sm font-semibold text-[var(--vbase-slate900)]">Product</h4>
          <ul className="mt-3 space-y-2 text-sm text-[var(--vbase-muted)]">
            <li>
              <button className="transition-colors hover:text-[var(--vbase-indigo)]" onClick={() => scrollTo("features")}>
                Features
              </button>
            </li>
            <li>
              <button className="transition-colors hover:text-[var(--vbase-indigo)]" onClick={() => scrollTo("pricing")}>
                Pricing
              </button>
            </li>
            <li>
              <Link to="/signup" className="transition-colors hover:text-[var(--vbase-indigo)]">
                Create account
              </Link>
            </li>
          </ul>
        </div>
        <div>
          <h4 className="text-sm font-semibold text-[var(--vbase-slate900)]">Legal</h4>
          <ul className="mt-3 space-y-2 text-sm text-[var(--vbase-muted)]">
            <li>
              <Link to="/privacy" className="transition-colors hover:text-[var(--vbase-indigo)]">
                Privacy policy
              </Link>
            </li>
            <li>
              <Link to="/terms" className="transition-colors hover:text-[var(--vbase-indigo)]">
                Terms & conditions
              </Link>
            </li>
          </ul>
        </div>
        <div>
          <h4 className="text-sm font-semibold text-[var(--vbase-slate900)]">Support</h4>
          <ul className="mt-3 space-y-2 text-sm text-[var(--vbase-muted)]">
            <li>
              <Link to="/landing" className="transition-colors hover:text-[var(--vbase-indigo)]" onClick={(e) => { e.preventDefault(); scrollTo("contact"); }}>
                Contact form
              </Link>
            </li>
            <li>
              <a href="mailto:support@vbase.example" className="transition-colors hover:text-[var(--vbase-indigo)]">
                support@vbase.example
              </a>
            </li>
            <li>Mon–Fri, 9:00–18:00 CET</li>
          </ul>
        </div>
      </div>
      <p className="mx-auto mt-10 max-w-6xl border-t border-[var(--vbase-border)] pt-6 text-xs text-[var(--vbase-muted)]">
        © {new Date().getFullYear()} V-Base CRM. All rights reserved.
      </p>
    </footer>
  );
}

export function LandingPage() {
  const { user } = useAuthStore();
  return (
    <div className="-m-6 min-h-screen bg-[var(--vbase-bg)]">
      <Navbar signedIn={Boolean(user)} />
      <main>
        <Hero signedIn={Boolean(user)} />
        <FeatureGrid />
        <Testimonials />
        <Pricing signedIn={Boolean(user)} />
        <ContactSection />
        <CtaBand signedIn={Boolean(user)} />
      </main>
      <Footer />
    </div>
  );
}
