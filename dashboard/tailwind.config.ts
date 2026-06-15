import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Tour-page palette
        bg: {
          deep: "#050810",
          base: "#0a0f1c",
          elev: "#131b2e",
          card: "#161e35",
          overlay: "#1c2540",
        },
        ink: {
          1: "#e6edf7",
          2: "#a4afc4",
          3: "#6e7a92",
          4: "#4a5570",
        },
        accent: {
          cyan: "#22d3ee",
          violet: "#a78bfa",
          amber: "#f59e0b",
          up: "#22c55e",
          down: "#ef4444",
          blue: "#60a5fa",
        },
        // Legacy terminal colors retained for the pixel TradingFloor canvas
        terminal: {
          bg: "#0a0e0a",
          panel: "#0f1f0f",
          border: "#1f3a1f",
          text: "#9eff9e",
          dim: "#4a8a4a",
          amber: "#ffb000",
          red: "#ff4040",
          blue: "#40a0ff",
        },
      },
      fontFamily: {
        sans: ["var(--font-inter)", "system-ui", "sans-serif"],
        display: ["var(--font-space-grotesk)", "system-ui", "sans-serif"],
        mono: ["var(--font-jetbrains-mono)", "monospace"],
        // Pixel fonts for the Trading Floor canvas
        terminal: ["var(--font-vt323)", "monospace"],
        pixel: ["var(--font-press-start)", "monospace"],
      },
      boxShadow: {
        "tour-card": "0 24px 64px rgba(0,0,0,0.55), inset 0 1px 0 rgba(255,255,255,0.04)",
        "tour-glow": "0 0 60px rgba(34,211,238,0.15)",
      },
    },
  },
  plugins: [],
};

export default config;
