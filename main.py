from fastapi import FastAPI, Header, HTTPException, Request, Query, Depends
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional
from collections import defaultdict, deque
from threading import Lock
import time
import uuid
import base64
import json
import math

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Retry-After"],
)

TOTAL_ORDERS = 50
RATE_LIMIT = 19
WINDOW_SECONDS = 10

ORDERS_CATALOG = [
    {"id": i, "name": f"Order {i}"}
    for i in range(1, TOTAL_ORDERS + 1)
]

idempotency_store = {}
idempotency_lock = Lock()

rate_buckets = defaultdict(deque)
rate_lock = Lock()


def encode_cursor(position: int) -> str:
    raw = json.dumps({"pos": position}).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("utf-8")


def decode_cursor(cursor: str) -> int:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("utf-8"))
        data = json.loads(raw.decode("utf-8"))
        position = int(data["pos"])

        if position < 0 or position > TOTAL_ORDERS:
            raise ValueError

        return position
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid cursor")


def check_rate_limit(request: Request):
    client_id = request.headers.get("X-Client-Id", "anonymous")
    now = time.monotonic()

    with rate_lock:
        bucket = rate_buckets[client_id]

        while bucket and now - bucket[0] >= WINDOW_SECONDS:
            bucket.popleft()

        if len(bucket) >= RATE_LIMIT:
            retry_after = math.ceil(WINDOW_SECONDS - (now - bucket[0]))
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded",
                headers={"Retry-After": str(retry_after)}
            )

        bucket.append(now)


@app.get("/")
def root():
    return {
        "message": "Orders API is running",
        "total_orders": TOTAL_ORDERS,
        "rate_limit": f"{RATE_LIMIT} requests per {WINDOW_SECONDS} seconds"
    }


@app.post("/orders", status_code=201, dependencies=[Depends(check_rate_limit)])
def create_order(
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key")
):
    if not idempotency_key:
        raise HTTPException(status_code=400, detail="Idempotency-Key header is required")

    with idempotency_lock:
        if idempotency_key in idempotency_store:
            return idempotency_store[idempotency_key]

        order = {
            "id": str(uuid.uuid4()),
            "status": "created"
        }

        idempotency_store[idempotency_key] = order
        return order


@app.get("/orders", dependencies=[Depends(check_rate_limit)])
def list_orders(
    limit: int = Query(default=10, ge=1),
    cursor: Optional[str] = None
):
    if cursor is None:
        start = 0
    else:
        start = decode_cursor(cursor)

    end = min(start + limit, TOTAL_ORDERS)

    items = ORDERS_CATALOG[start:end]
    next_cursor = encode_cursor(end) if end < TOTAL_ORDERS else None

    return {
        "items": items,
        "next_cursor": next_cursor
    }
