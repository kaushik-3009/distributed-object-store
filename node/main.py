from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
import os
import shutil

app = FastAPI(title="Storage Node Service")

DATA_DIR = os.getenv("DATA_DIR", "/app/data")
os.makedirs(DATA_DIR, exist_ok=True)

@app.get("/health")
def health_check():
    node_id = os.getenv("NODE_ID", "unknown_node")
    zone = os.getenv("NODE_ZONE", "default-zone")
    return {"status": "ok", "service": f"storage-node-{node_id}", "zone": zone}

@app.get("/metrics")
def get_metrics():
    node_id = os.getenv("NODE_ID", "unknown_node")
    rss, vms = 0, 0
    try:
        with open("/proc/self/status", "r") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    rss = int(line.split()[1]) * 1024
                elif line.startswith("VmSize:"):
                    vms = int(line.split()[1]) * 1024
    except Exception:
        pass
    return {
        "node_id": node_id,
        "rss_bytes": rss,
        "rss_mb": rss / (1024 * 1024),
        "vms_bytes": vms,
        "vms_mb": vms / (1024 * 1024),
    }

@app.post("/upload/{file_id}")
async def upload_chunk(file_id: str, file: UploadFile = File(...)):
    file_path = os.path.join(DATA_DIR, file_id)
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    return {"message": f"Successfully stored {file_id}"}

@app.get("/download/{file_id}")
async def download_chunk(file_id: str):
    file_path = os.path.join(DATA_DIR, file_id)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(file_path)

@app.delete("/delete/{file_id}")
async def delete_chunk(file_id: str):
    file_path = os.path.join(DATA_DIR, file_id)
    if os.path.exists(file_path):
        os.remove(file_path)
        return {"message": f"Deleted {file_id}"}
    raise HTTPException(status_code=404, detail="File not found")

@app.post("/corrupt/{file_id}")
async def corrupt_chunk(file_id: str):
    """
    ADMIN ENDPOINT: Intentionally ruins a file to test the Integrity Layer.
    Appends the word "CORRUPTION" to the middle of the binary file.
    """
    file_path = os.path.join(DATA_DIR, file_id)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")
    
    with open(file_path, "a") as f:
        f.write("HACKER_CORRUPTION")
        
    return {"message": f"File {file_id} has been intentionally corrupted."}

@app.get("/list")
async def list_chunks():
    chunks = []
    if os.path.exists(DATA_DIR):
        for f in os.listdir(DATA_DIR):
            if os.path.isfile(os.path.join(DATA_DIR, f)):
                chunks.append(f)
    return {"chunks": chunks}
