import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        surface: {
          950: "#07111f",
          900: "#0d1726",
          800: "#152235",
          700: "#22324a",
        },
        ink: {
          50: "#f7fbff",
          100: "#deebf7",
          200: "#b8d0e8",
          300: "#88abc8",
          400: "#5c84a3",
        },
        accent: {
          cyan: "#4fd1c5",
          blue: "#75a9ff",
          amber: "#f3be4d",
          red: "#ff7b72",
          green: "#5fd08a",
          violet: "#b69cff",
        },
        signal: {
          success: "#5fd08a",
          failure: "#ff7b72",
          warning: "#f3be4d",
          inconclusive: "#b69cff",
          info: "#75a9ff",
          concern: "#f59e85",
          replay: "#4fd1c5",
          semantic: "#a7b6ff",
        },
      },
      boxShadow: {
        panel: "0 12px 36px rgba(3, 10, 19, 0.28)",
      },
      borderRadius: {
        xl: "1rem",
      },
      fontFamily: {
        sans: ["var(--font-sans)", "Segoe UI", "sans-serif"],
        mono: ["var(--font-mono)", "Consolas", "monospace"],
      },
    },
  },
  plugins: [],
};

export default config;
