# Auto-Voorspeller: één container met de API, het model en de gebouwde frontend.
#   docker build -t auto-voorspeller .
#   docker run -p 8000:8000 auto-voorspeller      -> http://localhost:8000

# Stap 1: frontend bouwen
FROM node:20-slim AS frontend
WORKDIR /frontend
COPY app/frontend/package.json app/frontend/package-lock.json ./
RUN npm ci
COPY app/frontend/ ./
RUN npm run build

# Stap 2: API met model en data
FROM python:3.12-slim
WORKDIR /app
COPY app/api/requirements.txt app/api/requirements.txt
RUN pip install --no-cache-dir -r app/api/requirements.txt
COPY app/api app/api
COPY model-building/model_catboost.cbm model-building/marktfactor.csv model-building/model_meta.json \
     model-building/cpi.csv model-building/
COPY model-building/app_data model-building/app_data
COPY --from=frontend /frontend/dist app/frontend/dist

# Hostingdiensten geven de poort vaak mee via $PORT
ENV PORT=8000
EXPOSE 8000
CMD uvicorn main:app --app-dir app/api --host 0.0.0.0 --port ${PORT}
