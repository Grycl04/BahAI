FROM python:3.12.8-slim

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --upgrade pip && \
    pip install "numpy<2" && \
    pip install "scikit-learn==1.5.0" && \
    pip install -r requirements.txt

COPY . .

WORKDIR /app/backend

EXPOSE 10000

CMD ["gunicorn", "--bind", "0.0.0.0:10000", "chatbot_backend:app"]
