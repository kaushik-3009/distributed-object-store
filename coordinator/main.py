from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import StreamingResponse
import httpx
import os
import uuid
import sqlite3
import io
from erasure_coding import ReedSolomon

app = FastAPI(title="Coordinator Service")

# --- Configuration ---
NODE_URLS = os.getenv("NODE_URLS", "http://node1:8000,http://node2:8000,http://node3:8000").split(",")
DB_FILE = "/app/coordinator.db"

# K=2, N=3 setup
rs = ReedSolomon(k=2, n=3)

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS files (
            filename TEXT PRIMARY KEY,
            file_id TEXT NOT NULL,
            original_size INTEGER NOT NULL,
            padding_len INTEGER NOT NULL
        )
    ''')
    conn.commit()
    conn.close()

init_db()

@app.post("/upload/")
async def upload_file(file: UploadFile = File(...)):
    file_bytes = await file.read()
    original_size = len(file_bytes)
    
    # 1. ERASURE CODING: Split into 3 fragments
    fragments, padding_len = rs.encode(file_bytes)
    file_id = str(uuid.uuid4())
    
    # 2. DISTRIBUTE: Send each fragment to exactly one node
    # Fragment 0 -> Node 1, Fragment 1 -> Node 2, Fragment 2 -> Node 3
    async with httpx.AsyncClient() as client:
        for i, fragment in enumerate(fragments):
            node_url = NODE_URLS[i]
            # Use a unique internal name for the chunk: fileID_index
            chunk_id = f"{file_id}_{i}"
            files = {'file': (chunk_id, fragment)}
            await client.post(f"{node_url}/upload/{chunk_id}", files=files, timeout=5.0)

    # 3. METADATA
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        REPLACE INTO files (filename, file_id, original_size, padding_len) 
        VALUES (?, ?, ?, ?)
    ''', (file.filename, file_id, original_size, padding_len))
    conn.commit()
    conn.close()

    return {"message": "Erasure encoded and distributed", "filename": file.filename}

@app.get("/download/{filename}")
async def download_file(filename: str):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT file_id, original_size, padding_len FROM files WHERE filename = ?', (filename,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        raise HTTPException(status_code=404, detail="File not found")
    
    file_id, original_size, padding_len = row
    retrieved_fragments = {}

    # 1. GATHER: Try to get at least K=2 fragments from the nodes
    async with httpx.AsyncClient() as client:
        for i, node_url in enumerate(NODE_URLS):
            try:
                chunk_id = f"{file_id}_{i}"
                response = await client.get(f"{node_url}/download/{chunk_id}", timeout=2.0)
                if response.status_code == 200:
                    retrieved_fragments[i] = response.content
            except httpx.RequestError:
                continue

    # 2. DECODE: If we have enough, reconstruct the original bytes
    if len(retrieved_fragments) < 2:
        raise HTTPException(status_code=500, detail="Not enough fragments available to reconstruct file")

    reconstructed_data = rs.decode(retrieved_fragments, original_size, padding_len)
    
    return StreamingResponse(
        io.BytesIO(reconstructed_data), 
        media_type="application/octet-stream", 
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )
