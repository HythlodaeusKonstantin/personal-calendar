FROM python:3.11-slim

WORKDIR /app

# Устанавливаем distutils для pip
RUN apt-get update && \
    apt-get install -y python3-distutils && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8443

CMD ["python", "run_ssl.py"] 