import os
import io
import uuid
import json
import sqlite3
import hashlib
import random
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
import httpx
from pydantic import BaseModel

from erasure_coding import ReedSolomon

# --- CONFIG & GLOBALS ---
DB_FILE = "/app/coordinator.db"
http_client: httpx.AsyncClient = None

RAW_NODE_URLS = os.getenv(
    "NODE_URLS",
    "http://node1:8000,http://node2:8000,http://node3:8000,http://node4:8000,http://node5:8000"
).split(",")

CLUSTER_TOPOLOGY = {url: {"active": True, "zone": "unknown"} for url in RAW_NODE_URLS}

# --- DATABASE ---
def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS files (
            filename TEXT PRIMARY KEY,
            file_id TEXT NOT NULL,
            version_id TEXT NOT NULL,
            original_size INTEGER NOT NULL,
            padding_len INTEGER NOT NULL,
            k INTEGER NOT NULL,
            n INTEGER NOT NULL,
            manifest TEXT NOT NULL,
            content_hash TEXT
        )
    ''')
    conn.commit()
    conn.close()

def get_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

# --- CORE LOGIC ---
async def core_upload(filename: str, file_bytes: bytes, k: int, n: int):
    """Internal core logic for uploading/seeding files."""
    content_hash = get_hash(file_bytes)
    original_size = len(file_bytes)

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # 1. Deduplication Check
    cursor.execute('SELECT file_id, version_id, original_size, padding_len, k, n, manifest FROM files WHERE content_hash = ? LIMIT 1', (content_hash,))
    existing = cursor.fetchone()
    if existing:
        file_id, version_id, size, pad, ek, en, manifest = existing
        try:
            cursor.execute('''
                INSERT INTO files (filename, file_id, version_id, original_size, padding_len, k, n, manifest, content_hash)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (filename, file_id, version_id, size, pad, ek, en, manifest, content_hash))
            conn.commit()
            conn.close()
            return {"message": "Deduplicated successfully", "filename": filename, "deduplicated": True}
        except sqlite3.IntegrityError:
            conn.close()
            return {"message": "File already exists", "filename": filename}

    # 2. Encoding
    rs = ReedSolomon()
    fragments, padding_len = rs.encode(file_bytes, k, n)

    # 3. Geo-Aware Node Selection
    zones = {}
    for url, info in CLUSTER_TOPOLOGY.items():
        if info["active"]:
            z = info["zone"]
            if z not in zones: zones[z] = []
            zones[z].append(url)
    
    total_active = sum(len(v) for v in zones.values())
    if total_active < n:
        conn.close()
        raise HTTPException(status_code=503, detail=f"Not enough active nodes (need {n}, have {total_active})")

    # Round-robin spread across zones
    selected_nodes = []
    zone_names = list(zones.keys())
    random.shuffle(zone_names)
    idx = 0
    while len(selected_nodes) < n:
        z = zone_names[idx % len(zone_names)]
        if zones[z]:
            selected_nodes.append(zones[z].pop(random.randrange(len(zones[z]))))
        idx += 1

    file_id = str(uuid.uuid4())
    version_id = str(uuid.uuid4())
    hashes = [get_hash(f) for f in fragments]
    manifest = {}

    for i, fragment in enumerate(fragments):
        node_url = selected_nodes[i]
        chunk_id = f"{file_id}_{version_id}_{i}"
        files = {'file': (chunk_id, fragment)}
        await http_client.post(f"{node_url}/upload/{chunk_id}", files=files, timeout=10.0)
        manifest[str(i)] = {"node": node_url, "hash": hashes[i]}

    # 4. Persistence
    cursor.execute('''
        INSERT OR REPLACE INTO files (filename, file_id, version_id, original_size, padding_len, k, n, manifest, content_hash) 
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (filename, file_id, version_id, original_size, padding_len, k, n, json.dumps(manifest), content_hash))
    conn.commit()
    conn.close()
    return {"message": "Success", "filename": filename}

# --- STARTUP TASKS ---
async def initialize_topology():
    print(f"[*] Discovery: Mapping {len(RAW_NODE_URLS)} nodes...")
    for url in RAW_NODE_URLS:
        try:
            resp = await http_client.get(f"{url}/health", timeout=3.0)
            if resp.status_code == 200:
                zone = resp.json().get("zone", "default-zone")
                CLUSTER_TOPOLOGY[url] = {"active": True, "zone": zone}
                print(f"    [+] {url} -> {zone}")
        except Exception:
            CLUSTER_TOPOLOGY[url] = {"active": False, "zone": "unknown"}
            print(f"    [-] {url} -> OFFLINE")

async def seed_default_files():
    conn = sqlite3.connect(DB_FILE)
    count = conn.execute('SELECT COUNT(*) FROM files').fetchone()[0]
    conn.close()
    if count == 0:
        print("[*] Seeding default system files...")
        defaults = [
            "/app/testfile1.json",
            "/app/testfile2.json",
        ]
        for path in defaults:
            if os.path.exists(path):
                with open(path, "rb") as f:
                    await core_upload(os.path.basename(path), f.read(), 2, 3)
                print(f"    [+] Seeded: {os.path.basename(path)}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    global http_client
    init_db()
    http_client = httpx.AsyncClient()
    async def startup_sequence():
        await asyncio.sleep(3)
        await initialize_topology()
        await seed_default_files()
    asyncio.create_task(startup_sequence())
    yield
    await http_client.aclose()

# --- APP INIT ---
app = FastAPI(title="SecStore Coordinator", lifespan=lifespan)
app.mount("/ui", StaticFiles(directory="/app/static", html=True), name="static")

# --- ENDPOINTS ---
@app.post("/upload/")
async def upload_file(file: UploadFile = File(...), custom_filename: str = Form(None), k: int = Form(2), n: int = Form(3)):
    filename = custom_filename if custom_filename else file.filename
    file_bytes = await file.read()
    if len(file_bytes) > 20 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large (Max 20MB)")
    return await core_upload(filename, file_bytes, k, n)

@app.get("/list/")
async def list_files(prefix: str = ""):
    conn = sqlite3.connect(DB_FILE)
    rows = conn.execute('SELECT filename, original_size, k, n FROM files WHERE filename LIKE ?', (f"{prefix}%",)).fetchall()
    conn.close()
    return [{"filename": r[0], "size_bytes": r[1], "k": r[2], "n": r[3]} for r in rows]

@app.get("/download/{filename:path}")
async def download_file(filename: str, background_tasks: BackgroundTasks):
    conn = sqlite3.connect(DB_FILE)
    row = conn.execute('SELECT file_id, version_id, original_size, padding_len, k, n, manifest FROM files WHERE filename = ?', (filename,)).fetchone()
    conn.close()
    if not row: raise HTTPException(status_code=404, detail="File not found")
    
    file_id, version_id, size, pad, k, n, manifest_str = row
    manifest = json.loads(manifest_str)
    retrieved = {}
    missing = []

    for idx, meta in manifest.items():
        url = meta["node"]
        if not CLUSTER_TOPOLOGY.get(url, {}).get("active"):
            missing.append(int(idx)); continue
        try:
            resp = await http_client.get(f"{url}/download/{file_id}_{version_id}_{idx}", timeout=5.0)
            if resp.status_code == 200 and get_hash(resp.content) == meta["hash"]:
                retrieved[int(idx)] = resp.content
            else: missing.append(int(idx))
        except Exception: missing.append(int(idx))

    if len(retrieved) < k:
        raise HTTPException(status_code=500, detail="Not enough valid fragments to reconstruct file.")

    rs = ReedSolomon()
    data = rs.decode(retrieved, k, n, size, pad)
    
    if missing:
        async def heal_worker():
            frags, _ = rs.encode(data, k, n)
            active_nodes = [u for u, i in CLUSTER_TOPOLOGY.items() if i["active"]]
            for i in missing:
                if not active_nodes: break
                node = random.choice(active_nodes)
                cid = f"{file_id}_{version_id}_{i}"
                try:
                    await http_client.post(f"{node}/upload/{cid}", files={'file': (cid, frags[i])})
                    manifest[str(i)] = {"node": node, "hash": get_hash(frags[i])}
                except Exception: pass
            conn = sqlite3.connect(DB_FILE)
            conn.execute('UPDATE files SET manifest = ? WHERE filename = ?', (json.dumps(manifest), filename))
            conn.commit(); conn.close()
        background_tasks.add_task(heal_worker)

    return StreamingResponse(io.BytesIO(data), media_type="application/octet-stream", headers={"Content-Disposition": f"attachment; filename={os.path.basename(filename)}"})

@app.delete("/delete/{filename:path}")
async def delete_file(filename: str):
    print(f"[*] DELETE_REQUEST: Received request to delete '{filename}'")
    conn = sqlite3.connect(DB_FILE)
    row = conn.execute('SELECT file_id, version_id, manifest, content_hash FROM files WHERE filename = ?', (filename,)).fetchone()
    
    if not row:
        print(f"    [-] DELETE_ERROR: File '{filename}' not found in database.")
        conn.close(); raise HTTPException(status_code=404, detail="File not found")
    fid, vid, m_str, chash = row
    count = conn.execute('SELECT COUNT(*) FROM files WHERE content_hash = ?', (chash,)).fetchone()[0]
    if count == 1:
        for idx, meta in json.loads(m_str).items():
            try: await http_client.delete(f"{meta['node']}/delete/{fid}_{vid}_{idx}")
            except Exception: pass
    conn.execute('DELETE FROM files WHERE filename = ?', (filename,))
    conn.commit(); conn.close()
    return {"message": "Deleted"}

@app.get("/admin/topology")
async def get_topology(): return CLUSTER_TOPOLOGY

class TopologyToggleRequest(BaseModel):
    node_url: str

@app.post("/admin/topology/toggle")
async def toggle_node(req: TopologyToggleRequest):
    if req.node_url in CLUSTER_TOPOLOGY:
        CLUSTER_TOPOLOGY[req.node_url]["active"] = not CLUSTER_TOPOLOGY[req.node_url]["active"]
        return {"active": CLUSTER_TOPOLOGY[req.node_url]["active"]}
    raise HTTPException(status_code=404)

@app.post("/admin/corrupt/{node_id}/{filename:path}")
async def corrupt_file(node_id: int, filename: str):
    try: url = RAW_NODE_URLS[node_id - 1]
    except IndexError: raise HTTPException(status_code=400)
    conn = sqlite3.connect(DB_FILE)
    row = conn.execute('SELECT file_id, version_id, manifest FROM files WHERE filename = ?', (filename,)).fetchone()
    conn.close()
    if not row: raise HTTPException(status_code=404)
    fid, vid, m_str = row
    for idx, meta in json.loads(m_str).items():
        if meta["node"] == url:
            await http_client.post(f"{url}/corrupt/{fid}_{vid}_{idx}")
            return {"message": "Corrupted"}
    raise HTTPException(status_code=404, detail="No chunk on this node")
