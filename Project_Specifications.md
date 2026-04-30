# Project Summary: Advanced Distributed Object Store with Integrity

## Topic
This project implements a **high-availability distributed object store with cryptographic integrity** over an erasure-coded storage backend. The system is designed to provide maximum fault tolerance and storage efficiency through custom mathematical engines and geo-aware placement strategies.

## Key Architectural Enhancements

### 1. Custom Reed-Solomon Engine
Unlike standard replication, this system implements **Generalized Reed-Solomon Erasure Coding** from scratch. Using Vandermonde matrices and Gaussian Elimination over Galois Fields ($GF(2^8)$), files are shredded into $n$ fragments. The system can reconstruct the original file from any $k$ fragments, allowing for a configurable balance between storage overhead and fault tolerance.

### 2. Merkle-Style Deduplication
To optimize storage across the cluster, the Coordinator employs content-addressable storage logic. Every file is hashed (SHA-256) before processing. If multiple users upload the same content under different filenames, the system only stores the data fragments once, creating lightweight virtual pointers in the manifest.

### 3. Geo-Aware Topology Placement
The system simulates real-world cloud infrastructure by assigning storage nodes to distinct **Availability Zones**. The placement engine ensures that fragments of a single file are distributed across as many zones as possible, ensuring data availability even during a complete regional data-center failure.

### 4. Active Read-Repair (Self-Healing)
The system is proactive. During every download, the Integrity Layer verifies fragment hashes. If a node returns corrupted data (bit-rot) or is offline, the Coordinator automatically:
1. Reconstructs the file using surviving parity/data fragments.
2. Spawns a background worker to re-encode the missing fragment.
3. Silently migrates the repaired data to a healthy node in the cluster.

### 5. High-Performance Utilitarian Dashboard
The user interface is designed for system administrators and engineers. Inspired by laboratory dashboards and terminal interfaces, it provides real-time visualization of the **Cluster Topology**, geographic distribution, and vault health.

## Core Architecture
- **Coordinator**: The stateless brain of the cluster. Handles deduplication, Reed-Solomon math, zone-aware routing, and background healing.
- **Storage Nodes**: Simple, high-concurrency binary storage services.
- **Content Manifest**: A SQLite-backed transactional index mapping file names and content hashes to distributed fragments.

## Main System Goals
1. **Zero Data Loss**: Survive up to $n - k$ simultaneous node failures.
2. **Storage Optimization**: Minimize footprint via Deduplication and Erasure Coding ($k/n$ ratio).
3. **Integrity Assurance**: Cryptographically detect and automatically repair bit-rot or malicious tampering.
4. **Elastic Scaling**: Seamlessly scale the cluster size from 3 to 256 nodes using the deployment engine.

## Demo Scenario
1. **Dynamic Scaling**: Run `make cluster nodes=6` to provision a custom cluster.
2. **Multi-Zone Upload**: Upload a file and observe fragments spreading across `us-east-1a`, `us-east-1b`, etc.
3. **Simulated Blackout**: Toggle multiple nodes to "OFFLINE" in the Dashboard.
4. **Resilient Retrieval**: Download the file. Observe it downloading successfully and the dashboard showing the "Healing" process reviving the missing chunks.
5. **Deduplication Test**: Upload the same large file twice; observe the second upload completing instantly without new fragments being created.
