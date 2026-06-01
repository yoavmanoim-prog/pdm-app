from fastapi import FastAPI
from app.routers import schematics

app = FastAPI(title="PDM — Mechanic Schematic Manager")

app.include_router(schematics.router)


@app.get("/")
def root():
    return {"status": "ok", "app": "PDM"}


@app.get("/health")
def health():
    return {"healthy": True}
