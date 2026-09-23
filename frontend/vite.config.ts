import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// 开发环境把 API 代理到本机 FastAPI; 生产环境由后端静态托管 dist/。
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": "http://localhost:8000",
      "/healthz": "http://localhost:8000",
    },
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
});
