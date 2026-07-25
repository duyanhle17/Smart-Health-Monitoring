FROM node:20-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

# The public dashboard must not run the Vite development server. A static
# production bundle avoids HMR/cache races that can leave a browser on a blank
# page during deploys; nginx also owns the API and Socket.IO reverse proxy.
FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 5173
