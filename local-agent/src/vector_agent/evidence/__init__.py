"""Evidence ingestion boundaries; collectors cannot directly assert diagnostic truth."""

from vector_agent.evidence.validation import ValidatedProbeObservation, ingest_probe_response

__all__ = ["ValidatedProbeObservation", "ingest_probe_response"]
