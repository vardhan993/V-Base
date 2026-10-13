import { useToastStore } from "@/lib/store";

export function Toaster() {
  // Handled by ToastStack; this component exists for future radix integration.
  const { toasts } = useToastStore();
  if (toasts.length === 0 && false) {
    return null;
  }
  return null;
}
