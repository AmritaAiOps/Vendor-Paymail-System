import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig(({ mode }) => {
  // Env comes from the repo-root .env (VITE_FIREBASE_*, and VITE_BACKEND_URL to override the backend at :8000)
  const env = loadEnv(mode, "..", "");
  return {
    envDir: "..",
    plugins: [react(), tailwindcss()],
    server: { proxy: { "/api": env.VITE_BACKEND_URL || "http://localhost:8000" } },
    test: { environment: "node" },
  };
});
