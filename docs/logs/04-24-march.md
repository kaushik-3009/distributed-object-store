# Session 04: 24 March 2026

## Accomplishments
- Implemented Phase 3: Integrity & Consistency Protocol.
- Updated the Coordinator database to store `version_id` and SHA-256 hashes (`hash_0`, `hash_1`, `hash_2`) for every chunk during upload.
- Updated the Coordinator download process to fingerprint every downloaded chunk and compare it against the database.
- Added a `POST /corrupt/{file_id}` admin endpoint to the storage nodes to simulate a hacker attack or disk rot.

## Observations
- The Mix-and-Match attack is now impossible. If a chunk's hash does not match, the Coordinator drops the chunk entirely and attempts to reconstruct the file using the remaining healthy fragments.
- A file is only reconstructed if we have $k=2$ *cryptographically verified* fragments.

## Things to Fix Next Time
- The local prototype is fully featured.
- Phase 4 involves moving this system off the local machine and into the Cloud (AWS via Terraform).
