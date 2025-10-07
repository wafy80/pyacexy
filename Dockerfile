FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY pyacexy/ ./pyacexy/
COPY setup.py README.md ./

RUN pip install --no-cache-dir -e .

EXPOSE 8080

CMD ["pyacexy"]
