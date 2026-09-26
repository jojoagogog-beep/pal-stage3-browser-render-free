FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=10000
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    chromium ca-certificates fonts-liberation curl \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py stage3_send_ready_worker_v1.py candidate_route_worker_v1.py v9_send_worker.py v6_v9_send_worker.py browser_slots_v7.py local_ledger_v7.py safety_contract_v6.py ./
EXPOSE 10000
CMD ["gunicorn","-w","1","--worker-class","gthread","--threads","4","-b","0.0.0.0:10000","--timeout","600","app:app"]
