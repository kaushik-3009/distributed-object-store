import os
import io
import uuid
import json
import sqlite3
import hashlib
import random
from contextlib import asynccontextmanager

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
import httpx
from pydantic import BaseModel

from erasure_coding import ReedSolomon

# 1. Setup Global HTTP Client and Topology
http_client: httpx.AsyncClient = None

RAW_NODE_URLS = os.getenv(
    "NODE_URLS",
    "http://node1:8000,http://node2:8000,http://node3:8000,http://node4:8000,http://node5:8000"
).split(",")

CLUSTER_TOPOLOGY = {url: True for url in RAW_NODE_URLS}

@asynccontextmanager
async def lifespan(app: FastAPI):
    global http_client
    http_client = httpx.AsyncClient()
    yield
    await http_client.aclose()

app = FastAPI(title="Coordinator Service", lifespan=lifespan)

# Mount the static directory to serve our web UI
app.mount("/ui", StaticFiles(directory="/app/static", html=True), name="static")

DB_FILE = "/app/coordinator.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    # Recreate the table schema
    cursor.execute('DROP TABLE IF EXISTS files')
    cursor.execute('''
        CREATE TABLE files (
            filename TEXT PRIMARY KEY,
            file_id TEXT NOT NULL,
            version_id TEXT NOT NULL,
            original_size INTEGER NOT NULL,
            padding_len INTEGER NOT NULL,
            k INTEGER NOT NULL,
            n INTEGER NOT NULL,
            manifest TEXT NOT NULL
        )
    ''')
    conn.commit()
    conn.close()

init_db()

def get_hash(data: bytes) -> str:
    """Returns the SHA-256 fingerprint of the data."""
    return hashlib.sha256(data).hexdigest()

@app.post("/upload/")
async def upload_file(
    file: UploadFile = File(...), 
    custom_filename: str = Form(None), 
    k: int = Form(2), 
    n: int = Form(3)
):
    filename = custom_filename if custom_filename else file.filename
    file_bytes = await file.read()
    original_size = len(file_bytes)
    
    # Restrict file size to 20MB to prevent memory exhaustion
    if original_size > 20 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File exceeds 20MB maximum size limit.")
        
    rs = ReedSolomon()
    fragments, padding_len = rs.encode(file_bytes, k, n)
    file_id = str(uuid.uuid4())
    version_id = str(uuid.uuid4())
    
    hashes = [get_hash(f) for f in fragments]
    
    healthy_nodes = [url for url, is_active in CLUSTER_TOPOLOGY.items() if is_active]
    if len(healthy_nodes) < n:
        raise HTTPException(status_code=500, detail="Not enough healthy nodes in cluster topology.")
        
    selected_nodes = random.sample(healthy_nodes, n)
    manifest = {}

    for i, fragment in enumerate(fragments):
        node_url = selected_nodes[i]
        chunk_id = f"{file_id}_{version_id}_{i}"
        files = {'file': (chunk_id, fragment)}
        
        try:
            await http_client.post(f"{node_url}/upload/{chunk_id}", files=files, timeout=5.0)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to upload to node {node_url}: {e}")
            
        manifest[str(i)] = {"node": node_url, "hash": hashes[i]}

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        REPLACE INTO files (filename, file_id, version_id, original_size, padding_len, k, n, manifest) 
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (filename, file_id, version_id, original_size, padding_len, k, n, json.dumps(manifest)))
    conn.commit()
    conn.close()

    return {"message": "Secured, encoded, and distributed", "filename": filename}

@app.get("/list/")
async def list_files(prefix: str = ""):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT filename, original_size, k, n FROM files WHERE filename LIKE ?', (f"{prefix}%",))
    rows = cursor.fetchall()
    conn.close()
    return [{"filename": row[0], "size_bytes": row[1], "k": row[2], "n": row[3]} for row in rows]

async def heal_file(filename: str, reconstructed_data: bytes, k: int, n: int, file_id: str, version_id: str, manifest: dict, missing_indices: list):
    """Background task to heal missing or corrupted fragments."""
    try:
        rs = ReedSolomon()
        fragments, _ = rs.encode(reconstructed_data, k, n)
        hashes = [get_hash(f) for f in fragments]
        
        active_nodes = [node for node, active in CLUSTER_TOPOLOGY.items() if active]
        
        for i in missing_indices:
            if not active_nodes:
                print("No active nodes available for healing.")
                break
                
            new_node = random.choice(active_nodes)
            chunk_id = f"{file_id}_{version_id}_{i}"
            fragment = fragments[i]
            
            files = {'file': (chunk_id, fragment)}
            try:
                await http_client.post(f"{new_node}/upload/{chunk_id}", files=files, timeout=5.0)
                manifest[str(i)] = {"node": new_node, "hash": hashes[i]}
                print(f"Self-healed fragment {i} of {filename} on {new_node}")
            except Exception as e:
                print(f"Failed to heal fragment {i} on {new_node}: {e}")
                
        # Update manifest in database
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute('UPDATE files SET manifest = ? WHERE filename = ?', (json.dumps(manifest), filename))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Error during self-healing: {e}")

@app.get("/download/{filename:path}")
async def download_file(filename: str, background_tasks: BackgroundTasks):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT file_id, version_id, original_size, padding_len, k, n, manifest FROM files WHERE filename = ?', (filename,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        raise HTTPException(status_code=404, detail="File not found")
        
    file_id, version_id, original_size, padding_len, k, n, manifest_str = row
    manifest = json.loads(manifest_str)
    
    retrieved_fragments = {}
    missing_indices = []

    for idx_str, meta in manifest.items():
        i = int(idx_str)
        node_url = meta["node"]
        expected_hash = meta["hash"]
        
        if not CLUSTER_TOPOLOGY.get(node_url, False):
            print(f"Node {node_url} is inactive. Skipping chunk {i}.")
            missing_indices.append(i)
            continue
            
        chunk_id = f"{file_id}_{version_id}_{i}"
        try:
            response = await http_client.get(f"{node_url}/download/{chunk_id}", timeout=2.0)
            if response.status_code == 200:
                downloaded_data = response.content
                downloaded_hash = get_hash(downloaded_data)
                
                if downloaded_hash == expected_hash:
                    retrieved_fragments[i] = downloaded_data
                else:
                    print(f"Integrity check failed for fragment {i} from {node_url}")
                    missing_indices.append(i)
            else:
                print(f"Failed to download fragment {i} from {node_url}")
                missing_indices.append(i)
        except httpx.RequestError:
            print(f"Node {node_url} unavailable.")
            missing_indices.append(i)

    if len(retrieved_fragments) < k:
        raise HTTPException(status_code=500, detail="Not enough valid fragments to reconstruct file.")

    rs = ReedSolomon()
    reconstructed_data = rs.decode(retrieved_fragments, k, n, original_size, padding_len)
    
    if missing_indices:
        print(f"Triggering background self-healing for {filename}. Missing indices: {missing_indices}")
        background_tasks.add_task(
            heal_file, 
            filename, 
            reconstructed_data, 
            k, 
            n, 
            file_id, 
            version_id, 
            manifest, 
            missing_indices
        )
        
    return StreamingResponse(
        io.BytesIO(reconstructed_data), 
        media_type="application/octet-stream", 
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

class TopologyToggleRequest(BaseModel):
    node_url: str

@app.post("/admin/topology/toggle")
async def toggle_topology(req: TopologyToggleRequest):
    if req.node_url in CLUSTER_TOPOLOGY:
        CLUSTER_TOPOLOGY[req.node_url] = not CLUSTER_TOPOLOGY[req.node_url]
        return {"message": f"Toggled {req.node_url} to active={CLUSTER_TOPOLOGY[req.node_url]}"}
    else:
        raise HTTPException(status_code=404, detail="Node URL not found in topology")

@app.get("/admin/topology")
async def get_topology():
    return CLUSTER_TOPOLOGY

@app.delete("/delete/{filename:path}")
async def delete_file(filename: str):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT file_id, version_id, manifest FROM files WHERE filename = ?', (filename,))
    row = cursor.fetchone()
    
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="File not found")
        
    file_id, version_id, manifest_str = row
    manifest = json.loads(manifest_str)
    
    # Send delete requests to nodes
    for idx_str, meta in manifest.items():
        node_url = meta["node"]
        chunk_id = f"{file_id}_{version_id}_{idx_str}"
        try:
            # We fire and forget these deletes. If a node is down, the chunk is orphaned, 
            # but in a real system we'd use a background sweeper.
            await http_client.delete(f"{node_url}/delete/{chunk_id}", timeout=2.0)
        except Exception as e:
            print(f"Failed to delete chunk {chunk_id} from {node_url}: {e}")

    # Remove from manifest
    cursor.execute('DELETE FROM files WHERE filename = ?', (filename,))
    conn.commit()
    conn.close()
    
    return {"message": f"Successfully deleted {filename}"}

@app.post("/admin/corrupt/{node_id}/{filename:path}")
async def corrupt_file(node_id: int, filename: str):
    """
    Demo/Admin Endpoint: Instructs a specific node to corrupt its chunk for this file.
    """
    try:
        node_url = RAW_NODE_URLS[node_id - 1]
    except IndexError:
        raise HTTPException(status_code=400, detail=f"Invalid node_id. Must be between 1 and {len(RAW_NODE_URLS)}.")

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT file_id, version_id, manifest FROM files WHERE filename = ?', (filename,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        raise HTTPException(status_code=404, detail="File not found")
        
    file_id, version_id, manifest_str = row
    manifest = json.loads(manifest_str)
    
    chunk_id = None
    for idx_str, meta in manifest.items():
        if meta["node"] == node_url:
            chunk_id = f"{file_id}_{version_id}_{idx_str}"
            break
            
    if not chunk_id:
        raise HTTPException(status_code=404, detail=f"No chunk found on node {node_url} for file {filename}")

    try:
        response = await http_client.post(f"{node_url}/corrupt/{chunk_id}", timeout=2.0)
        if response.status_code == 200:
            return {"message": f"Successfully instructed node {node_id} ({node_url}) to corrupt chunk for '{filename}'"}
        else:
            raise HTTPException(status_code=500, detail=f"Node {node_url} returned an error: {response.text}")
    except httpx.RequestError as e:
        raise HTTPException(status_code=500, detail=f"Could not reach node {node_url}: {str(e)}")
