"""App entry. Shared: every router is mounted here once, so neither track edits this file."""
from fastapi import FastAPI

from app.routers import (auth, batches, email_history, email_queue, exceptions, health, reconcile,
                         reports, review, scheduler, settings, vendors)

app = FastAPI(title="Vendor Payment Reconciliation")

for r in (health, auth, batches, reconcile, scheduler,
          email_queue, email_history, exceptions, review, reports, vendors, settings):
    app.include_router(r.router, prefix="/api")
