"""App entry. Shared, frozen: every router is registered here once, so nobody edits this file again."""
from fastapi import FastAPI

from app.routers import (batches, email_history, email_queue, exceptions, health, manual_review,
                         reports, scheduler, settings, vendors)

app = FastAPI(title="Vendor Payment Reconciliation")

for r in (health, batches, scheduler,                                                        # Person A
          reports, email_queue, email_history, exceptions, manual_review, vendors, settings):  # Person B
    app.include_router(r.router, prefix="/api")
