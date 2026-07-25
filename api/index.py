from fastapi import FastAPI

app = FastAPI()

@app.get("/")
def root():
    return {"message": "API is working"}

@app.get("/healthz")
def health():
    return {"status": "ok"}
