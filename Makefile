.PHONY: help doctor bootstrap serve ui worker eval test test-fast clean docker-up docker-down docker-logs docker-build docker-test

PYTHON := python3

help:
	@echo "========================================================================"
	@echo "ADAM — Native Local Development Commands (MacBook Air 8GB Optimized)"
	@echo "========================================================================"
	@echo "  make doctor      Check system memory, headroom, disk, and engines"
	@echo "  make bootstrap   Seed mini public pilot corpus in SQLite (< 2 sec)"
	@echo "  make serve       Start FastAPI backend API server on port 8000"
	@echo "  make ui          Start Next.js frontend UI on port 3000"
	@echo "  make worker      Run native background OCR worker queue"
	@echo "  make eval        Run offline pilot gate gold set benchmark (215 queries)"
	@echo "  make test        Run full automated test suite with pytest"
	@echo "  make clean       Clean temporary files and enforce storage cache cap"
	@echo "  make docker-up   Start editable Docker development stack"
	@echo "  make docker-down Stop Docker stack (keeps named volumes)"
	@echo "  make docker-logs Follow API and UI Docker logs"
	@echo "  make docker-build Rebuild Docker development images"
	@echo "  make docker-test Run the backend test suite in Docker"
	@echo "========================================================================"

doctor:
	adam dev doctor

bootstrap:
	adam dev bootstrap

serve:
	adam serve

ui:
	cd ui && npm run dev

worker:
	adam worker ocr

eval:
	adam eval

test:
	pytest -v

test-fast:
	pytest -q --tb=short

clean:
	adam dev cache-clean --cap-mb 2048
	rm -rf .pytest_cache ui/.next

docker-up:
	docker compose up --build

docker-down:
	docker compose down

docker-logs:
	docker compose logs -f api ui

docker-build:
	docker compose build --no-cache

docker-test:
	docker compose run --rm api pytest -q
