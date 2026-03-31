# Session 03: 24 March 2026

## Accomplishments
- Implemented Phase 2: Custom Erasure Coding (Reed-Solomon).
- Created `erasure_coding.py` with GF(2^8) math for manual encoding/decoding.
- Updated Coordinator to split files into 3 fragments (2 data, 1 parity).
- Distributed fragments across 3 storage nodes (one per node).
- Updated Coordinator download logic to reconstruct files even if 1 node is missing.

## Observations
- The storage overhead is now exactly 1.5x (e.g., a 100MB file takes 150MB total).
- The system survives 1 node failure. If 2 nodes are down, it fails as expected (needs k=2).
- The math uses Galois Field XOR for addition/subtraction.

## Things to Fix Next Time
- Currently, the system assumes fragments are always correct. If a fragment is corrupted (bit-rot or malicious), the Reed-Solomon math will output garbage without warning.
- Phase 3 will introduce the **Integrity & Consistency Protocol** to detect corrupted fragments before reconstruction.
