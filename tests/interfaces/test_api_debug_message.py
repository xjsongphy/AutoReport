"""Tests for ApiDebugMessage."""

from datetime import datetime
from autoreport.interfaces.types import ApiDebugMessage, MessageType


def test_api_debug_message_creation():
    """ApiDebugMessage should be created with required fields."""
    msg = ApiDebugMessage(
        model="claude-sonnet-4-20250514",
        tokens_in=1000,
        tokens_out=500,
        duration_ms=1500,
        status="success"
    )

    assert msg.type == MessageType.API_DEBUG
    assert msg.model == "claude-sonnet-4-20250514"
    assert msg.tokens_in == 1000
    assert msg.tokens_out == 500
    assert msg.duration_ms == 1500
    assert msg.status == "success"
    assert msg.error is None
    assert isinstance(msg.timestamp, datetime)


def test_api_debug_message_with_error():
    """ApiDebugMessage should support error status."""
    msg = ApiDebugMessage(
        model="claude-sonnet-4-20250514",
        tokens_in=1000,
        tokens_out=0,
        duration_ms=5000,
        status="error",
        error="Rate limit exceeded"
    )

    assert msg.status == "error"
    assert msg.error == "Rate limit exceeded"


def test_api_debug_message_default_timestamp():
    """ApiDebugMessage should have default timestamp."""
    msg = ApiDebugMessage(
        model="gpt-4",
        tokens_in=500,
        tokens_out=300,
        duration_ms=2000,
        status="success"
    )

    # Timestamp should be set automatically
    assert msg.timestamp is not None
    # Should be very recent (within last minute)
    assert (datetime.now() - msg.timestamp).total_seconds() < 60


def test_api_debug_message_serialization():
    """ApiDebugMessage should be serializable to dict."""
    msg = ApiDebugMessage(
        model="claude-sonnet-4-20250514",
        tokens_in=1000,
        tokens_out=500,
        duration_ms=1500,
        status="success"
    )

    # Model dump should work
    data = msg.model_dump()

    assert data["type"] == MessageType.API_DEBUG
    assert data["model"] == "claude-sonnet-4-20250514"
    assert data["tokens_in"] == 1000
    assert data["tokens_out"] == 500
    assert data["duration_ms"] == 1500
    assert data["status"] == "success"
