import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  base: "./",
  server: {
    proxy: {
      "/api": "http://127.0.0.1:8000",
      "/app/api": {
        target: "http://127.0.0.1:8000",
        rewrite: (path) => path.replace(/^\/app/, ""),
      },
    },
  },
  build: {
    chunkSizeWarningLimit: 1500,
    rollupOptions: { output: { manualChunks: { map: ["maplibre-gl"] } } },
  },
});
