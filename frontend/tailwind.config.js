/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["Outfit", "system-ui", "sans-serif"],
      },
      colors: {
        paper: "#111114",
        surface: {
          DEFAULT: "#1f1f27",
          muted: "#282832",
        },
        ink: {
          DEFAULT: "#f2f2f6",
          muted: "#b8b8c4",
          light: "#8f8f9e",
        },
        glass: {
          DEFAULT: "rgba(17,17,20,0.85)",
          stroke: "rgba(255,255,255,0.09)",
          hover: "rgba(255,255,255,0.05)",
        },
        rail: "#0b0b0e",
        accent: {
          DEFAULT: "#4d93ff",
          light: "#7ab5ff",
          muted: "rgba(77,147,255,0.14)",
        },
        danger: {
          DEFAULT: "#dc2626",
          muted: "rgba(220,38,38,0.08)",
        },
        success: {
          DEFAULT: "#16a34a",
          muted: "rgba(22,163,74,0.08)",
        },
        warn: {
          DEFAULT: "#d97706",
          muted: "rgba(217,119,6,0.08)",
        },
      },
      borderRadius: {
        "2xl": "1rem",
        "3xl": "1.5rem",
        "4xl": "2rem",
      },
      boxShadow: {
        "soft": "0 1px 3px rgba(0,0,0,0.04), 0 1px 2px rgba(0,0,0,0.02)",
        "medium": "0 4px 12px rgba(0,0,0,0.06), 0 1px 3px rgba(0,0,0,0.03)",
        "lifted": "0 8px 30px rgba(0,0,0,0.08), 0 2px 6px rgba(0,0,0,0.03)",
        "glow-blue": "0 0 20px rgba(37,99,235,0.15)",
      },
      keyframes: {
        "fade-in": {
          "0%": { opacity: "0", transform: "translateY(20px) scale(0.98)", filter: "blur(3px)" },
          "100%": { opacity: "1", transform: "translateY(0) scale(1)", filter: "blur(0)" },
        },
        "fade-up": {
          "0%": { opacity: "0", transform: "translateY(28px)", filter: "blur(4px)" },
          "100%": { opacity: "1", transform: "translateY(0)", filter: "blur(0)" },
        },
        "scale-in": {
          "0%": { opacity: "0", transform: "scale(0.94)" },
          "100%": { opacity: "1", transform: "scale(1)" },
        },
        shimmer: {
          "0%": { transform: "translateX(-100%)" },
          "100%": { transform: "translateX(100%)" },
        },
        "pulse-glow": {
          "0%, 100%": { boxShadow: "0 0 8px rgba(37,99,235,0.1)" },
          "50%": { boxShadow: "0 0 20px rgba(37,99,235,0.2)" },
        },
      },
      animation: {
        "fade-in": "fade-in 0.8s cubic-bezier(0.32,0.72,0,1) forwards",
        "fade-up": "fade-up 0.8s cubic-bezier(0.32,0.72,0,1) forwards",
        "scale-in": "scale-in 0.6s cubic-bezier(0.32,0.72,0,1) forwards",
        shimmer: "shimmer 2.5s infinite linear",
        "pulse-glow": "pulse-glow 2s cubic-bezier(0.4,0,0.6,1) infinite",
      },
    },
  },
  plugins: [],
};
