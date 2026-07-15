import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// 개발 서버(vite dev)에서 /api 를 로컬 FastAPI(8000)로 프록시.
// 컨테이너 배포 시에는 nginx.conf 가 같은 역할을 한다.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
});
