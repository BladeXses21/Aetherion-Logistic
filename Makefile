.PHONY: up down logs test migrate lint shell seed-cities

up:
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f

test:
	docker compose exec api-gateway pytest tests/ -v
	docker compose exec agent-service pytest tests/ -v
	docker compose exec lardi-connector pytest tests/ -v
	docker compose exec auth-worker pytest tests/ -v

migrate:
	docker compose exec api-gateway alembic upgrade head

lint:
	ruff check . && ruff format --check .

shell:
	docker compose exec $(s) bash

seed-cities:
	python api-gateway/scripts/import_cities_v1.py
