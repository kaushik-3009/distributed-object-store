from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import StreamingResponse
import httpx
import os
import uuid
import sqlite3
import io
import hashlib
from erasure_coding import ReedSolomon
from fastapi.staticfiles import StaticFiles

app = FastAPI(title="Coordinator Service")

# Mount the static directory to serve our web UI
app.mount("/ui", StaticFiles(directory="/app/static", html=True), name="static")

NODE_URLS = os.getenv("NODE_URLS", "http://node1:8000,http://node2:8000,http://node3:8000").split(",")
DB_FILE = "/app/coordinator.db"
rs = ReedSolomon(k=2, n=3)

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    # We added hash columns to store the cryptographic fingerprints
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS files (
            filename TEXT PRIMARY KEY,
            file_id TEXT NOT NULL,
            version_id TEXT NOT NULL,
            original_size INTEGER NOT NULL,
            padding_len INTEGER NOT NULL,
            hash_0 TEXT NOT NULL,
            hash_1 TEXT NOT NULL,
            hash_2 TEXT NOT NULL
        )
    ''')
    conn.commit()
    conn.close()

init_db()

def get_hash(data: bytes) -> str:
    """Returns the SHA-256 fingerprint of the data."""
    return hashlib.sha256(data).hexdigest()

@app.post("/upload/")
async def upload_file(file: UploadFile = File(...), custom_filename: str = None):
    # If a custom filename (like /photos/cat.jpg) is provided, use that.
    filename = custom_filename if custom_filename else file.filename
    file_bytes = await file.read()
    original_size = len(file_bytes)
    
    fragments, padding_len = rs.encode(file_bytes)
    file_id = str(uuid.uuid4())
    version_id = str(uuid.uuid4()) # To prevent mix-and-match attacks
    
    # 1. HASHING: Take a fingerprint of each fragment
    hashes = [get_hash(f) for f in fragments]
    
    # 2. DISTRIBUTE
    async with httpx.AsyncClient() as client:
        for i, fragment in enumerate(fragments):
            node_url = NODE_URLS[i]
            chunk_id = f"{file_id}_{version_id}_{i}"
            files = {'file': (chunk_id, fragment)}
            await client.post(f"{node_url}/upload/{chunk_id}", files=files, timeout=5.0)

    # 3. SECURE METADATA: Save the fingerprints securely in the database
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        REPLACE INTO files (filename, file_id, version_id, original_size, padding_len, hash_0, hash_1, hash_2) 
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (filename, file_id, version_id, original_size, padding_len, hashes[0], hashes[1], hashes[2]))
    conn.commit()
    conn.close()

    return {"message": "Secured, encoded, and distributed", "filename": filename}

@app.get("/list/")
async def list_files(prefix: str = ""):
    """Lists all files, optionally filtering by a directory prefix."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT filename, original_size FROM files WHERE filename LIKE ?', (f"{prefix}%",))
    rows = cursor.fetchall()
    conn.close()
    return [{"filename": row[0], "size_bytes": row[1]} for row in rows]

@app.get("/download/{filename:path}")
async def download_file(filename: str):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT file_id, version_id, original_size, padding_len, hash_0, hash_1, hash_2 FROM files WHERE filename = ?', (filename,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        raise HTTPException(status_code=404, detail="File not found")
    
    file_id, version_id, original_size, padding_len = row[0:4]
    expected_hashes = {0: row[4], 1: row[5], 2: row[6]}
    
    retrieved_fragments = {}

    # 1. GATHER AND VERIFY: Download and check fingerprints
    async with httpx.AsyncClient() as client:
        for i, node_url in enumerate(NODE_URLS):
            try:
                chunk_id = f"{file_id}_{version_id}_{i}"
                response = await client.get(f"{node_url}/download/{chunk_id}", timeout=2.0)
                
                if response.status_code == 200:
                    downloaded_data = response.content
                    downloaded_hash = get_hash(downloaded_data)
                    
                    # INTEGRITY CHECK: Does the downloaded chunk match our saved fingerprint?
                    if downloaded_hash == expected_hashes[i]:
                        retrieved_fragments[i] = downloaded_data
                        print(f"Fragment {i} verified successfully.")
                    else:
                        print(f"WARNING: Fragment {i} from {node_url} failed integrity check! Discarding.")
            except httpx.RequestError:
                print(f"Node {node_url} unavailable.")
                continue

    # 2. DECODE: We need at least 2 VERIFIED fragments to proceed
    if len(retrieved_fragments) < 2:
        raise HTTPException(status_code=500, detail="Not enough valid fragments to securely reconstruct file. Data may be lost or under attack.")

    reconstructed_data = rs.decode(retrieved_fragments, original_size, padding_len)
    
    return StreamingResponse(
        io.BytesIO(reconstructed_data), 
        media_type="application/octet-stream", 
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )
@app.post("/admin/corrupt/{node_id}/{filename:path}")
async def corrupt_file(node_id: int, filename: str):
    """
    Demo/Admin Endpoint: Instructs a specific node to corrupt its chunk for this file.
    This simulates bit-rot or a hacker modifying the file on the node's hard drive.
    """
    if node_id not in [1, 2, 3]:
        raise HTTPException(status_code=400, detail="Invalid node_id. Must be 1, 2, or 3.")

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT file_id, version_id FROM files WHERE filename = ?', (filename,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        raise HTTPException(status_code=404, detail="File not found")
    
    file_id, version_id = row
    
    # Calculate the internal chunk name based on our encoding logic.
    # Node 1 gets chunk 0, Node 2 gets chunk 1, Node 3 gets chunk 2
    chunk_index = node_id - 1
    chunk_id = f"{file_id}_{version_id}_{chunk_index}"
    node_url = NODE_URLS[chunk_index]

    # Ask the specific node to corrupt its chunk
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(f"{node_url}/corrupt/{chunk_id}", timeout=2.0)
            if response.status_code == 200:
                return {"message": f"Successfully instructed Node {node_id} to corrupt chunk for '{filename}'"}
            else:
                raise HTTPException(status_code=500, detail=f"Node {node_id} returned an error: {response.text}")
        except httpx.RequestError as e:
            raise HTTPException(status_code=500, detail=f"Could not reach Node {node_id}: {str(e)}")
