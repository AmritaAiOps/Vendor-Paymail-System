import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig(({ mode }) => {
  // Backend port is 8000 (docs/CONTRACT.md); override with VITE_BACKEND_URL in frontend/.env.local
  const env = loadEnv(mode, ".", "");
  return {
    plugins: [react(), tailwindcss()],
    server: { proxy: { "/api": env.VITE_BACKEND_URL || "http://localhost:8000" } },
    test: { environment: "node" },
  };
});
