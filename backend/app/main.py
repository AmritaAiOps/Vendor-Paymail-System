"""App entry: every router is registered here once, plus JSON logging and the 500 handler (app.middleware)."""
from fastapi import Depends, FastAPI

from app.auth import require_viewer
from app.middleware import install
from app.routers import (auth, batches, email_history, email_queue, exceptions, health, manual_review,
                         reports, scheduler, settings, vendors)

app = FastAPI(title="Vendor Payment Reconciliation")

app.include_router(health.router, prefix="/api")  # the only route open without login
for r in (auth, batches, scheduler,                                                          # Person A
          reports, email_queue, email_history, exceptions, manual_review, vendors, settings):  # Person B
    app.include_router(r.router, prefix="/api", dependencies=[Depends(require_viewer)])

install(app)
