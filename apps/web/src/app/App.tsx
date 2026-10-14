import { useEffect, useState } from "react";
import { HashRouter, Routes, Route, Navigate, useLocation } from "react-router-dom";
import { ThemeProvider } from "@/lib/theme";
import { useAuthStore, useSidebarStore } from "@/lib/store";
import { api } from "@/lib/api";
import { Sidebar } from "@/components/sidebar";
import { Topbar } from "@/components/topbar";
import { CommandPalette } from "@/components/command-palette";
import { ToastStack } from "@/components/toast-stack";
import { Toaster } from "@/components/ui/toaster";
import { LoginPage } from "@/pages/login";
import { SignupPage } from "@/pages/signup";
import { DashboardPage } from "@/pages/dashboard";
import { PipelinePage } from "@/pages/pipeline";
import { TasksPage } from "@/pages/tasks";
import { CompaniesPage } from "@/pages/companies";
import { CompanyDetailPage } from "@/pages/company";
import { ContactPage } from "@/pages/contacts";
import { ContactPage as ContactDetailPage } from "@/pages/contact";
import { ContactEditPage } from "@/pages/contact-edit";
import { ContactNewPage } from "@/pages/contact-new";
import { CompanyNewPage } from "@/pages/company-new";
import { CompanyEditPage } from "@/pages/company-edit";
import { LeadsPage } from "@/pages/leads";
import { LeadNewPage } from "@/pages/lead-new";
import { LeadDetailPage } from "@/pages/lead";
import { LeadEditPage } from "@/pages/lead-edit";
import { AllRecordsPage } from "@/pages/all-records";
import { ListsPage } from "@/pages/lists";
import { TagsPage } from "@/pages/tags";
import { SavedSearchesPage } from "@/pages/saved-searches";
import { SavedViewsPage } from "@/pages/saved-views";
import { CustomFieldsPage } from "@/pages/custom-fields";
import { BackupPage } from "@/pages/backup";
import { ImportPage } from "@/pages/import";
import { DuplicatesPage } from "@/pages/duplicates";
import { DataQualityPage } from "@/pages/data-quality";
import { AnalyticsPage } from "@/pages/analytics";
import { ActivityPage } from "@/pages/activity";
import { SequencesPage } from "@/pages/sequences";
import { SettingsPage } from "@/pages/settings";
import { Layout } from "@/components/layout";
import { Loader2 } from "lucide-react";

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
      <div className={`flex flex-1 flex-col transition-all duration-200 ${collapsed ? "ml-14" : "ml-0"}`}>
        {!isAuthRoute && <Topbar />}
        <main className="flex-1 p-6 overflow-auto">
          <Routes>
            <Route element={<AuthLoader><Layout /></AuthLoader>}>
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
              <Route path="/contacts" element={<ContactPage />} />
              <Route path="/contacts/new" element={<ContactNewPage />} />
              <Route path="/contacts/:id" element={<ContactDetailPage />} />
              <Route path="/contacts/:id/edit" element={<ContactEditPage />} />
              <Route path="/all-records" element={<AllRecordsPage />} />
              <Route path="/lists" element={<ListsPage />} />
              <Route path="/tags" element={<TagsPage />} />
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
            </Route>
            <Route path="/login" element={<LoginPage />} />
            <Route path="/signup" element={<SignupPage />} />
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
