import { useState, useEffect } from "react";
import { api } from "@/lib/api";
import { toast } from "@/lib/store";
import { IconMailPlus, IconTrash2 } from "@/lib/icons";

export function CampaignsPage() {
  const [campaigns, setCampaigns] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [nameFilter, setNameFilter] = useState("");

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const params: Record<string, string> = {};
        if (nameFilter) params.name = nameFilter;
        const data = await api.get<{ items: any[]; total: number }>("/campaigns", { params });
        if (!cancelled) setCampaigns(data.items || []);
        setLoading(false);
      } catch (e) {
        console.error(e);
      }
    };
    load();
    return () => { cancelled = true; };
  }, [nameFilter]);

  const deleteCampaign = async (id: number) => {
    if (!window.confirm("Delete this campaign?")) return;
    try {
      await api.delete(`/campaigns/${id}`);
      toast("Campaign deleted", "success");
      const params: Record<string, string> = {};
      if (nameFilter) params.name = nameFilter;
      const data = await api.get<{ items: any[]; total: number }>("/campaigns", { params });
      setCampaigns(data.items || []);
    } catch (e: any) {
      toast(e?.data?.detail || "Could not delete campaign", "error");
    }
  };

  const activeCount = campaigns.filter((c) => c.active).length;
  const sentCount = campaigns.filter((c) => c.sent_count > 0).length;
  const activeLabel = activeCount === 1 ? "active campaign" : `${activeCount} active campaigns`;

  const handleCreate = async (name: string) => {
    if (!name.trim()) {
      toast("Campaign name is required", "error");
      return;
    }
    try {
      await api.post("/campaigns", { name });
      toast("Campaign created", "success");
      setNameFilter("");
      const params: Record<string, string> = {};
      const data = await api.get<{ items: any[]; total: number }>("/campaigns", { params });
      setCampaigns(data.items || []);
    } catch (e: any) {
      toast(e?.data?.detail || "Could not create campaign", "error");
    }
  };

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-4">
        <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
          <div className="space-y-3">
            <DetailCard title="Campaigns" icon={<IconMailPlus className="h-4 w-4" />}>
              {loading ? (
                <div className="h-6 w-48 rounded bg-[var(--vbase-slate200)]" />
              ) : (
                <ul className="space-y-2">
                  {campaigns.length ? (
                    campaigns.map((c) => (
                      <li key={c.id} className="flex items-center gap-2 text-sm">
                        <span className={c.active ? "font-medium text-[var(--vbase-green)]" : "font-medium text-[var(--vbase-slate600)]"}>
                          {c.name}
                        </span>
                        {c.active && (
                          <span className="text-xs text-[var(--vbase-slate400)]">• active</span>
                        )}
                        {!c.active && (
                          <span className="text-xs text-[var(--vbase-slate400)]">• inactive</span>
                        )}
                        <span className="ml-auto text-xs text-[var(--vbase-slate500)]">
                          {c.start_date ? new Date(c.start_date).toLocaleDateString() : ""}
                        </span>
                        <button
                          onClick={() => deleteCampaign(c.id)}
                          className="vbase-btn-danger-soft text-xs"
                        >
                          <IconTrash2 className="h-3 w-3" />
                          Delete
                        </button>
                      </li>
                    ))
                  ) : (
                    <p className="text-sm text-[var(--vbase-slate400)]">No campaigns yet.</p>
                  )}
                </ul>
              )}
            </DetailCard>
          </div>

          <div className="space-y-3">
            <DetailCard title="Create Campaign" icon={<IconMailPlus className="h-4 w-4" />}>
              <form
                onSubmit={(e: React.FormEvent) => {
                  e.preventDefault();
                  const input = (e.target as HTMLFormElement).elements.namedItem("name") as HTMLInputElement;
                  const name = input ? input.value.trim() : "";
                  if (!name) {
                    toast("Campaign name is required", "error");
                    return;
                  }
                  handleCreate(name);
                }}
              >
                <input
                  type="text"
                  name="name"
                  placeholder="Campaign name"
                  className="vbase-input h-8 text-sm"
                />
                <button type="submit" className="vbase-btn-primary vbase-btn-sm flex-shrink-0">
                  Create
                </button>
              </form>
            </DetailCard>
          </div>
        </div>
      </div>

      <div className="grid gap-6 md:grid-cols-2">
        <DetailCard title="Active campaigns" icon={<IconMailPlus className="h-4 w-4" />}>
          {activeCount > 0 ? (
            <p className="text-sm text-[var(--vbase-slate800)]">
              {activeLabel}
            </p>
          ) : (
            <p className="text-sm text-[var(--vbase-slate400)]">No active campaigns</p>
          )}
        </DetailCard>

        <DetailCard title="Campaign stats" icon={<IconMailPlus className="h-4 w-4" />}>
          {campaigns.length ? (
            <p className="text-sm text-[var(--vbase-slate800)]">
              Total: {campaigns.length}, Sent: {sentCount}
            </p>
          ) : (
            <p className="text-sm text-[var(--vbase-slate400)]">No campaigns</p>
          )}
        </DetailCard>
      </div>

      <div className="vbase-card">
        <p className="text-sm text-[var(--vbase-slate500)]">
          No contacts filter for campaigns
        </p>
      </div>
    </div>
  );
}

function DetailCard({ title, icon, children }: { title: string; icon: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className="flex items-start gap-3 rounded-lg border border-[var(--vbase-border)] bg-[var(--vbase-bg-alt)] p-4">
      <div className="mt-0.5 flex h-7 w-7 items-center justify-center rounded border border-[var(--vbase-border)] bg-[var(--vbase-bg)] text-[var(--vbase-slate500)]">
        {icon}
      </div>
      <div className="min-w-0 flex-1">
        <p className="text-xs text-[var(--vbase-slate500)]">{title}</p>
        <div className="mt-1.5">{children}</div>
      </div>
    </div>
  );
}