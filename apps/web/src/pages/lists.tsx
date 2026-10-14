import { useState, useEffect, useCallback } from "react";
import { IconPlus, IconTrash2, IconUsers, IconDownload, IconChevronRight, IconX } from "@/lib/icons";
import { api } from "@/lib/api";
import { ContactList, Contact } from "@/lib/types";
import { toast } from "@/lib/store";
import { downloadCsv } from "@/lib/download";

export function ListsPage() {
  const [lists, setLists] = useState<ContactList[]>([]);
  const [, setLoading] = useState(false);
  const [, setCreateOpen] = useState(false);
  const [selectedList, setSelectedList] = useState<ContactList | null>(null);
  const [listContacts, setListContacts] = useState<Contact[]>([]);
  const [, setAddOpen] = useState(false);

  const fetchLists = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.get<ContactList[]>("/lists");
      setLists(data);
    } catch (e) { console.error(e); } finally { setLoading(false); }
  }, []);

  useEffect(() => { fetchLists(); }, [fetchLists]);

  const fetchListContacts = useCallback(async (id: number) => {
    try {
      const data = await api.get<any>(`/lists/${id}/contacts`);
      setListContacts(data.items || []);
      setSelectedList({ id, name: data.name, description: data.description, kind: data.kind } as any);
    } catch (e) { console.error(e); }
  }, []);

  const deleteList = async (id: number) => {
    await api.delete(`/lists/${id}`);
    toast("List deleted", "success");
    fetchLists();
    setSelectedList(null);
    setListContacts([]);
  };

  const removeContacts = async (contactIds: number[]) => {
    if (!selectedList) return;
    await api.delete(`/lists/${selectedList.id}/contacts`, { params: { contact_ids: contactIds } });
    toast("Removed from list", "success");
    fetchListContacts(selectedList.id);
  };

  const exportList = async () => {
    if (!selectedList) return;
    try {
      const data = await api.get<{ items: any[] }>(`/lists/${selectedList.id}/contacts`);
      downloadCsv(data.items, `${selectedList.name.replace(/[^a-zA-Z0-9]/g, "_")}-contacts.csv`);
      toast("Export started", "success");
    } catch (e: any) { toast(e?.data?.detail || "Export failed", "error"); }
  };

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-[var(--vbase-slate900)]">Lists</h1>
        <button onClick={() => setCreateOpen(true)} className="vbase-btn-primary flex items-center gap-1.5"><IconPlus className="h-4 w-4" /><span>Create list</span></button>
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="vbase-card flex-1 overflow-hidden">
          <div className="border-b border-[var(--vbase-border)] px-4 py-3">
            <h3 className="font-semibold text-[var(--vbase-slate800)]">All lists</h3>
          </div>
          <div className="divide-y divide-[var(--vbase-border)]">
            {lists.map((list) => (
              <div key={list.id} className="flex items-center gap-3 px-4 py-3">
                <div className="flex h-9 w-9 items-center justify-center rounded-md bg-[var(--vbase-bg-alt)]">
                  <IconHash className="h-4 w-4 text-[var(--vbase-slate500)]" />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="font-medium text-[var(--vbase-slate800)]">{list.name}</p>
                  {list.description && <p className="text-xs text-[var(--vbase-slate500)]">{list.description}</p>}
                </div>
                <span className="text-sm text-[var(--vbase-slate500)]">{list.contact_count || 0}</span>
                <div className="flex items-center gap-1" onClick={() => fetchListContacts(list.id)}>
                  <button aria-label={`Open ${list.name}`} className="vbase-btn vbase-btn-icon-sm vbase-btn-ghost">
                    <IconChevronRight className="h-4 w-4" />
                  </button>
                </div>
              </div>
            ))}
            {!lists.length && (
              <div className="px-4 py-12 text-center text-sm text-[var(--vbase-slate500)]">
                <IconHash className="h-8 w-8 mx-auto mb-2 text-[var(--vbase-slate300)]" />
                No lists yet
              </div>
            )}
          </div>
        </div>

        {selectedList && (
          <div className="vbase-card lg:col-span-2">
            <div className="border-b border-[var(--vbase-border)] px-4 py-3 flex items-center justify-between">
              <div className="flex-1">
                <h3 className="font-semibold text-[var(--vbase-slate800)]">{selectedList.name}</h3>
                {selectedList.description && <p className="text-xs text-[var(--vbase-slate500)]">{selectedList.description}</p>}
              </div>
              <div className="flex items-center gap-2">
                <button onClick={exportList} className="vbase-btn-secondary flex items-center gap-1"><IconDownload className="h-4 w-4" /><span>Export</span></button>
                <button onClick={() => setAddOpen(true)} className="vbase-btn-primary flex items-center gap-1"><IconPlus className="h-4 w-4" /><span>Add contacts</span></button>
                <button onClick={() => deleteList(selectedList.id)} className="vbase-btn-danger flex items-center gap-1"><IconTrash2 className="h-4 w-4" /><span>Delete</span></button>
              </div>
            </div>
            <div className="divide-y divide-[var(--vbase-border)]">
              {listContacts.map((contact) => (
                <div key={contact.id} className="flex items-center gap-3 px-4 py-3">
                  <div className="flex h-9 w-9 items-center justify-center rounded-md bg-[var(--vbase-bg-alt)]">
                    <IconUsers className="h-4 w-4 text-[var(--vbase-slate500)]" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="font-medium text-[var(--vbase-slate800)]">{contact.name}</p>
                    <p className="text-xs text-[var(--vbase-slate500)]">{contact.job_title || contact.email}</p>
                  </div>
                  <button aria-label={`Remove ${contact.name} from list`} className="vbase-btn vbase-btn-icon-sm vbase-btn-danger-soft" onClick={() => removeContacts([contact.id])}>
                    <IconX className="h-4 w-4" />
                  </button>
                </div>
              ))}
              {!listContacts.length && (
                <div className="px-4 py-12 text-center text-sm text-[var(--vbase-slate500)]">
                  No contacts in this list
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function IconHash({ className }: any) {
  return <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M4 9h16M4 15h16" /></svg>;
}
