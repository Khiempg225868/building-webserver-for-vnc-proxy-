FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY  vnc_proxy.py .
COPY noVNC ./noVNC/


EXPOSE 5001
EXPOSE 6081
EXPOSE 8081

CMD ["/bin/sh", "-c", "(cd /app/noVNC && python3 -m http.server 8081) & python3 /app/vnc_proxy.py"]```