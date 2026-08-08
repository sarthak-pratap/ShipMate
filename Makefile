.PHONY: help infra api worker web test cli

help:
	@echo "make infra   # start local postgres + valkey (docker compose)"
	@echo "make api     # run FastAPI on :8000"
	@echo "make worker  # run the background worker"
	@echo "make web     # run the Vite dev server on :3000"
	@echo "make test    # run the python test suite"
	@echo "make cli     # demo the generator on the sample compose file"

infra:
	docker compose up -d

api:
	cd api && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

worker:
	cd worker && python worker.py

web:
	cd web && npm install && npm run dev

test:
	cd api && python -m pytest tests/ -q

cli:
	cd api && python shipmate_cli.py compose ../examples/taskboard-compose.yml
