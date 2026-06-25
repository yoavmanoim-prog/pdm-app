"""
On-site (AWS-free) ASGI entrypoint.

Run with:  uvicorn app.onsite:app

This is the ONE seam between the cloud app and the on-site build. It reuses the
entire FastAPI application unchanged (``app.main:app`` — all routers, auth,
startup, migrations) but swaps the storage layer from S3 to the local
filesystem and adds a public endpoint to serve those files.

How the swap works without editing any cloud file:
  Every caller does ``from app import storage`` and then calls
  ``storage.upload_file(...)`` etc. Python resolves ``storage.upload_file`` on
  the module object *at call time*, so if we replace those attributes on the
  module here — before any request is handled — every router transparently uses
  the filesystem backend. The cloud entrypoint (``app.main``) never imports this
  module, so its S3 behaviour is completely untouched.
"""

from app import storage, storage_local

# Re-point each public storage function at its filesystem equivalent.
# (Listed explicitly rather than looped, so it's obvious what is being swapped
# and a typo surfaces as an AttributeError at startup, not a silent miss.)
storage.upload_file = storage_local.upload_file
storage.download_file = storage_local.download_file
storage.generate_presigned_url = storage_local.generate_presigned_url
storage.presigned_url_if_exists = storage_local.presigned_url_if_exists
storage.copy_from_peer = storage_local.copy_from_peer
storage.delete_file = storage_local.delete_file
storage.file_exists = storage_local.file_exists

# Import the real app only AFTER the swap (order isn't strictly required since
# callers resolve attributes lazily, but it keeps the intent unambiguous).
from app.main import app  # noqa: E402
from app import files_router  # noqa: E402

# Public route (no login dependency): browser navigations to PDFs can't carry a
# JWT, so the signed URL is the gate. See files_router for details.
app.include_router(files_router.router)
