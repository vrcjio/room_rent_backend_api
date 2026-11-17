from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


class SyncRecordItem(BaseModel):
    table_name: str = Field(..., description="e.g. rooms, tenants, bills, landlord_profile")
    record_key: str = Field(..., description="Unique key across devices")
    data: Dict[str, Any]
    is_deleted: int = 0
    deleted_at: Optional[str] = None
    updated_at: str


class SyncPushRequest(BaseModel):
    device_id: str
    records: List[SyncRecordItem]


class SyncPushResponse(BaseModel):
    status: str
    applied_count: int
    skipped_conflicts: int
    server_time: str


class SyncPullResponse(BaseModel):
    status: str
    server_time: str
    records: List[Dict[str, Any]]