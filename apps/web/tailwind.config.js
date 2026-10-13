/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        vbase: {
          sidebar: "#0b1220",
          sidebarHover: "#162032",
          sidebarActive: "#1d2a44",
          border: "#e4e8ef",
          borderDark: "#d0d6e1",
          muted: "#6b7280",
          mutedBg: "#f4f6fb",
          bg: "#ffffff",
          bgAlt: "#f8fafc",
          slate100: "#f1f5f9",
          slate200: "#e2e8f0",
          slate300: "#cbd5e1",
          slate400: "#94a3b8",
          slate500: "#64748b",
          slate600: "#475569",
          slate700: "#334155",
          slate800: "#1e293b",
          slate900: "#0f172a",
          slate950: "#020617",
          indigo: {
            400: "#818cf8",
            500: "#6366f1",
            600: "#4f46e5",
            700: "#4338ca",
          },
          green: {
            500: "#22c55e",
            600: "#16a34a",
          },
          amber: {
            500: "#f59e0b",
            600: "#d97706",
          },
          red: {
            500: "#ef4444",
            600: "#dc2626",
          },
          cyan: {
            500: "#06b6d4",
            600: "#0891b2",
          },
        },
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "-apple-system", "Segoe UI", "Roboto", "Helvetica", "Arial", "sans-serif"],
      },
      fontSize: {
        "2xs": ["0.625rem", { lineHeight: "1rem" }],
      },
      boxShadow: {
        soft: "0 1px 2px 0 rgb(0 0 0 / 0.04), 0 1px 3px 0 rgb(0 0 0 / 0.06)",
        sm: "0 1px 2px 0 rgb(0 0 0 / 0.05)",
        md: "0 4px 6px -1px rgb(0 0 0 / 0.08), 0 2px 4px -2px rgb(0 0 0 / 0.05)",
        lg: "0 10px 15px -3px rgb(0 0 0 / 0.08), 0 4px 6px -4px rgb(0 0 0 / 0.04)",
      },
      borderRadius: {
        sm: "6px",
        DEFAULT: "8px",
        md: "10px",
        lg: "12px",
      },
      animation: {
        "fade-in": "fadeIn 150ms cubic-bezier(0.16, 1, 0.3, 1)",
        "fade-in-up": "fadeInUp 200ms cubic-bezier(0.16, 1, 0.3, 1)",
        "slide-in-right": "slideInRight 200ms cubic-bezier(0.16, 1, 0.3, 1)",
        pulse: "pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite",
      },
      keyframes: {
        fadeIn: {
          "0%": { opacity: "0" },
          "100%": { opacity: "1" },
        },
        fadeInUp: {
          "0%": { opacity: "0", transform: "translateY(8px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        slideInRight: {
          "0%": { opacity: "0", transform: "translateX(-8px)" },
          "100%": { opacity: "1", transform: "translateX(0)" },
        },
      },
    },
  },
  plugins: [],
};
