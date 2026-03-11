.PHONY: build up down logs restart shell

build:
	docker compose build

up:
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f --tail=100

restart:
	docker compose restart

shell:
	docker compose exec support-bot bash
