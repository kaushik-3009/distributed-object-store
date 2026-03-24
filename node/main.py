from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
import os
import shutil

app = FastAPI(title="Storage Node Service")

# Use an environment variable or default to /app/data
DATA_DIR = os.getenv("DATA_DIR", "/app/data")
os.makedirs(DATA_DIR, exist_ok=True)

@app.get("/health")
def health_check():
    node_id = os.getenv("NODE_ID", "unknown_node")
    return {"status": "ok", "service": f"storage-node-{node_id}"}

@app.post("/upload/{file_id}")
async def upload_chunk(file_id: str, file: UploadFile = File(...)):
    # Simple: save the file using the file_id as the name
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
