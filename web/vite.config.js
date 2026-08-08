import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Local dev proxies /api to the FastAPI server on :8000.
// In production on Zerops, set VITE_API_BASE to the api service URL at build time.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      "/api": "http://localhost:8000",
    },
  },
});
