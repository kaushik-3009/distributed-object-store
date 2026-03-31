# Session 01: 24 March 2026

## Accomplishments
- Set up the GitHub repository structure and documentation folders.
- Scaffolded the Python FastAPI apps (`coordinator/` and `node/`).
- Created basic `/health` endpoints.
- Created a local `docker-compose.yml` to spin up 1 Coordinator and 3 Nodes.

## Observations
- Decided on **Reed-Solomon** for erasure coding.
- Decided to use **SQLite** for the Coordinator to store metadata persistently without adding extra database containers.
- Decided on a **Versioned Manifest** approach for the Integrity Layer to prevent mix-and-match attacks.
- Using a `k=2, n=3` default setup for initial testing.

## Things to Fix Next Time
- Need to implement Phase 1: Basic Replication (`PUT` and `GET` without erasure coding yet).
