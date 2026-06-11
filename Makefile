PYTHON ?= python3
VENV ?= .venv
PORT ?= 8765
HOST ?= 127.0.0.1
APP_URL := http://$(HOST):$(PORT)

.PHONY: setup dev test smoke docker-build docker-up docker-down status

setup:
	$(PYTHON) -m venv $(VENV)
	$(VENV)/bin/python -m pip install --upgrade pip
	$(VENV)/bin/python -m pip install -r requirements.txt

dev:
	HOST=$(HOST) PORT=$(PORT) $(VENV)/bin/python backend/app.py

test:
	node --check frontend/src/app.js
	$(VENV)/bin/python -m compileall backend tests
	$(VENV)/bin/python -m unittest discover -v

smoke:
	@echo "Checking $(APP_URL)/api/health"
	@curl -fsS "$(APP_URL)/api/health" | grep '"app_name": "NPA Agent"'
	@echo "NPA Agent health check passed: $(APP_URL)"

docker-build:
	docker compose build

docker-up:
	docker compose up --build

docker-down:
	docker compose down

status:
	git status --short --ignored
