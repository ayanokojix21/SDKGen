# Stub for job manager
def create_job(url: str, language: str, page_content: str, page_links: list) -> tuple[str, dict]:
    """Creates a new job and initial state."""
    import uuid
    job_id = str(uuid.uuid4())
    return job_id, {}

def save_checkpoint(job_id: str, state: dict):
    pass

def load_checkpoint(job_id: str) -> dict:
    return {}
