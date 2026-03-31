# Session 02: 24 March 2026

## Accomplishments
- Implemented Phase 1: Basic Replication (No Erasure Coding yet).
- Created Node endpoints (`PUT /upload/{file_id}`, `GET /download/{file_id}`) to save physical files to disk.
- Created Coordinator endpoints (`POST /upload/`, `GET /download/{filename}`).
- Set up SQLite database in the Coordinator to map client filenames to internal UUIDs.

## Observations
- Right now, if I upload a 10MB file, it takes 30MB of storage overall because a full copy goes to all 3 nodes (Basic Replication).
- The Coordinator will successfully let us download a file as long as at least 1 out of the 3 nodes is still alive. This proves basic fault tolerance!

## Things to Fix Next Time
- The replication is inefficient space-wise.
- Next is Phase 2: Replace the full-file duplication with Custom Erasure Coding (Reed-Solomon) so we can split a 10MB file into smaller chunks instead.
