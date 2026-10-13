import { useEffect, type ReactNode } from "react";
import { useThemeStore, type ThemeMode } from "./store";

function resolveTheme(mode: ThemeMode, systemDark: boolean): string {
  if (mode === "system") {
    return systemDark ? "dark" : "light";
  }
  return mode;
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const { mode, setResolvedTheme } = useThemeStore();

  useEffect(() => {
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const getSystemDark = () => media.matches;

    const apply = () => {
      const theme = resolveTheme(mode, getSystemDark());
      setResolvedTheme(theme);
      if (theme === "dark") {
        document.documentElement.classList.add("dark");
      } else {
        document.documentElement.classList.remove("dark");
      }
    };

    apply();
    media.addEventListener("change", apply);
    return () => media.removeEventListener("change", apply);
  }, [mode, setResolvedTheme]);

  return <>{children}</>;
}
