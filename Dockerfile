FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN python db_sqlite.py

CMD ["python", "bot_sqlite.py"]
