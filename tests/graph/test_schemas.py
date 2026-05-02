"""Tests for backend/graph/schemas.py — Pydantic model validation."""
import pytest
from pydantic import ValidationError
from backend.graph.schemas import (
    SupervisorDecision, CrawlPlan, CrawlPage, ApiSchema, GeneratedSdk,
    QaReport, QaSummary, AuthConfig, SdkFile, QaTestResult, KnowledgeBaseSummary,
    Endpoint, Parameter,
)


def test_supervisor_decision_validation():
    valid = SupervisorDecision(next_agent="researcher", reasoning="Need docs", instruction="Crawl")
    assert valid.next_agent == "researcher"
    assert valid.reasoning == "Need docs"


def test_crawl_plan_validation():
    valid = CrawlPlan(
        crawl_plan=[CrawlPage(url="http://api.com/docs", reason="docs", priority=1)],
        skipped=[],
        notes="None",
    )
    assert len(valid.crawl_plan) == 1
    assert valid.crawl_plan[0].priority == 1


def test_api_schema_validation():
    valid = ApiSchema(
        api_name="Test",
        base_url="http://api",
        auth=AuthConfig(type="bearer", location="header", key_name="Auth", example="token"),
        endpoints=[
            Endpoint(
                name="test", method="GET", path="/test", description="",
                path_params=[], query_params=[], request_body=None, response_schema=None,
            )
        ],
    )
    assert valid.api_name == "Test"
    assert len(valid.endpoints) == 1


def test_generated_sdk_validation():
    valid = GeneratedSdk(
        files=[SdkFile(filename="client.py", content="pass")],
        internal_notes="Looks good",
    )
    assert len(valid.files) == 1
    assert valid.files[0].filename == "client.py"


def test_qa_report_validation():
    valid = QaReport(
        summary=QaSummary(passed=1, failed=0, recommendation="proceed"),
        test_plan=[
            QaTestResult(
                test_id="1", category="static", target="client.py",
                description="Syntax check", status="pass", details="OK", fix_suggestion=None,
            )
        ],
    )
    assert valid.summary.recommendation == "proceed"
    assert len(valid.test_plan) == 1


def test_knowledge_base_summary():
    valid = KnowledgeBaseSummary(
        api_name="WeatherAPI",
        base_url="https://api.weather.com",
        auth=AuthConfig(type="api_key", location="query", key_name="appid", example="abc123"),
        key_endpoints_summary="GET /forecast, GET /current",
    )
    assert valid.api_name == "WeatherAPI"
