.PHONY: install test lint clean build docker-build

install:
	pip install -e .

test:
	pytest tests/ -v

lint:
	ruff check kubbernetd/

clean:
	rm -rf dist/ build/ *.egg-info/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

build:
	pip install build
	python -m build

docker-build:
	docker build -t kubbernetd/operator:latest -f Dockerfile .