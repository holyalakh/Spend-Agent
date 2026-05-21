/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        cursor: {
          bg: "#1e1e1e",
          input: "#2d2d2d",
          sidebar: "#252526",
          border: "#3e3e3e",
          text: "#cccccc",
          subtle: "#6b6b6b",
          muted: "#858585",
          accent: "#0078d4",
          "accent-hover": "#1a86d9",
          user: "#2d2d2d",
        },
      },
      fontFamily: {
        sans: [
          "-apple-system",
          "BlinkMacSystemFont",
          "Segoe UI",
          "Roboto",
          "Helvetica Neue",
          "Arial",
          "sans-serif",
        ],
        mono: ["Menlo", "Monaco", "Courier New", "monospace"],
      },
    },
  },
  plugins: [],
};
