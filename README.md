# Distributed Object Store with Integrity

A fault-tolerant distributed storage system that splits files across multiple nodes using custom Reed-Solomon erasure coding (k=2, n=3) and verifies fragment integrity with SHA-256 hashes to detect corruption and prevent "mix-and-match" attacks during reconstruction.

You can lose 1 out of 3 storage nodes and the file still comes back. You can corrupt a fragment on a surviving node and the system catches it before it ever touches the decoder.

## How It Works

### Upload Flow

```mermaid
sequenceDiagram
    participant C as Client
    participant Coord as Coordinator
    participant EC as Reed-Solomon Encoder
    participant N1 as Node 1
    participant N2 as Node 2
    participant N3 as Node 3

    C->>Coord: POST /upload/ (file)
    Coord->>EC: encode(data, k=2, n=3)
    EC-->>Coord: [D0, D1, P0] + padding_len
    Coord->>Coord: SHA-256 hash each fragment
    Coord->>Coord: Store manifest in SQLite
    par distribute fragments
        Coord->>N1: POST /upload/{file_id} (D0)
        Coord->>N2: POST /upload/{file_id} (D1)
        Coord->>N3: POST /upload/{file_id} (P0)
    end
    N1-->>Coord: 200 OK
    N2-->>Coord: 200 OK
    N3-->>Coord: 200 OK
    Coord-->>C: 200 OK
```

### Download Flow (with corruption detection)

```mermaid
sequenceDiagram
    participant C as Client
    participant Coord as Coordinator
    participant N1 as Node 1
    participant N2 as Node 2
    participant N3 as Node 3

    C->>Coord: GET /download/{filename}
    Coord->>Coord: Lookup manifest (version, hashes)
    par fetch fragments
        Coord->>N1: GET /download/{file_id}
        Coord->>N2: GET /download/{file_id}
        Coord->>N3: GET /download/{file_id}
    end
    N1-->>Coord: D0 bytes
    N2-->>Coord: D1 bytes (CORRUPTED)
    N3-->>Coord: P0 bytes
    Coord->>Coord: Verify SHA-256(D0) == hash_0 ✓
    Coord->>Coord: Verify SHA-256(D1) == hash_1 ✗ REJECT
    Coord->>Coord: Verify SHA-256(P0) == hash_2 ✓
    Coord->>Coord: decode({D0, P0}) → reconstruct D1 via XOR
    Coord-->>C: StreamingResponse (original file)
```

### Erasure Coding

The encoder splits each file into 2 data chunks and computes 1 parity chunk. In GF(2^8), addition is XOR, so parity = D0 ^ D1 byte-by-byte.

```mermaid
flowchart TB
    subgraph encode["Encode"]
        A["Original File<br/><i>any size</i>"] --> B["Pad to multiple of k=2"]
        B --> C["Split into 2 chunks"]
        C --> D0["D0<br/>first half"]
        C --> D1["D1<br/>second half"]
        D0 --> P0["P0 = D0 ⊕ D1<br/><i>XOR byte-by-byte</i>"]
        D1 --> P0
    end

    subgraph decode["Reconstruct (any 2 of 3)"]
        direction LR
        R1["D0 + D1"] --> O1["direct concat"]
        R2["D0 + P0"] --> O2["D1 = P0 ⊕ D0"]
        R3["D1 + P0"] --> O3["D0 = P0 ⊕ D1"]
    end

    encode ~~~ decode
```

The Galois Field implementation uses primitive polynomial `x^8 + x^4 + x^3 + x^2 + 1` (0x11D) with precomputed log/antilog tables for fast arithmetic. This isn't just a library wrapping `pyreedsolomon` -- it's the actual field math built from scratch (`coordinator/erasure_coding.py`).

### Integrity Protocol

The problem this solves: if a file gets updated (v1 → v2), a stale node might still hold a v1 fragment. Blindly mixing fragments from different versions produces garbage.

```mermaid
flowchart TB
    subgraph manifest["Versioned Manifest (SQLite)"]
        direction LR
        M["filename: secret.txt<br/>version: abc-123<br/>hash_0: a3f2c1...<br/>hash_1: 7b9e0d...<br/>hash_2: f1a8c3..."]
    end

    subgraph verify["Download Verification Loop"]
        direction TB
        F["Fetch fragment from node"] --> H["Compute SHA-256(fragment)"]
        H --> CMP{"hash == manifest entry?"}
        CMP -->|Yes| ACCEPT["Accept fragment ✓"]
        CMP -->|No| REJECT["Reject fragment ✗<br/><i>log warning, try parity</i>"]
    end

    manifest --> verify
```

Every fragment is cryptographically bound to a specific file version. A corrupted or stale fragment gets rejected before it ever reaches the decoder.

## Quick Start

```bash
# start the cluster (1 coordinator + 3 storage nodes)
docker-compose up --build

# in another terminal, upload a file
python client.py upload ./myfile.txt /docs/myfile.txt

# list stored files
python client.py list

# download it back
python client.py download /docs/myfile.txt ./downloaded.txt

# simulate node corruption (corrupts fragment on node 3)
python client.py corrupt 3 /docs/myfile.txt

# download again -- system detects corruption and reconstructs from remaining nodes
python client.py download /docs/myfile.txt ./downloaded_v2.txt
```

Or open `http://localhost:8000/ui/` for the web dashboard.

## Project Structure

```
sec-dist-proj/
├── coordinator/
│   ├── main.py                 # FastAPI service: upload, download, list, admin endpoints
│   ├── erasure_coding.py       # Custom Reed-Solomon over GF(2^8), k=2, n=3
│   ├── static/index.html       # Web dashboard
│   ├── Dockerfile
│   └── requirements.txt
├── node/
│   ├── main.py                 # FastAPI service: fragment storage (store/retrieve/delete/corrupt)
│   ├── Dockerfile
│   └── requirements.txt
├── client.py                   # CLI client (upload, download, list, corrupt)
├── test_suite.py               # Integration tests (healthy, single-corruption, double-corruption)
├── terraform/main.tf           # AWS infra (VPC, EC2, ECR, SG)
├── docker-compose.yml          # Local orchestration

```

## API Reference

### Coordinator (port 8000)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/upload/` | Upload a file. Multipart form with `file` field. Optional `custom_filename` query param. |
| `GET` | `/download/{filename}` | Download a file. Fetches fragments, verifies hashes, decodes, streams back. |
| `GET` | `/list/` | List stored files. Optional `prefix` query param for filtering. |
| `POST` | `/admin/corrupt/{node_id}/{filename}` | Corrupt a fragment on a specific node (demo/testing). |
| `GET` | `/ui/` | Web dashboard. |

### Storage Nodes (port 8000 internally)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Health check. |
| `POST` | `/upload/{file_id}` | Store a fragment binary. |
| `GET` | `/download/{file_id}` | Retrieve a fragment binary. |
| `DELETE` | `/delete/{file_id}` | Delete a fragment. |
| `POST` | `/corrupt/{file_id}` | Append garbage bytes to simulate corruption. |

## Running the Tests

The integration tests require the Docker Compose stack to be running:

```bash
docker-compose up --build -d
python test_suite.py
```

Three tests:

| Test | What It Does | Expected Result |
|------|-------------|-----------------|
| `test_01_upload_and_download_healthy` | Upload then download with all nodes up | File matches original |
| `test_02_single_corruption_resilience` | Corrupt fragment on 1 node, then download | System recovers using parity, file matches |
| `test_03_double_corruption_failure` | Corrupt fragments on 2 nodes, then download | HTTP 500 -- not enough valid fragments |

## Infrastructure

Terraform config (`terraform/main.tf`) provisions a minimal AWS environment:

```mermaid
flowchart TB
    subgraph vpc["VPC (10.0.0.0/16)"]
        subgraph subnet["Public Subnet (10.0.1.0/24)"]
            subgraph ec2["EC2 t3.micro"]
                C["Coordinator<br/>:8000"]
                N1["Node 1<br/>:8001"]
                N2["Node 2<br/>:8002"]
                N3["Node 3<br/>:8003"]
            end
            SG["Security Group<br/>22 (SSH), 8000 (HTTP)"]
        end
    end

    ECR["ECR<br/>container images"]
    CW["CloudWatch<br/>log aggregation"]

    ECR --> ec2
    ec2 --> CW
```

All resources fit within the AWS Free Tier. Spin up for demos, tear down after:

```bash
cd terraform
terraform init
terraform plan
terraform apply
# ...demo...
terraform destroy
```

## Tech Stack

- **Python 3.10** / **FastAPI** / **Uvicorn** -- services
- **httpx** -- async HTTP between coordinator and nodes
- **SQLite** -- metadata and fragment hash manifest
- **Docker Compose** -- local orchestration
- **Terraform** -- AWS infrastructure as code
- **Vanilla HTML/CSS/JS** -- web dashboard (no framework overhead)

## License

Apache 2.0
