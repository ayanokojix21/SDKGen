from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uuid

# Import the SSE tools (EventSourceResponse is the modern way)
# from sse_starlette.sse import EventSourceResponse

app = FastAPI(title="Docs-to-Code Server")

# Allow Chrome extension and local testing to hit this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, restrict this
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class GenerateRequest(BaseModel):
    target_url: str
    language: str
    page_content: str
    page_links: list[dict]

@app.get("/health")
async def health_check():
    """Simple health check endpoint."""
    return {"status": "ok"}

@app.post("/generate/start")
async def start_generation(request: GenerateRequest):
    """
    Starts a new SDK generation job.
    Returns the job_id immediately while the graph runs in the background.
    """
    job_id = str(uuid.uuid4())
    # TODO: Initialize SDKJobState
    # TODO: Save checkpoint
    # TODO: Launch graph runner as background asyncio task
    
    return {"job_id": job_id, "message": "Job started successfully"}

@app.get("/generate/stream")
async def stream_generation(job_id: str):
    """
    SSE endpoint. Streams events from the job's event queue to the frontend.
    """
    # TODO: implement EventSourceResponse yielding events from job state
    return {"error": "Not implemented yet. Run Task 1.5 to implement SSE"}

@app.get("/download/{job_id}")
async def download_sdk(job_id: str):
    """
    Returns a ZIP file containing the generated SDK.
    """
    # TODO: return ZIP file
    return {"error": "Not implemented yet"}
