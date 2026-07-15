# frontend/Dockerfile — React(Vite) 멀티스테이지: node 빌드 → nginx 정적 서빙
# --- 빌드 스테이지 ---
FROM node:20-alpine AS build
WORKDIR /app
COPY package.json ./
RUN npm install
COPY . .
RUN npm run build

# --- 서빙 스테이지 ---
FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
