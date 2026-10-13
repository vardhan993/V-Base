import { useEffect, useState, useCallback } from "react";
import { useAuthStore } from "./store";

export function useDebounce<T>(value: T, delay:number) {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);
  return debounced;
}

export function useMediaQuery(query:string): boolean {
  const [matches, setMatches] = useState(false);
  useEffect(() => {
    const media = window.matchMedia(query);
    const onChange = (e: MediaQueryListEvent) => setMatches(e.matches);
    media.addEventListener("change", onChange);
    setMatches(media.matches);
    return () => media.removeEventListener("change", onChange);
  }, [query]);
  return matches;
}

export function useIsDark() {
  return useMediaQuery("(prefers-color-scheme: dark)");
}

export function useOnline() {
  const [online, setOnline] = useState(navigator.onLine);
  useEffect(() => {
    const on = () => setOnline(true);
    const off = () => setOnline(false);
    window.addEventListener("online", on);
    window.addEventListener("offline", off);
    return () => {
      window.removeEventListener("online", on);
      window.removeEventListener("offline", off);
    };
  }, []);
  return online;
}

export function useCopyToClipboard() {
  const [copied, setCopied] = useState(false);
  const copy = useCallback(async (text:string) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
      return true;
    } catch {
      return false;
    }
  }, []);
  return { copied, copy };
}

export function useAsyncState<T>(initial:{loading:boolean; data:T | null; error:any | null} = {loading:false, data:null, error:null}) {
  const [state, setState] = useState(initial);
  const run = useCallback(async (fn: () => Promise<T>) => {
    setState({loading:true, data:null, error:null});
    try {
      const data = await fn();
      setState({loading:false, data, error:null});
      return data;
    } catch (e) {
      setState({loading:false, data:null, error:e});
      throw e;
    }
  }, []);
  return [state, run] as const;
}

export function useSafeAuthRedirect() {
  const { user, loading } = useAuthStore();
  useEffect(() => {
    if (!loading && !user) {
      window.location.hash = "#/login";
    }
  }, [user, loading]);
}
