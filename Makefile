.PHONY: help
help:
	@echo "=== SecStore Distributed Object Store ==="
	@echo ""
	@echo "  CLUSTER COMMANDS:"
	@echo "    make cluster nodes=N    - Generate config for N nodes (min 3)"
	@echo "    make build              - Build and start cluster (fresh start)"
	@echo "    make up                - Start existing cluster (no rebuild)"
	@echo "    make down              - Stop all containers"
	@echo "    make clean             - Stop + remove DB and cache"
	@echo ""
	@echo "  MONITORING:"
	@echo "    make status            - Show cluster/node/file status"
	@echo "    make logs             - Stream coordinator logs"
	@echo "    make logs-heal        - Watch REPAIR/UPLOAD/DELETE events"
	@echo ""
	@echo "  DEMO COMMANDS:"
	@echo "    make demo-seed         - Re-seed testfile1 + testfile2"
	@echo "    make demo-kill-node    - Toggle a random node OFFLINE"
	@echo "    make demo-upload       - Upload Project_Specifications.md"
	@echo "    make demo-download     - Download /demo/spec.md"
	@echo "    make demo-corrupt      - Corrupt Node 3's chunks"
	@echo ""
	@echo "  ACCESS URLs:"
	@echo "    http://localhost:8000/ui/        - Web Dashboard"
	@echo "    http://localhost:8000/list/       - File list API"
	@echo "    http://localhost:8000/docs      - Swagger API docs"
	@echo ""
	@echo "  For WebSocket terminal: connect to ws://localhost:8000/ws/stream"
	@echo ""

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

logs-heal:
	@echo "Watching heal/repair logs..."
	docker logs sec-dist-proj-coordinator-1 -f | grep -E "(REPAIR|UPLOAD|DELETE|TOPOLOGY)"

status:
	@echo "=== Cluster Status ==="
	@docker compose ps --format "table {{.Name}}\t{{.Status}}"
	@echo ""
	@echo "=== Files in Vault ==="
	@curl -s http://localhost:8000/list/ | python3 -m json.tool 2>/dev/null || echo "Coordinator not responding"
	@echo ""
	@echo "=== Node Metrics ==="
	@curl -s http://localhost:8000/admin/topology | python3 -c "import json,sys; t=json.load(sys.stdin); print('Nodes:', len(t)); [print(f'  {k}: active={v[\"active\"]}, chunks={len(v.get(\"chunks\",[]))}') for k,v in t.items()]"

demo-seed:
	@echo "Seeding test files..."
	@curl -s -X POST -F "file=@coordinator/testfile1.json" -F "custom_filename=testfile1.json" -F "k=2" -F "n=3" http://localhost:8000/upload/
	@curl -s -X POST -F "file=@coordinator/testfile2.json" -F "custom_filename=testfile2.json" -F "k=2" -F "n=3" http://localhost:8000/upload/
	@echo "Done. Files:"
	@curl -s http://localhost:8000/list/ | python3 -m json.tool

demo-kill-node:
	@echo "Killing random node..."
	@NODE=$$(curl -s http://localhost:8000/admin/topology | python3 -c "import json,sys; t=list(json.load(sys.stdin).keys()); print(t[0])") && \
	curl -s -X POST -H "Content-Type: application/json" -d "{\"node_url\": \"$$NODE\"}" http://localhost:8000/admin/topology/toggle && \
	echo "Killed $$NODE"

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
