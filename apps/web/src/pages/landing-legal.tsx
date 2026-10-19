// ---------------------------------------------------------------------------
// Public legal pages: privacy policy and terms & conditions.
//
// Plain legal copy styled with the app's design tokens, sharing the landing
// page's chrome (nav + footer) so the look stays consistent. Content lives in
// data arrays so both pages stay short and easy to edit.
// ---------------------------------------------------------------------------

import { Link } from "react-router-dom";
import { IconArrowLeft } from "@/lib/icons";

function LegalShell({
  title,
  updated,
  intro,
  sections,
}: {
  title: string;
  updated: string;
  intro: string;
  sections: { heading: string; paragraphs: string[] }[];
}) {
  return (
    <div className="-m-6 min-h-screen bg-[var(--vbase-bg)]">
      <div className="mx-auto flex max-w-3xl flex-col px-4 py-14 sm:px-6">
        <Link
          to="/"
          className="mb-8 inline-flex w-fit items-center gap-1.5 text-sm font-medium text-[var(--vbase-muted)] transition-colors hover:text-[var(--vbase-indigo)]"
        >
          <IconArrowLeft className="h-4 w-4" /> Back to vbase.example
        </Link>
        <h1 className="text-4xl font-black text-[var(--vbase-slate900)]">{title}</h1>
        <p className="mt-2 text-sm text-[var(--vbase-muted)]">Last updated: {updated}</p>
        <p className="mt-6 text-base leading-relaxed text-[var(--vbase-muted)]">{intro}</p>

        <div className="mt-10 space-y-10">
          {sections.map((s) => (
            <section key={s.heading}>
              <h2 className="text-xl font-bold text-[var(--vbase-slate900)]">{s.heading}</h2>
              {s.paragraphs.map((p, i) => (
                <p key={i} className="mt-3 text-sm leading-relaxed text-[var(--vbase-muted)]">
                  {p}
                </p>
              ))}
            </section>
          ))}
        </div>

        <div className="mt-14 rounded-2xl border border-[var(--vbase-border)] bg-[var(--vbase-bg-alt)] p-6">
          <p className="text-sm text-[var(--vbase-muted)]">
            Questions about this document? Email{" "}
            <a href="mailto:legal@vbase.example" className="font-medium text-[var(--vbase-indigo)] hover:underline">
              legal@vbase.example
            </a>
            and we will respond within two business days.
          </p>
        </div>
      </div>
    </div>
  );
}

const PRIVACY_SECTIONS = [
  {
    heading: "1. Who we are",
    paragraphs: [
      "V-Base CRM (“V-Base”, “we”, “us”) provides customer relationship management software at vbase.example. This policy explains what personal data we collect, why we collect it, and the rights you have over it.",
      "For the purposes of applicable data protection law (including the EU GDPR and UK GDPR), we act as the data controller for account information and as a data processor for the customer records you store in V-Base.",
    ],
  },
  {
    heading: "2. Data we collect",
    paragraphs: [
      "Account data: name, email address, username, password (stored only as a salted hash), and optional profile details you provide.",
      "Usage data: feature interactions, timestamps, IP address, browser type and approximate location, collected to secure accounts and improve the product.",
      "Customer content: the records you import or create — contacts, companies, notes, tasks, email activity and custom fields. This content is processed solely to provide the service to you and your workspace.",
      "Support data: messages you send to our support channels and their metadata.",
    ],
  },
  {
    heading: "3. How we use data",
    paragraphs: [
      "We use your data to: operate and secure the service; authenticate you; sync and back up your records; send transactional email such as password resets and import error reports; measure aggregate product usage; and comply with legal obligations.",
      "We do not sell personal data. We do not use your customer content to train machine-learning models, and we do not share it with advertisers.",
    ],
  },
  {
    heading: "4. Hosting, storage and transfers",
    paragraphs: [
      "Data is stored in managed cloud databases with encryption in transit (TLS 1.2+) and at rest. Backups are taken continuously and retained according to the documented backup schedule.",
      "Where personal data is transferred outside your region, we rely on appropriate safeguards such as Standard Contractual Clauses.",
    ],
  },
  {
    heading: "5. Cookies",
    paragraphs: [
      "V-Base sets strictly necessary cookies only: a signed session cookie that keeps you logged in and a preference cookie for your theme. We do not set advertising or third-party tracking cookies on the app.",
    ],
  },
  {
    heading: "6. Data retention and deletion",
    paragraphs: [
      "You can delete individual records, or your entire account, from the app at any time; this removal is immediate and irreversible. Backups roll off on their normal schedule, and residual copies are deleted or anonymized within 30 days of account closure.",
    ],
  },
  {
    heading: "7. Your rights",
    paragraphs: [
      "Depending on your jurisdiction you may have the right to access, correct, export, restrict or delete your personal data, and to object to certain processing or lodge a complaint with a supervisory authority.",
      "You can exercise most rights directly in the app (profile editing, “My exports”, “Delete account”) or by emailing legal@vbase.example. We respond to verified requests within 30 days.",
    ],
  },
  {
    heading: "8. Changes to this policy",
    paragraphs: [
      "We may update this policy as the product evolves. Material changes are announced by email and in-app at least 14 days before they take effect, and the “last updated” date above always reflects the current version.",
    ],
  },
];

export function PrivacyPage() {
  return (
    <LegalShell
      title="Privacy policy"
      updated="October 2026"
      intro="Your workspace data belongs to you. This policy describes, in plain language, exactly what V-Base stores and why."
      sections={PRIVACY_SECTIONS}
    />
  );
}

const TERMS_SECTIONS = [
  {
    heading: "1. Agreement",
    paragraphs: [
      "These Terms & Conditions (“Terms”) govern your access to and use of the V-Base CRM web application and related services. By creating an account or using the service, you accept these Terms. If you use V-Base on behalf of an organization, you confirm you are authorized to bind that organization.",
    ],
  },
  {
    heading: "2. Accounts and eligibility",
    paragraphs: [
      "You must provide accurate registration information and are responsible for activity that happens under your credentials. Accounts are personal to the registered user; sharing one login across multiple people is not permitted (use the built-in team invites instead).",
      "You must be at least 16 years old, or the minimum age required by the law of your jurisdiction, to use V-Base.",
    ],
  },
  {
    heading: "3. Acceptable use",
    paragraphs: [
      "You agree not to: upload unlawful content or content you have no right to process; import or distribute spam, malware or material that infringes others' rights; probe or disrupt the service, bypass usage limits or rate controls, or access other users' data; reverse engineer the service except where such prohibition is unenforceable by law.",
      "We may suspend or terminate accounts that violate this section, with notice where practicable.",
    ],
  },
  {
    heading: "4. Your data",
    paragraphs: [
      "You retain all rights to the content you store in V-Base. You grant us the limited, non-exclusive license needed to host, back up, display and transmit that content for the sole purpose of providing the service to you and your collaborators.",
      "You can export your data at any time in CSV/XLSX format. If your account is terminated, we make a transition export available on request before deletion.",
    ],
  },
  {
    heading: "5. Subscriptions, billing and refunds",
    paragraphs: [
      "Paid plans are billed per user, in advance, monthly or annually, plus applicable taxes. Plan limits (record counts, import sizes) are described on the pricing page and enforced in the product.",
      "You may cancel at any time; access continues until the end of the paid period and does not auto-renew after that. If we fail to deliver the materially deficient service described on our pricing page, we will refund the proportional unused portion.",
    ],
  },
  {
    heading: "6. Availability, support and changes",
    paragraphs: [
      "We target continuous availability but the service may be interrupted for maintenance or events beyond our reasonable control. Plan-documented SLAs apply only to Enterprise agreements. Feature sets and plan limits may change; material reductions will be announced in advance.",
    ],
  },
  {
    heading: "7. Disclaimers and liability",
    paragraphs: [
      "The service is provided “as is”. To the maximum extent permitted by law, we disclaim implied warranties of merchantability, fitness for a particular purpose and non-infringement.",
      "Our aggregate liability arising from the service is limited to the greater of the fees you paid in the 12 months before the claim or USD 100. We are not liable for indirect, incidental, special or consequential damages, including lost profits or data you could have exported.",
    ],
  },
  {
    heading: "8. Termination",
    paragraphs: [
      "You may close your account at any time from Settings. We may terminate or suspend access for violations of these Terms, for non-payment, or where required by law. Sections 4, 7 and 9 survive termination.",
    ],
  },
  {
    heading: "9. Governing law and disputes",
    paragraphs: [
      "These Terms are governed by the laws of the jurisdiction in which the V-Base operating entity is registered, without regard to conflict-of-law rules. The parties will attempt good-faith resolution of disputes for 30 days before pursuing formal proceedings.",
    ],
  },
];

export function TermsPage() {
  return (
    <LegalShell
      title="Terms & conditions"
      updated="October 2026"
      intro="The ground rules for using V-Base: your rights, your data, and what you can expect from us."
      sections={TERMS_SECTIONS}
    />
  );
}
