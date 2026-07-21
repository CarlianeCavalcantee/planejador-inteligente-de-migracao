.PHONY: install lint fmt test test-cov scan clean

install:
	pip install -r requirements.txt -r requirements-dev.txt

lint:
	ruff check .
	mypy core/

fmt:
	ruff format .
	ruff check --fix .

test:
	pytest tests/

test-cov:
	pytest tests/ --cov=core --cov-report=term-missing

scan:
	python scanner.py

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	rm -f impacto_cnpj.checkpoint.json
