.PHONY: up down logs ps migrate test shell psql redis-cli

up:
	docker-compose up -d --build

down:
	docker-compose down

logs:
	docker-compose logs -f

ps:
	docker-compose ps

migrate:
	docker-compose exec backend alembic upgrade head

test:
	docker-compose exec backend pytest

shell:
	docker-compose exec backend bash

psql:
	docker-compose exec postgres psql -U $(POSTGRES_USER) -d $(POSTGRES_DB)

redis-cli:
	docker-compose exec redis redis-cli
