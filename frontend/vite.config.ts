import { defineConfig, loadEnv } from "vite";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "VITE_");
  return {
  server: {
    proxy: {
      "/api": env.VITE_API_PROXY_TARGET || "http://127.0.0.1:8000",
    },
  },
  };
});
