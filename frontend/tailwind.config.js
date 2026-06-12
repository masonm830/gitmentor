/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        bg: "#0d1117",
        surface: "#161b22",
        surface2: "#1c2128",
        border: "#30363d",
        accent: "#58a6ff",
        text: "#e6edf3",
        textmute: "#8b949e",
        success: "#3fb950",
        warning: "#d29922",
        danger: "#f85149",
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "monospace"],
      },
      borderRadius: {
        DEFAULT: "6px",
        md: "6px",
        lg: "6px",
      },
    },
  },
  plugins: [],
};
