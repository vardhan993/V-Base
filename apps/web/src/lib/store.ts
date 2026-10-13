import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";

export type ThemeMode = "light" | "dark" | "system";
export type ToastType = "success" | "error" | "info";

export interface AuthState {
  user:any | null;
  token: string | null;
  loading: boolean;
  setUser: (user:any | null) => void;
  setToken: (token:string | null) => void;
  setLoading: (loading:boolean) => void;
  logout: () => void;
}

export const useAuthStore = create<AuthState>()((set) => ({
  user: null,
  token: null,
  loading: true,
  setUser: (user) => set({ user }),
  setToken: (token) => set({ token }),
  setLoading: (loading) => set({ loading }),
  logout: () => set({ user: null, token: null }),
}));

export interface ThemeState {
  mode: ThemeMode;
  setMode: (mode:ThemeMode) => void;
  resolvedTheme: string;
  setResolvedTheme: (theme:string) => void;
}

export const useThemeStore = create<ThemeState>()(
  persist(
    (set) => ({
      mode: "system",
      resolvedTheme: "light",
      setMode: (mode) => set({ mode }),
      setResolvedTheme: (resolvedTheme) => set({ resolvedTheme }),
    }),
    {
      name: "vbase-theme",
      storage: createJSONStorage(() => localStorage),
    }
  )
);

export interface SidebarState {
  collapsed: boolean;
  toggle: () => void;
  setCollapsed: (collapsed:boolean) => void;
}

export const useSidebarStore = create<SidebarState>()(
  persist(
    (set) => ({
      collapsed: false,
      toggle: () => set((s) => ({ collapsed: !s.collapsed })),
      setCollapsed: (collapsed) => set({ collapsed }),
    }),
    { name: "vbase-sidebar", storage: createJSONStorage(() => localStorage) }
  )
);

export interface CommandPaletteState {
  open: boolean;
  setOpen: (open:boolean) => void;
  input: string;
  setInput: (input:string) => void;
}

export const useCommandPaletteStore = create<CommandPaletteState>()((set) => ({
  open: false,
  setOpen: (open) => set({ open }),
  input: "",
  setInput: (input) => set({ input }),
}));

export interface ToastState {
  toasts: Array<{ id: string; message: string; type: "success" | "error" | "info"; duration?: number }>;
  add: (message:string, type:"success" | "error" | "info", duration?:number) => void;
  remove: (id:string) => void;
}

export const useToastStore = create<ToastState>()((set) => ({
  toasts: [],
  add: (message, type, duration = 4000) => {
    const id = Math.random().toString(36).slice(2);
    set((s) => ({ toasts: [...s.toasts, { id, message, type, duration }] }));
    if (duration > 0) {
      setTimeout(() => {
        set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) }));
      }, duration);
    }
    return id;
  },
  remove: (id) => set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })),
}));

export function toast(message:string, type:"success" | "error" | "info", duration?:number) {
  return useToastStore.getState().add(message, type, duration);
}
