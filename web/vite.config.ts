import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The live API (engine/, FastAPI) runs on :8100; the dev server proxies /live to it so
// the browser sees one origin. `vite build` output is served by the API itself.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: { "/live": { target: "http://127.0.0.1:8100", changeOrigin: true } },
  },
  build: { target: "es2023", chunkSizeWarningLimit: 900 },
});
