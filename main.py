from datetime import datetime, timezone, timedelta
import os
import sqlite3
import string
import random

from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

DB_DIR = os.getenv("DB_DIR", "/app/data")
os.makedirs(DB_DIR, exist_ok=True)

DB_URL = os.path.join(DB_DIR, "deliveries.db")


def init_db():
    with get_connection() as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS deliveries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL UNIQUE,
                dispatched_at TEXT NOT NULL,
                delivered_at TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        con.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()

    yield


app = FastAPI(title="Delivery Simulation API", lifespan=lifespan)


class SendRequest(BaseModel):
    to_dispatch: int = Field(gt=0)
    to_deliver: int = Field(gt=0)


def get_connection():
    con = sqlite3.connect(DB_URL)
    con.row_factory = sqlite3.Row
    return con


def generate_tracking_code():
    prefix = "".join(random.choices(string.ascii_uppercase, k=2))
    number = "".join(random.choices(string.digits, k=9))

    return f"{prefix}{number}BR"


def generate_unique_tracking_code(con):
    while True:
        code = generate_tracking_code()

        result = con.execute(
            "SELECT 1 FROM deliveries WHERE code = ?", (code,)
        ).fetchone()

        if result is None:
            return code


@app.post("/send")
async def send(data: SendRequest):
    stmt = """
            INSERT INTO deliveries (
                code,
                dispatched_at,
                delivered_at,
                created_at
            )
            VALUES (?, ?, ?, ?)
            """
    created_at = datetime.now(timezone.utc)
    dispatched_at = created_at + timedelta(seconds=data.to_dispatch)
    delivered_at = dispatched_at + timedelta(seconds=data.to_deliver)

    with get_connection() as con:
        code = generate_unique_tracking_code(con)

        cursor = con.execute(
            stmt,
            (
                code,
                dispatched_at.isoformat(),
                delivered_at.isoformat(),
                created_at.isoformat(),
            ),
        )

        con.commit()

    return {
        "id": cursor.lastrowid,
        "code": code,
        "dispatched_at": dispatched_at.isoformat(),
        "delivered_at": delivered_at.isoformat(),
        "created_at": created_at.isoformat(),
    }


@app.get("/track/{code}")
async def track(code: str):
    stmt = """
        SELECT *
        FROM deliveries
        WHERE code = ?
    """

    with get_connection() as con:
        result = con.execute(stmt, (code,)).fetchone()

    if result is None:
        raise HTTPException(status_code=404, detail="Entrega não encontrada")

    now = datetime.now(timezone.utc)
    dispatched_at = datetime.fromisoformat(result["dispatched_at"])
    delivered_at = datetime.fromisoformat(result["delivered_at"])

    if now < dispatched_at:
        status = "AWAITING_DISPATCH"
    elif now >= delivered_at:
        status = "DELIVERED"
    else:
        status = "IN_TRANSIT"

    return {
        "id": result["id"],
        "code": result["code"],
        "status": status,
        "dispatched_at": dispatched_at,
        "delivered_at": delivered_at,
    }
