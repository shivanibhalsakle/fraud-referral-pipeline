FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY referral_pipeline.py profile_data.py entrypoint.sh ./
RUN chmod +x entrypoint.sh


VOLUME ["/app/data", "/app/reports"]

ENTRYPOINT ["./entrypoint.sh"]
