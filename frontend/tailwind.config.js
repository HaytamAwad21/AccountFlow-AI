/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["Heebo", "Inter", "Noto Sans Hebrew", "Noto Sans Arabic", "system-ui", "Segoe UI", "Arial", "sans-serif"],
      },
      colors: {
        brand: {
          50: "#eef4ff",
          100: "#dbe6fe",
          500: "#3b6cf6",
          600: "#2752e6",
          700: "#1d3fc4",
          900: "#16325c",
        },
        wa: {
          header: "#075e54",
          teal: "#128c7e",
          green: "#25d366",
          bubble: "#dcf8c6",
          wall: "#efe7dd",
          link: "#027eb5",
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
  plugins: [],
};
