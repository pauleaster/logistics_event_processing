FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
	PYTHONUNBUFFERED=1

WORKDIR /workspace

COPY requirements.txt /workspace/requirements.txt

RUN pip install --no-cache-dir -r /workspace/requirements.txt

COPY . /workspace

CMD ["python", "-m", "app.main"]
