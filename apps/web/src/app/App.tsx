import { lazy, Suspense, useEffect, useState } from "react";
import { HashRouter, Routes, Route, Navigate, useLocation } from "react-router-dom";
import { ThemeProvider } from "@/lib/theme";
import { useAuthStore, useSidebarStore } from "@/lib/store";
import { api } from "@/lib/api";
import { Sidebar } from "@/components/sidebar";
import { Topbar } from "@/components/topbar";
import { CommandPalette } from "@/components/command-palette";
import { ToastStack } from "@/components/toast-stack";
import { Toaster } from "@/components/ui/toaster";
import { Loader2 } from "lucide-react";

// Every page is code-split: initial load ships only the shell, auth pages and
// the route you land on; the rest are fetched on first navigation.
const LoginPage = lazy(() => import("@/pages/login").then((m) => ({ default: m.LoginPage })));
const SignupPage = lazy(() => import("@/pages/signup").then((m) => ({ default: m.SignupPage })));
const DashboardPage = lazy(() => import("@/pages/dashboard").then((m) => ({ default: m.DashboardPage })));
const PipelinePage = lazy(() => import("@/pages/pipeline").then((m) => ({ default: m.PipelinePage })));
const TasksPage = lazy(() => import("@/pages/tasks").then((m) => ({ default: m.TasksPage })));
const CompaniesPage = lazy(() => import("@/pages/companies").then((m) => ({ default: m.CompaniesPage })));
const CompanyDetailPage = lazy(() => import("@/pages/company").then((m) => ({ default: m.CompanyDetailPage })));
const ContactsListPage = lazy(() => import("@/pages/contacts").then((m) => ({ default: m.ContactPage })));
const ContactDetailPage = lazy(() => import("@/pages/contact").then((m) => ({ default: m.ContactPage })));
const ContactEditPage = lazy(() => import("@/pages/contact-edit").then((m) => ({ default: m.ContactEditPage })));
const ContactNewPage = lazy(() => import("@/pages/contact-new").then((m) => ({ default: m.ContactNewPage })));
const CompanyNewPage = lazy(() => import("@/pages/company-new").then((m) => ({ default: m.CompanyNewPage })));
const CompanyEditPage = lazy(() => import("@/pages/company-edit").then((m) => ({ default: m.CompanyEditPage })));
const LeadsPage = lazy(() => import("@/pages/leads").then((m) => ({ default: m.LeadsPage })));
const LeadNewPage = lazy(() => import("@/pages/lead-new").then((m) => ({ default: m.LeadNewPage })));
const LeadDetailPage = lazy(() => import("@/pages/lead").then((m) => ({ default: m.LeadDetailPage })));
const LeadEditPage = lazy(() => import("@/pages/lead-edit").then((m) => ({ default: m.LeadEditPage })));
const AllRecordsPage = lazy(() => import("@/pages/all-records").then((m) => ({ default: m.AllRecordsPage })));
const ListsPage = lazy(() => import("@/pages/lists").then((m) => ({ default: m.ListsPage })));
const TagsPage = lazy(() => import("@/pages/tags").then((m) => ({ default: m.TagsPage })));
const SavedSearchesPage = lazy(() => import("@/pages/saved-searches").then((m) => ({ default: m.SavedSearchesPage })));
const SavedViewsPage = lazy(() => import("@/pages/saved-views").then((m) => ({ default: m.SavedViewsPage })));
const CustomFieldsPage = lazy(() => import("@/pages/custom-fields").then((m) => ({ default: m.CustomFieldsPage })));
const BackupPage = lazy(() => import("@/pages/backup").then((m) => ({ default: m.BackupPage })));
const ImportPage = lazy(() => import("@/pages/import").then((m) => ({ default: m.ImportPage })));
const DuplicatesPage = lazy(() => import("@/pages/duplicates").then((m) => ({ default: m.DuplicatesPage })));
const DataQualityPage = lazy(() => import("@/pages/data-quality").then((m) => ({ default: m.DataQualityPage })));
const AnalyticsPage = lazy(() => import("@/pages/analytics").then((m) => ({ default: m.AnalyticsPage })));
const ActivityPage = lazy(() => import("@/pages/activity").then((m) => ({ default: m.ActivityPage })));
const CampaignsPage = lazy(() => import("@/pages/campaigns").then((m) => ({ default: m.CampaignsPage })));
const SequencesPage = lazy(() => import("@/pages/sequences").then((m) => ({ default: m.SequencesPage })));
const SettingsPage = lazy(() => import("@/pages/settings").then((m) => ({ default: m.SettingsPage })));
const BillingPage = lazy(() => import("@/pages/billing").then((m) => ({ default: m.BillingPage })));
const Layout = lazy(() => import("@/components/layout").then((m) => ({ default: m.Layout })));

function AuthLoader({ children }: { children:React.ReactNode }) {
  const { user, loading, setUser, setToken, setLoading } = useAuthStore();
  const [checked, setChecked] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const tryLoad = async () => {
      try {
        const data = await api.get<{ id:number; email:string; username:string; full_name:string | null; is_active:boolean; is_superuser:boolean }>("/auth/me");
        setUser(data);
        setToken("session");
      } catch {
        setUser(null);
        setToken(null);
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    tryLoad();
    return () => { cancelled = true; };
  }, [setUser, setToken, setLoading]);

  useEffect(() => {
    if (!loading) setChecked(true);
  }, [loading, setChecked]);

  if (!checked) return <LoadingScreen />;
  if (!user) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

function LoadingScreen() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-[var(--vbase-bg)]">
      <div className="flex flex-col items-center gap-3 text-[var(--vbase-slate500)]">
        <Loader2 className="h-8 w-8 animate-spin text-[var(--vbase-indigo)]" />
        <span className="text-sm font-medium">Loading V-Base</span>
      </div>
    </div>
  );
}

function AppShell() {
  const location = useLocation();
  const { collapsed } = useSidebarStore();
  const isAuthRoute = location.pathname.startsWith("/login") || location.pathname.startsWith("/signup");

  return (
    <div className="flex h-screen bg-[var(--vbase-bg)]">
      {!isAuthRoute && <Sidebar />}
      <div
        className={`flex flex-1 flex-col transition-all duration-200 md:ml-[224px] ${
          collapsed ? "md:ml-[68px]" : ""
        }`}
      >
        {!isAuthRoute && <Topbar />}
        <main className="flex-1 p-6 overflow-auto">
          <Routes>
            <Route
              element={
                <AuthLoader>
                  <Suspense fallback={<LoadingScreen />}>
                    <Layout />
                  </Suspense>
                </AuthLoader>
              }
            >
              <Route path="/" element={<Navigate to="/dashboard" replace />} />
              <Route path="/dashboard" element={<DashboardPage />} />
              <Route path="/pipeline" element={<PipelinePage />} />
              <Route path="/tasks" element={<TasksPage />} />
              <Route path="/leads" element={<LeadsPage />} />
              <Route path="/leads/new" element={<LeadNewPage />} />
              <Route path="/leads/:id" element={<LeadDetailPage />} />
              <Route path="/leads/:id/edit" element={<LeadEditPage />} />
              <Route path="/companies" element={<CompaniesPage />} />
              <Route path="/companies/new" element={<CompanyNewPage />} />
              <Route path="/companies/:id" element={<CompanyDetailPage />} />
              <Route path="/companies/:id/edit" element={<CompanyEditPage />} />
              <Route path="/contacts" element={<ContactsListPage />} />
              <Route path="/contacts/new" element={<ContactNewPage />} />
              <Route path="/contacts/:id" element={<ContactDetailPage />} />
              <Route path="/contacts/:id/edit" element={<ContactEditPage />} />
              <Route path="/all-records" element={<AllRecordsPage />} />
  <Route path="/lists" element={<ListsPage />} />
  <Route path="/tags" element={<TagsPage />} />
  <Route path="/campaigns" element={<CampaignsPage />} />
              <Route path="/saved-searches" element={<SavedSearchesPage />} />
              <Route path="/saved-views" element={<SavedViewsPage />} />
              <Route path="/custom-fields" element={<CustomFieldsPage />} />
              <Route path="/backup" element={<BackupPage />} />
              <Route path="/import" element={<ImportPage />} />
              <Route path="/duplicates" element={<DuplicatesPage />} />
              <Route path="/data-quality" element={<DataQualityPage />} />
              <Route path="/analytics" element={<AnalyticsPage />} />
              <Route path="/sequences" element={<SequencesPage />} />
              <Route path="/activity" element={<ActivityPage />} />
              <Route path="/settings" element={<SettingsPage />} />
              <Route path="/billing" element={<BillingPage />} />
            </Route>
            <Route
              path="/login"
              element={
                <Suspense fallback={<LoadingScreen />}>
                  <LoginPage />
                </Suspense>
              }
            />
            <Route
              path="/signup"
              element={
                <Suspense fallback={<LoadingScreen />}>
                  <SignupPage />
                </Suspense>
              }
            />
          </Routes>
        </main>
      </div>
      {!isAuthRoute && <CommandPalette />}
      {!isAuthRoute && <ToastStack />}
      <Toaster />
    </div>
  );
}

export function App() {
  return (
    <HashRouter>
      <ThemeProvider>
        <AppShell />
      </ThemeProvider>
    </HashRouter>
  );
}
