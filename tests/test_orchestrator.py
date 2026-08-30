"""Unit and integration tests for pipeline orchestration, routing, and graceful fallback."""
import pytest
from app.orchestrator import run_pipeline

LONG_CONTEXT = """System: You are an AI assistant specialized in cloud infrastructure analysis.

Instruction: All output MUST adhere to GDPR and SOC2 compliance regulations.
Constraint: DO NOT display plain-text credentials under any circumstances.

Section 1: AWS VPC Configuration
The virtual private cloud (VPC) is configured across three availability zones (us-east-1a, us-east-1b, us-east-1c). Subnets are divided into public ingress tiers and private application tiers. In order to ensure redundancy, NAT gateways are deployed in each AZ.

Section 2: Database Replication
The relational database utilizes Aurora PostgreSQL multi-region replication. Read replicas are automatically scaled based on CPU utilization and query latency metrics. Please be aware that backup retention is set to 35 days.

Section 2: Database Replication
The relational database utilizes Aurora PostgreSQL multi-region replication. Read replicas are automatically scaled based on CPU utilization and query latency metrics. Please be aware that backup retention is set to 35 days.

Section 3: Kubernetes Ingress Controller
Ingress-nginx is deployed with TLS termination at the Network Load Balancer (NLB) layer. Cert-manager automatically renews Let's Encrypt certificates every 60 days.

Section 4: Observability and Telemetry
Prometheus scrapes metrics from service endpoints every 15 seconds. Grafana dashboards visualize request rates, error rates, and p99 latency distributions.
"""

def test_pipeline_full_execution():
    """Verify full pipeline execution on verbose context."""
    res = run_pipeline(
        query="How is database replication configured and what is the backup retention period?",
        context=LONG_CONTEXT,
        token_budget=150,
        simulate_tier2_failure=False,
    )
    assert res.original_tokens > res.optimized_tokens
    assert res.reduction_percentage > 0
    assert res.route in ["FULL", "LIGHT"]
    assert res.trace.chunks_total > 0
    assert res.trace.chunks_pinned_critical >= 2  # System + Constraint
    assert res.trace.fallback_triggered is False
    assert res.trace.fallback_reason is None

    # Check stage latencies are logged
    assert res.trace.stage_latency_ms.chunking >= 0.0
    assert res.trace.stage_latency_ms.total > 0.0


def test_pipeline_graceful_fallback_on_tier2_failure():
    """
    CRITICAL TEST: When Tier-2 compression fails, the pipeline MUST catch the exception,
    log fallback_triggered=True and fallback_reason, and fall back to Tier-1 output.
    """
    res = run_pipeline(
        query="How is database replication configured and what is the backup retention period?",
        context=LONG_CONTEXT,
        token_budget=150,
        simulate_tier2_failure=True,  # Force Tier 2 failure
    )
    # The request should succeed without throwing an exception!
    assert res is not None
    assert res.trace.fallback_triggered is True
    assert res.trace.fallback_reason is not None
    assert "Tier 2 compression failed" in res.trace.fallback_reason
    assert res.optimized_tokens > 0
    assert len(res.optimized_context) > 0


def test_pipeline_skip_route():
    """When context is already within budget and minimal, route should be SKIP."""
    short_context = "System: Hello world. This is a short statement."
    res = run_pipeline(
        query="Hello",
        context=short_context,
        token_budget=200,  # budget much larger than context
    )
    assert res.route == "SKIP"
    assert res.trace.chunks_removed_irrelevant == 0
    assert res.trace.chunks_compressed == 0


def test_critical_info_survives_compression():
    """
    Design.md §8 & §10 Hard-Rule Check:
    Verify deterministically that critical instructions, negations ('MUST', 'DO NOT'),
    and constraints are 100% retained in the final optimized context.
    """
    res = run_pipeline(
        query="Explain the database backup retention schedule.",
        context=LONG_CONTEXT,
        token_budget=120,
    )
    optimized = res.optimized_context
    assert "System: You are an AI assistant" in optimized
    assert "MUST adhere to GDPR and SOC2" in optimized
    assert "DO NOT display plain-text credentials" in optimized
    assert "35 days" in optimized or "Database Replication" in optimized

