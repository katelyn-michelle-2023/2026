import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    allowedHosts: ["findyouraura.fit"],
    proxy: {
      "/chat": { target: "http://localhost:8000", changeOrigin: true },
      "/audio": { target: "http://localhost:8000", changeOrigin: true },
    },
  },
});
