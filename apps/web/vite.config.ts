import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    port: 5173,
    strictPort: true,
    host: "127.0.0.1",
    open: false,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
  build: {
    target: "es2020",
    outDir: "dist",
    rollupOptions: {
      output: {
        // Keep long-lived vendor code in separate cacheable chunks so app-code
        // edits do not invalidate the browser cache for library code, and so
        // charts (recharts) only download for the pages that render them.
        manualChunks(id) {
          if (!id.includes("node_modules")) return undefined;
          if (id.includes("recharts") || id.includes("d3-")) return "charts";
          if (id.includes("@radix-ui") || id.includes("@floating-ui") || id.includes("@tanstack")) return "radix";
          if (id.includes("lucide-react")) return "icons";
          if (id.includes("react") || id.includes("scheduler") || id.includes("react-router") || id.includes("zustand")) return "react-core";
          return "vendor";
        },
      },
    },
    chunkSizeWarningLimit: 700,
  },
});
