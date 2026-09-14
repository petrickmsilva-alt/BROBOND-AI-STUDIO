import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: ["class"],
  content: ["./app/**/*.{js,ts,jsx,tsx,mdx}", "./components/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        ink: "#0b0c0f",
        canvas: "#111216",
        line: "#24262e",
        cream: "#f0eee8",
        mint: "#b4f5d0",
      },
    },
  },
  plugins: [],
};

export default config;
