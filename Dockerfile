FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV HOST=0.0.0.0
ENV PORT=8765

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend ./backend
COPY frontend ./frontend
COPY templates ./templates
COPY samples ./samples
COPY docs ./docs
RUN mkdir -p \
    data/audit \
    data/company_history \
    data/knowledge \
    data/legal_docs \
    data/private_skills \
    data/reports \
    data/secrets \
    data/uploads

EXPOSE 8765

CMD ["python", "backend/app.py"]
