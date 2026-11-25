import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Builds the robot icon into the Streamlit app's static folder (served at /app/static/companion/).
// `npm run dev` serves index.html with the model from that same folder for local tweaking.
export default defineConfig(({ command }) => ({
  plugins: [react()],
  base: "./",
  publicDir: command === "serve" ? "../../app/static/companion" : false,
  build: {
    outDir: "../../app/static/companion",
    emptyOutDir: false,
    target: "es2020",
    chunkSizeWarningLimit: 1200,
    rollupOptions: {
      input: "src/robot-icon.tsx",
      preserveEntrySignatures: "exports-only",
      output: { entryFileNames: "robot.js", chunkFileNames: "robot-[name]-[hash].js", assetFileNames: "[name][extname]" },
    },
  },
}));
