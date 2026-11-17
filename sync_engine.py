import json
from datetime import datetime, timezone
from typing import List, Dict, Any, Tuple
from database import server_db_session
from schemas import SyncRecordItem


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def process_push_records(device_id: str, items: List[SyncRecordItem]) -> Tuple[int, int, str]:
    """
    Multi-Device Conflict Resolution:
    1. Delete-Wins: Agar server par record pehle se deleted hai, toh offline update reject hoga.
    2. Tombstone Propagation: Agar incoming record delete hai, toh server par is_deleted=1 mark hoga.
    3. Last-Write-Wins: Dono active hain toh latest UTC 'updated_at' timestamp jeetega.
    """
    applied = 0
    skipped = 0
    now = utc_now()

    with server_db_session() as conn:
        for item in items:
            existing = conn.execute(
                "SELECT * FROM synced_records WHERE table_name = ? AND record_key = ?",
                (item.table_name, item.record_key),
            ).fetchone()

            payload_str = json.dumps(item.data, ensure_ascii=False)

            if not existing:
                conn.execute(
                    """
                    INSERT INTO synced_records
                    (table_name, record_key, device_id, payload_json, is_deleted, deleted_at, updated_at, server_received_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        item.table_name,
                        item.record_key,
                        device_id,
                        payload_str,
                        item.is_deleted,
                        item.deleted_at,
                        item.updated_at,
                        now,
                    ),
                )
                applied += 1
                continue

            # Rule 1: Server par pehle se deleted hai -> Delete Wins!
            if existing["is_deleted"] == 1:
                skipped += 1
                continue

            # Rule 2: Incoming record delete command hai -> Tombstone mark karein
            if item.is_deleted == 1:
                conn.execute(
                    """
                    UPDATE synced_records
                    SET is_deleted = 1,
                        deleted_at = ?,
                        updated_at = ?,
                        device_id = ?,
                        payload_json = ?,
                        server_received_at = ?
                    WHERE id = ?
                    """,
                    (
                        item.deleted_at or item.updated_at,
                        item.updated_at,
                        device_id,
                        payload_str,
                        now,
                        existing["id"],
                    ),
                )
                applied += 1
                continue

            # Rule 3: Update vs Update -> Latest UTC timestamp jeetega
            if item.updated_at >= existing["updated_at"]:
                conn.execute(
                    """
                    UPDATE synced_records
                    SET payload_json = ?,
                        updated_at = ?,
                        device_id = ?,
                        server_received_at = ?
                    WHERE id = ?
                    """,
                    (payload_str, item.updated_at, device_id, now, existing["id"]),
                )
                applied += 1
            else:
                skipped += 1

    return applied, skipped, now


def fetch_records_since(since_timestamp: str = "") -> Tuple[List[Dict[str, Any]], str]:
    """Last sync ke baad ke sabhi updates aur tombstones client ko bhejta hai."""
    now = utc_now()
    with server_db_session() as conn:
        if since_timestamp:
            rows = conn.execute(
                """
                SELECT * FROM synced_records
                WHERE server_received_at > ?
                ORDER BY server_received_at ASC
                """,
                (since_timestamp,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM synced_records ORDER BY server_received_at ASC"
            ).fetchall()

        results = []
        for r in rows:
            results.append(
                {
                    "table_name": r["table_name"],
                    "record_key": r["record_key"],
                    "device_id": r["device_id"],
                    "data": json.loads(r["payload_json"]),
                    "is_deleted": r["is_deleted"],
                    "deleted_at": r["deleted_at"],
                    "updated_at": r["updated_at"],
                    "server_received_at": r["server_received_at"],
                }
            )
        return results, now