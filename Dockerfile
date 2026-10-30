# Dockerfile Unificado para Render / Railway / Fly.io
# Compila el Frontend Astro y sirve todo (Astro + FastAPI + 16 Tablas + PDF) en $PORT
FROM node:22-alpine AS frontend-builder
WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY backend ./backend
COPY database ./database
COPY --from=frontend-builder /app/dist ./dist
ENV PORT=8000
EXPOSE 8000
CMD ["sh", "-c", "python -m uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
