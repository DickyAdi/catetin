import type { Config } from "tailwindcss";

export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        primary: {
          DEFAULT: "#167D6B",
          hover: "#0F5C4E",
          soft: "#E4F2EE",
          "on-dark": "#3FBAA4",
        },
        canvas: "#FAF7F2",
        surface: {
          white: "#FFFFFF",
          dark: "#1F2A27",
          "dark-soft": "#26332F",
        },
        ink: {
          DEFAULT: "#2D2A26",
          muted: "#6B655E",
          faint: "#9A938A",
        },
        "on-dark": {
          DEFAULT: "#F2EFE9",
          muted: "#B8B2A8",
        },
        hairline: "#E8E2D8",
        "divider-soft": "#F0ECE4",
        profit: "#2E9E6B",
        expense: "#C0563B",
      },
      fontFamily: {
        sans: [
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "Roboto",
          "sans-serif",
        ],
      },
      fontSize: {
        "hero-display": [
          "44px",
          { lineHeight: "1.15", fontWeight: "700", letterSpacing: "0" },
        ],
        "hero-display-mobile": [
          "34px",
          { lineHeight: "1.15", fontWeight: "700", letterSpacing: "0" },
        ],
        "display-md": [
          "32px",
          { lineHeight: "1.2", fontWeight: "700", letterSpacing: "0" },
        ],
        lead: ["24px", { lineHeight: "1.4", fontWeight: "500", letterSpacing: "0" }],
        "body-strong": [
          "18px",
          { lineHeight: "1.5", fontWeight: "700", letterSpacing: "0" },
        ],
        body: ["18px", { lineHeight: "1.6", fontWeight: "400", letterSpacing: "0" }],
        "body-small": [
          "16px",
          { lineHeight: "1.55", fontWeight: "400", letterSpacing: "0" },
        ],
        "button-large": [
          "18px",
          { lineHeight: "1", fontWeight: "700", letterSpacing: "0" },
        ],
        "button-utility": [
          "16px",
          { lineHeight: "1", fontWeight: "600", letterSpacing: "0" },
        ],
        "nav-link": ["15px", { lineHeight: "1", fontWeight: "600", letterSpacing: "0" }],
        "money-figure": [
          "20px",
          { lineHeight: "1.3", fontWeight: "700", letterSpacing: "0" },
        ],
      },
      borderRadius: {
        card: "16px",
        tile: "16px",
        secondary: "8px",
        pill: "9999px",
      },
      boxShadow: {
        evidence: "0 1px 3px rgba(45,42,38,0.08), 0 8px 24px rgba(45,42,38,0.06)",
      },
      spacing: {
        xxs: "4px",
        xs: "8px",
        sm: "12px",
        md: "16px",
        lg: "24px",
        xl: "32px",
        xxl: "48px",
        section: "80px",
      },
      maxWidth: {
        content: "1040px",
      },
      screens: {
        tablet: "641px",
        desktop: "834px",
        wide: "1201px",
      },
      keyframes: {
        "accordion-down": {
          from: { height: "0" },
          to: { height: "var(--radix-accordion-content-height)" },
        },
        "accordion-up": {
          from: { height: "var(--radix-accordion-content-height)" },
          to: { height: "0" },
        },
      },
      animation: {
        "accordion-down": "accordion-down 0.2s ease-out",
        "accordion-up": "accordion-up 0.2s ease-out",
      },
    },
  },
  plugins: [],
} satisfies Config;
