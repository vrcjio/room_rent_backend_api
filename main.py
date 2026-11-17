import os
import shutil
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, Header, HTTPException, UploadFile, File, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from database import init_server_db, CLOUD_UPLOADS_DIR
from schemas import SyncPushRequest, SyncPushResponse, SyncPullResponse
from sync_engine import process_push_records, fetch_records_since

# Cloud par Environment Variable 'RENT_SYNC_API_KEY' se override kar sakte hain
API_SECRET_KEY = os.getenv("RENT_SYNC_API_KEY", "my_super_secret_rent_key_2026")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_server_db()
    yield


app = FastAPI(
    title="Room Rent Manager Cloud Sync API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def verify_api_key(x_api_key: str = Header(None)):
    if x_api_key != API_SECRET_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key")


@app.get("/")
@app.get("/health")
def health_check():
    return {"status": "online", "service": "Room Rent Manager Cloud Sync API"}


@app.post("/sync/push", response_model=SyncPushResponse)
def sync_push(payload: SyncPushRequest, x_api_key: str = Header(None)):
    verify_api_key(x_api_key)
    applied, skipped, server_time = process_push_records(payload.device_id, payload.records)
    return SyncPushResponse(
        status="success",
        applied_count=applied,
        skipped_conflicts=skipped,
        server_time=server_time,
    )


@app.get("/sync/pull", response_model=SyncPullResponse)
def sync_pull(
    since: str = Query(default="", description="Last sync UTC timestamp"),
    x_api_key: str = Header(None),
):
    verify_api_key(x_api_key)
    records, server_time = fetch_records_since(since)
    return SyncPullResponse(
        status="success",
        server_time=server_time,
        records=records,
    )


@app.post("/files/upload")
async def upload_backup_file(
    category: str = Query(..., description="e.g. id_proofs, agreements, receipts, branding"),
    file: UploadFile = File(...),
    x_api_key: str = Header(None),
):
    """ID proofs, Rent Agreements aur PDF Receipts ka backup save karta hai."""
    verify_api_key(x_api_key)
    target_dir = CLOUD_UPLOADS_DIR / category
    target_dir.mkdir(parents=True, exist_ok=True)

    safe_name = Path(file.filename).name
    dest_path = target_dir / safe_name

    with dest_path.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    return {"status": "uploaded", "cloud_path": f"{category}/{safe_name}"}


@app.get("/files/download/{category}/{filename}")
def download_backup_file(category: str, filename: str, x_api_key: str = Header(None)):
    """Naye device par restore karte waqt file wapas download karne ke liye."""
    verify_api_key(x_api_key)
    file_path = CLOUD_UPLOADS_DIR / category / Path(filename).name
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found on backup server")
    return FileResponse(path=str(file_path), filename=filename)