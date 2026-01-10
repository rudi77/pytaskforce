"""
Unit tests for LoggerProtocol interface.

Tests verify that structlog loggers conform to LoggerProtocol
and that the protocol can be used for dependency injection.
"""

from typing import Any

import structlog

from taskforce.core.interfaces.logging import LoggerProtocol


def test_structlog_logger_conforms_to_protocol() -> None:
    """Verify that structlog logger conforms to LoggerProtocol."""
    logger = structlog.get_logger().bind(component="test")
    
    # Type check: structlog logger should be compatible with LoggerProtocol
    protocol_logger: LoggerProtocol = logger
    
    # Verify all protocol methods exist and are callable
    assert hasattr(protocol_logger, "info")
    assert hasattr(protocol_logger, "warning")
    assert hasattr(protocol_logger, "error")
    assert hasattr(protocol_logger, "debug")
    
    # Verify methods can be called (no exceptions)
    protocol_logger.info("test_event", key="value")
    protocol_logger.warning("test_warning", key="value")
    protocol_logger.error("test_error", key="value")
    protocol_logger.debug("test_debug", key="value")


def test_protocol_accepts_kwargs() -> None:
    """Verify that protocol methods accept arbitrary keyword arguments."""
    logger = structlog.get_logger().bind(component="test")
    protocol_logger: LoggerProtocol = logger
    
    # Test with various keyword arguments
    protocol_logger.info("event", key1="value1", key2=123, key3=True)
    protocol_logger.warning("event", session_id="test-123", error="test error")
    protocol_logger.error("event", tool="test_tool", args={"param": "value"})
    protocol_logger.debug("event", iteration=1, step=5, max_steps=10)


def test_protocol_with_mock_logger() -> None:
    """Test that a mock logger can implement LoggerProtocol."""
    
    class MockLogger:
        """Mock logger implementation for testing."""
        
        def __init__(self) -> None:
            self.logs: list[dict[str, Any]] = []
        
        def info(self, event: str, **kwargs: Any) -> None:
            self.logs.append({"level": "info", "event": event, **kwargs})
        
        def warning(self, event: str, **kwargs: Any) -> None:
            self.logs.append({"level": "warning", "event": event, **kwargs})
        
        def error(self, event: str, **kwargs: Any) -> None:
            self.logs.append({"level": "error", "event": event, **kwargs})
        
        def debug(self, event: str, **kwargs: Any) -> None:
            self.logs.append({"level": "debug", "event": event, **kwargs})
    
    # Mock logger should conform to protocol
    mock_logger = MockLogger()
    protocol_logger: LoggerProtocol = mock_logger
    
    # Test all methods
    protocol_logger.info("test_info", key="value")
    protocol_logger.warning("test_warning", key="value")
    protocol_logger.error("test_error", key="value")
    protocol_logger.debug("test_debug", key="value")
    
    # Verify logs were recorded
    assert len(mock_logger.logs) == 4
    assert mock_logger.logs[0]["level"] == "info"
    assert mock_logger.logs[0]["event"] == "test_info"
    assert mock_logger.logs[0]["key"] == "value"
    assert mock_logger.logs[1]["level"] == "warning"
    assert mock_logger.logs[2]["level"] == "error"
    assert mock_logger.logs[3]["level"] == "debug"
