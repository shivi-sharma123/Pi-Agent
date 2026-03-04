FROM node:20-alpine AS build
WORKDIR /app
COPY dashboard/frontend/package.json ./
RUN npm install
COPY dashboard/frontend/ ./
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY dashboard/frontend/nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 3001
CMD ["nginx", "-g", "daemon off;"]
