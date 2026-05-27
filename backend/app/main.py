from fastapi import FastAPI

app = FastAPI()

@app.get("/")
def root():
    return {"status": "ok", "app": "MechDocs"}

@app.get("/health")
def health():
    return {"healthy": True}