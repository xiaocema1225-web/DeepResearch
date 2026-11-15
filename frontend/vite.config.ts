import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// 开发模式下把 /api 代理到 LangGraph 后端（langgraph dev 默认 2024 端口）
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://localhost:2024",
        changeOrigin: true,
      },
    },
  },
});
