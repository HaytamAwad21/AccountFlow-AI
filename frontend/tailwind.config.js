import containerQueries from "@tailwindcss/container-queries";

/** A colour scale whose values come from CSS variables, so light and dark share one set of utilities (see index.css). */
const scale = (name, steps) => Object.fromEntries(steps.map((s) => [s, `rgb(var(--${name}-${s}) / <alpha-value>)`]));
const STEPS = [50, 100, 200, 300, 400, 500, 600, 700, 800, 900];
const token = (name) => `rgb(var(--${name}) / <alpha-value>)`;

/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["Assistant", "Noto Sans Hebrew", "system-ui", "Segoe UI", "Arial", "sans-serif"],
        display: ["Secular One", "Assistant", "sans-serif"],
      },
      // Assistant reads small, so the scale sits a step above Tailwind's default.
      fontSize: {
        xs: ["0.8125rem", "1.15rem"],
        sm: ["0.9375rem", "1.35rem"],
        base: ["1rem", "1.5rem"],
        lg: ["1.125rem", "1.6rem"],
        xl: ["1.3125rem", "1.75rem"],
        "2xl": ["1.625rem", "2rem"],
      },
      // The world is flat and square. Discs stay round (rounded-full); the phone simulator
      // uses explicit radii so it keeps looking like real WhatsApp.
      borderRadius: { DEFAULT: "0", sm: "0", md: "0", lg: "0", xl: "0", "2xl": "0", "3xl": "0" },
      boxShadow: { DEFAULT: "none", sm: "none", md: "none", lg: "none", xl: "none", "2xl": "none" },
      colors: {
        ink: scale("ink", STEPS),
        brand: scale("brand", STEPS),
        canvas: token("canvas"),
        surface: token("surface"),
        link: token("link"),
        field: { DEFAULT: token("field"), muted: token("field-muted") },
        accent: { DEFAULT: "#ffb27a", deep: "#ffa05c", ink: "#0d1533" },
        wa: {
          header: "#075e54",
          teal: "#128c7e",
          green: "#25d366",
          bubble: "#dcf8c6",
          wall: "#efe7dd",
          link: "#027eb5",
          card: "#ffffff",
          bar: "#f0f2f5",
        },
      },
      keyframes: {
        "slide-in": { from: { transform: "translateY(8px)", opacity: "0" }, to: { transform: "translateY(0)", opacity: "1" } },
        pulseDot: { "0%,80%,100%": { opacity: "0.25" }, "40%": { opacity: "1" } },
      },
      animation: {
        "slide-in": "slide-in 180ms ease-out",
        "pulse-dot": "pulseDot 1.2s infinite ease-in-out",
      },
    },
  },
  // Pages lay out by the width of the content area (@container on <main>), not the window: the
  // sidebar and the phone simulator take a different share of the window at every size.
  plugins: [containerQueries],
};
