from typing import List, Optional, Dict
from pydantic import BaseModel, Field

# ── Supervisor ────────────────────────────────────────────────────────────

class SupervisorDecision(BaseModel):
    next_agent: str = Field(description="The name of the next agent to route to, or 'end' to finish.")
    instruction: str = Field(description="Specific directive for the next agent.")
    reasoning: str = Field(description="Brief explanation for this routing decision.")

# ── Researcher ────────────────────────────────────────────────────────────

class CrawlPage(BaseModel):
    url: str = Field(description="The absolute URL to crawl.")
    reason: str = Field(description="Why this page was selected (e.g., 'Auth details', 'Endpoints').")
    priority: int = Field(description="Crawl priority (1 is highest).")

class CrawlPlan(BaseModel):
    crawl_plan: List[CrawlPage] = Field(description="List of pages to crawl.")
    skipped: List[str] = Field(description="List of URLs or link texts that were skipped and why.")
    notes: Optional[str] = Field(description="General observations about the documentation structure.")

class AuthConfig(BaseModel):
    type: str = Field(description="Auth type (bearer, api_key, basic, oauth2, none).")
    location: str = Field(description="Where the auth info goes (header, query, body).")
    key_name: str = Field(description="The parameter or header name (e.g., 'Authorization', 'appid').")
    example: str = Field(description="A sample value for the auth parameter.")

class KnowledgeBaseSummary(BaseModel):
    api_name: str = Field(description="Official name of the API.")
    base_url: str = Field(description="The base URL for all API requests.")
    auth: AuthConfig = Field(description="Authentication configuration.")
    key_endpoints_summary: str = Field(description="A high-level summary of the most important endpoints found.")

# ── Architect ─────────────────────────────────────────────────────────────

class Parameter(BaseModel):
    name: str
    type: str
    required: bool
    description: str

class Endpoint(BaseModel):
    name: str = Field(description="CamelCase name for the SDK method.")
    path: str = Field(description="Endpoint path (e.g., '/weather').")
    method: str = Field(description="HTTP method (GET, POST, etc.).")
    description: str = Field(description="Description of what the endpoint does.")
    path_params: List[Parameter] = Field(default_factory=list)
    query_params: List[Parameter] = Field(default_factory=list)
    request_body: Optional[Dict] = Field(description="Schema of the request body if applicable.")
    response_schema: Optional[Dict] = Field(description="Schema of the expected response.")

class ApiSchema(BaseModel):
    api_name: str
    base_url: str
    auth: AuthConfig
    endpoints: List[Endpoint]

# ── Engineer ──────────────────────────────────────────────────────────────

class SdkFile(BaseModel):
    filename: str
    content: str

class GeneratedSdk(BaseModel):
    files: List[SdkFile] = Field(description="List of generated SDK files.")
    internal_notes: str = Field(description="Developer notes about the implementation or choices made.")

# ── QA Tester ─────────────────────────────────────────────────────────────

class QaTestResult(BaseModel):
    test_id: str
    category: str
    target: str
    description: str
    status: str = Field(description="pass, fail, or skip")
    details: str
    fix_suggestion: Optional[str]

class QaSummary(BaseModel):
    passed: int
    failed: int
    recommendation: str = Field(description="fix_by_engineer, fix_by_researcher, or proceed")

class QaReport(BaseModel):
    summary: QaSummary
    test_plan: List[QaTestResult]
