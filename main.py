"""
Middleware stack: CORS + Request Context + Rate Limit.
Compatible with Python 3.8+.
"""
import time
import uuid
from collections import defaultdict, deque

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

# ── Assigned values ──────────────────────────────────────────────────
EMAIL = "23f3004259@ds.study.iitm.ac.in"                    # <-- EDIT
ALLOWED_ORIGIN = "https://app-0037sh.example.com"
B = 8
WINDOW = 10.0
# ─────────────────────────────────────────────────────────────────────

app = FastAPI(title="Middleware Stack Demo")

CLIENT_HITS = defaultdict(deque)


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    client_id = request.headers.get("x-client-id")
    if client_id:
        now = time.monotonic()
        bucket = CLIENT_HITS[client_id]
        while bucket and bucket[0] <= now - WINDOW:
            bucket.popleft()
        if len(bucket) >= B:
            retry_after = max(1, int(WINDOW - (now - bucket[0])) + 1)
            return Response(
                content='{"detail":"rate limit exceeded"}',
                status_code=429,
                media_type="application/json",
                headers={"Retry-After": str(retry_after)},
            )
        bucket.append(now)
    return await call_next(request)


@app.middleware("http")
async def request_context_middleware(request: Request, call_next):
    incoming = (request.headers.get("x-request-id") or "").strip()
    request_id = incoming if incoming else str(uuid.uuid4())
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


CORS_ORIGIN_REGEX = (
    r"^https?://("
    r"app-0037sh\.example\.com"
    r"|([a-zA-Z0-9-]+\.)*s-anand\.net"
    r"|([a-zA-Z0-9-]+\.)*sanand\.workers\.dev"
    r"|localhost(:\d+)?"
    r"|127\.0\.0\.1(:\d+)?"
    r")$"
)

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=CORS_ORIGIN_REGEX,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID", "Retry-After"],
)


@app.get("/ping")
async def ping(request: Request):
    return {
        "email": EMAIL,
        "request_id": request.state.request_id,
    }


@app.get("/")
def root():
    return {"ok": True, "endpoint": "/ping", "allowed_origin": ALLOWED_ORIGIN, "B": B}
