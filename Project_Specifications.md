# Project Summary: Distributed Object Store with Integrity

## Topic
This project implements a **distributed object store with integrity** over an erasure-coded storage backend. The goal is to build a fault-tolerant system where data is split across multiple servers, while strictly ensuring that corrupted or inconsistent fragments are detected before file reconstruction. 

## The Problem
In standard distributed storage, spreading data across multiple machines improves fault tolerance. However, this creates a security and consistency vulnerability: if fragments are corrupted by a faulty node, or if a client maliciously or accidentally mixes fragments from different versions of a file, the system might reconstruct invalid or inconsistent data. 

The core challenge is not just storing data redundantly, but verifying that the fragments used for reconstruction all cryptographically belong to the **same original object and version**.

## Core Architecture
We are building a distributed object store from the ground up, featuring:
- **Custom Erasure Coding**: We are implementing our own erasure coding logic to split files into \(n\) fragments (where \(k\) are required to reconstruct), rather than relying on a third-party library.
- **Integrity Layer**: A metadata verification system inspired by secure distributed storage research. This layer ensures that fragments are cryptographically bound to a specific object version, preventing "mix-and-match" attacks and detecting bit-rot.
- **Service Topology**: 
  - A **Coordinator** service that handles client uploads, executes the custom erasure coding, distributes fragments, and performs integrity checks during retrieval.
  - Multiple **Storage Nodes** that store the individual fragments and their associated metadata.
- **Filesystem Interface**: A thin layer on top of the object store that allows users to interact with the system using file paths and basic directory listing.

## Main System Goals
The completed prototype must successfully demonstrate:
1. **Fault Tolerance**: A file can be perfectly reconstructed even if \(n - k\) storage nodes are shut down.
2. **Integrity & Consistency**: Corrupted fragments are actively detected and rejected. The system refuses to reconstruct a file if it is fed mismatched fragments from different writes.
3. **Usability**: Users can easily upload and retrieve files through a simple API/CLI.

## Cloud Deployment Strategy (AWS & Terraform)
To demonstrate the system in a realistic but cost-effective cloud environment, we are utilizing a lightweight AWS stack designed to fit within the Free Tier, fully automated via Infrastructure as Code:

- **Terraform**: Used to automatically provision and manage all AWS resources (EC2, ECR, S3, CloudWatch log groups, and IAM roles). This ensures the infrastructure is reproducible, version-controlled, and can be easily spun up for demos and torn down immediately afterward to prevent unexpected costs.
- **Amazon EC2 (t3.micro)**: The core host for the project. A single EC2 instance will run the entire system using **Docker Compose** to orchestrate the Coordinator and the \(n\) Storage Nodes. This simulates a distributed network without the cost of provisioning 7 separate virtual machines.
- **Amazon ECR (Elastic Container Registry)**: Used to store and manage our custom Docker images for the Coordinator and Node services, allowing for clean, repeatable deployments to the EC2 instance.
- **Amazon CloudWatch**: Configured to ingest logs from our Docker containers. This provides a professional observability dashboard to monitor system health and demonstrate request traffic during the presentation.
- **Amazon S3**: Utilized as a low-cost holding area for demo files, test artifacts, and Terraform state backups.

## Demo Scenario
The final presentation will feature a live fault-injection simulation:
1. Use Terraform to spin up the AWS environment and deploy the containers.
2. Upload a file via the Coordinator.
3. Show the custom erasure coding splitting the file across the active Storage Nodes.
4. **Availability Test**: Kill 1-2 Storage Node containers and demonstrate successful file reconstruction.
5. **Integrity Test**: Intentionally corrupt a fragment on a surviving node. Demonstrate the system catching the invalid hash/metadata, rejecting the bad fragment, and still reconstructing the file using the remaining valid fragments.

---

# Execution Guide: Phase-by-Phase Implementation

**AI AGENT INSTRUCTIONS:** 
Do NOT "one-shot" this project. I am a student and I need to understand what is happening as we build it. You must work strictly phase-by-phase. After completing a phase, you must stop, explain what we just did in plain English, and ask me a checkpoint question to ensure I understand before moving to the next phase. 

## Documentation Workflow
Before writing any code, we must maintain a `docs/` folder with two subdirectories:
1. **`docs/logs/` (Session Logs):** 
   - Files must be named in the format `[session_number]-[dd]-[monthname].md` (e.g., `01-24-march.md`, `02-25-march.md`).
   - Each log must track: What we accomplished in this session, observations, and "things to fix next time".
2. **`docs/notes/` (System Concepts):** 
   - Running notes on the architecture, erasure coding math, AWS setup, and distributed system concepts. 
   - This is my study guide for revisions and interviews. Update these notes whenever we introduce a new concept.

## Development Phases

### Phase 0: Skeleton & Documentation
- Set up the GitHub repository, `docs/logs`, and `docs/notes`.
- Scaffold the Python FastAPI apps (`coordinator/` and `node/`).
- Create basic `/health` endpoints and a local `docker-compose.yml` to spin up 1 Coordinator and 3 Nodes.
- *Learning Focus*: Understanding FastAPI, Docker Compose, and the Coordinator-Node architecture.

### Phase 1: Basic Replication (No Erasure Coding)
- Implement `PUT` and `GET` endpoints where the Coordinator simply copies the entire file to all active Storage Nodes.
- Ensure end-to-end communication works.
- *Learning Focus*: Handling file streams, HTTP requests between microservices, and basic distributed storage IO.

### Phase 2: Custom Erasure Coding
- Remove basic replication.
- Implement a custom erasure coding module in Python (e.g., using basic XOR parity or Galois Fields) to split a file into \(n\) fragments where \(k\) can reconstruct it.
- Update `PUT` to encode files, and `GET` to pull \(k\) fragments and decode them.
- *Learning Focus*: The math behind erasure coding, what \(k\)-of-\(n\) means, and how reconstruction handles missing data.

### Phase 3: Integrity & Consistency Protocol
- Implement fragment hashing and metadata binding (the core of the paper).
- The Coordinator must verify each downloaded fragment's hash against the expected metadata before passing it to the decode function.
- Create an admin endpoint on the Node to intentionally corrupt a fragment.
- *Learning Focus*: Cryptographic hashes, metadata management, preventing "mix-and-match" vulnerabilities.

### Phase 4: Cloud Infrastructure (AWS + Terraform)
- Write Terraform scripts to provision the VPC, EC2 (t3.micro), ECR, IAM roles, and CloudWatch log groups.
- Push our Docker images to ECR.
- Deploy the Docker Compose stack onto the EC2 instance.
- *Learning Focus*: Infrastructure as Code (IaC), AWS networking, container registries, and centralized logging.

### Phase 5: Filesystem Layer & Polish
- Add a thin UI or CLI to upload/download files using "paths" (e.g., `/folder/file.txt`).
- Write the final demo script that executes the fault injection (killing nodes, corrupting fragments).
- *Learning Focus*: Translating flat object keys into a filesystem namespace, and presenting a technical demo.
