.PHONY: up down build test demo clean cluster

cluster:
	@echo "Configuring cluster for $(nodes) nodes..."
	python deploy_cluster.py --nodes $(nodes)

up:
	@echo "Starting distributed object store cluster..."
	docker compose up -d

build:
	@echo "Building docker images..."
	docker compose up --build -d

down:
	@echo "Shutting down cluster..."
	docker compose down

test:
	@echo "Running integration tests..."
	python test_suite.py

logs:
	docker compose logs -f coordinator

demo-upload:
	@echo "Uploading test file..."
	python client.py upload ./Project_Specifications.md /demo/spec.md
	python client.py list

demo-corrupt:
	@echo "Corrupting Node 3..."
	python client.py corrupt 3 /demo/spec.md

demo-download:
	@echo "Downloading file (will reconstruct if corrupted)..."
	python client.py download /demo/spec.md ./demo_download.md
	@echo "Success! Check demo_download.md"

clean: down
	@echo "Cleaning up local artifacts..."
	rm -f demo_download.md
	rm -rf __pycache__ coordinator/__pycache__ node/__pycache__
	rm -f coordinator/coordinator.db
	rm -rf node/data/*
