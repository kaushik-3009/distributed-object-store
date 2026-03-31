# System Architecture and Concepts

## Core Components
Our system consists of two primary services:

1. **Coordinator Service**
   - The central entry point for the client.
   - Responsible for accepting files, chunking them (erasure coding), and distributing the chunks to the nodes.
   - Maintains a **SQLite Database** to track metadata (file names, versions, which chunks are on which node, and the cryptographic hash of each chunk).
   - Responsible for fetching chunks during a download, verifying their hashes, and reconstructing the original file.

2. **Storage Nodes (3 instances)**
   - Dumb storage containers. 
   - They expose a simple API to save a file chunk and retrieve a file chunk.
   - They do *not* know anything about the larger file, only the chunks they store.

## The Problem: "Mix and Match" Attacks
If a file is updated (Version 1 -> Version 2), the chunks change. If a node goes offline during an update, it might still hold a Version 1 chunk. If the Coordinator blindly reconstructs a file using two Version 2 chunks and one Version 1 chunk, the resulting file will be garbage. 

## The Solution: Versioned Manifest (Integrity Protocol)
When the Coordinator saves a file, it creates a unique version ID (e.g., a timestamp or UUID) and hashes each individual chunk. The Coordinator's database maps:
`File Name -> Version ID -> [Chunk 1 Hash, Chunk 2 Hash, Chunk 3 Hash]`.

When reconstructing, the Coordinator requests chunks for a *specific version ID* and verifies the hash of each downloaded chunk before passing them to the decoder. If a hash doesn't match the manifest, the chunk is rejected, and the system attempts to reconstruct using parity chunks.
