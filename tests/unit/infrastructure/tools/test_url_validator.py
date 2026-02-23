"""
Unit tests for URL Validator (SSRF protection)

Tests the validate_url_for_ssrf function that blocks requests to
private/internal network addresses, cloud metadata endpoints, etc.
"""

from unittest.mock import patch

from taskforce.infrastructure.tools.native.url_validator import validate_url_for_ssrf


class TestValidateUrlForSsrf:
    """Test suite for SSRF URL validation."""

    # -----------------------------------------------------------------------
    # Valid (safe) URLs
    # -----------------------------------------------------------------------

    def test_valid_https_url(self):
        """Test that a standard HTTPS URL passes validation."""
        is_safe, error = validate_url_for_ssrf("https://example.com/page")
        assert is_safe is True
        assert error is None

    def test_valid_http_url(self):
        """Test that a standard HTTP URL passes validation."""
        is_safe, error = validate_url_for_ssrf("http://example.com")
        assert is_safe is True
        assert error is None

    def test_valid_url_with_port(self):
        """Test that a URL with a port passes validation."""
        is_safe, error = validate_url_for_ssrf("https://example.com:8080/api")
        assert is_safe is True
        assert error is None

    def test_valid_url_with_path_and_query(self):
        """Test a URL with path and query parameters."""
        is_safe, error = validate_url_for_ssrf(
            "https://api.example.com/v1/search?q=hello&limit=10"
        )
        assert is_safe is True
        assert error is None

    # -----------------------------------------------------------------------
    # Missing / invalid scheme
    # -----------------------------------------------------------------------

    def test_missing_scheme(self):
        """Test that a URL without a scheme is rejected."""
        is_safe, error = validate_url_for_ssrf("example.com/page")
        assert is_safe is False
        assert "scheme" in error.lower()

    def test_unsupported_scheme_ftp(self):
        """Test that FTP scheme is rejected."""
        is_safe, error = validate_url_for_ssrf("ftp://files.example.com/data.csv")
        assert is_safe is False
        assert "ftp" in error.lower()

    def test_unsupported_scheme_file(self):
        """Test that file:// scheme is rejected."""
        is_safe, error = validate_url_for_ssrf("file:///etc/passwd")
        assert is_safe is False
        assert "file" in error.lower()

    def test_unsupported_scheme_javascript(self):
        """Test that javascript: scheme is rejected."""
        is_safe, error = validate_url_for_ssrf("javascript:alert(1)")
        assert is_safe is False
        assert "javascript" in error.lower()

    # -----------------------------------------------------------------------
    # Missing hostname
    # -----------------------------------------------------------------------

    def test_missing_hostname(self):
        """Test that a URL without a hostname is rejected."""
        is_safe, error = validate_url_for_ssrf("http://")
        assert is_safe is False
        assert "hostname" in error.lower()

    # -----------------------------------------------------------------------
    # Private / internal IP addresses (RFC 1918)
    # -----------------------------------------------------------------------

    def test_loopback_ipv4(self):
        """Test that 127.0.0.1 (loopback) is blocked."""
        is_safe, error = validate_url_for_ssrf("http://127.0.0.1/admin")
        assert is_safe is False
        assert "private" in error.lower() or "reserved" in error.lower()

    def test_localhost(self):
        """Test that 'localhost' resolving to 127.0.0.1 is blocked."""
        # localhost resolves to 127.0.0.1 on most systems
        is_safe, error = validate_url_for_ssrf("http://localhost/admin")
        assert is_safe is False
        assert "private" in error.lower() or "reserved" in error.lower()

    def test_private_10_network(self):
        """Test that 10.x.x.x private addresses are blocked."""
        is_safe, error = validate_url_for_ssrf("http://10.0.0.1/internal")
        assert is_safe is False
        assert "private" in error.lower()

    def test_private_172_16_network(self):
        """Test that 172.16.x.x private addresses are blocked."""
        is_safe, error = validate_url_for_ssrf("http://172.16.0.1/internal")
        assert is_safe is False
        assert "private" in error.lower()

    def test_private_192_168_network(self):
        """Test that 192.168.x.x private addresses are blocked."""
        is_safe, error = validate_url_for_ssrf("http://192.168.1.1/router")
        assert is_safe is False
        assert "private" in error.lower()

    # -----------------------------------------------------------------------
    # Link-local addresses
    # -----------------------------------------------------------------------

    def test_link_local_169_254(self):
        """Test that 169.254.x.x (link-local / AWS metadata) is blocked."""
        is_safe, error = validate_url_for_ssrf("http://169.254.169.254/latest/meta-data/")
        assert is_safe is False
        assert "private" in error.lower() or "reserved" in error.lower()

    # -----------------------------------------------------------------------
    # Cloud metadata endpoints
    # -----------------------------------------------------------------------

    def test_google_metadata_internal(self):
        """Test that metadata.google.internal is blocked."""
        is_safe, error = validate_url_for_ssrf(
            "http://metadata.google.internal/computeMetadata/v1/"
        )
        assert is_safe is False
        assert "blocked" in error.lower() or "metadata" in error.lower()

    def test_google_metadata_goog(self):
        """Test that metadata.goog is blocked."""
        is_safe, error = validate_url_for_ssrf("http://metadata.goog/computeMetadata/v1/")
        assert is_safe is False
        assert "blocked" in error.lower() or "metadata" in error.lower()

    # -----------------------------------------------------------------------
    # DNS resolution failure
    # -----------------------------------------------------------------------

    def test_dns_resolution_failure_passes(self):
        """Test that DNS resolution failure allows the URL through.

        The validator lets the actual HTTP client handle DNS failures
        rather than blocking the request.
        """
        import socket as _socket

        with patch(
            "taskforce.infrastructure.tools.native.url_validator.socket.getaddrinfo",
            side_effect=_socket.gaierror("Name resolution failed"),
        ):
            is_safe, error = validate_url_for_ssrf("https://nonexistent.example.invalid")
            assert is_safe is True
            assert error is None

    # -----------------------------------------------------------------------
    # Hostname resolving to private IP via DNS (mocked)
    # -----------------------------------------------------------------------

    def test_hostname_resolving_to_private_ip_blocked(self):
        """Test that a hostname resolving to a private IP is blocked."""
        fake_addrinfo = [
            (2, 1, 6, "", ("10.0.0.5", 0)),  # AF_INET, SOCK_STREAM
        ]
        with patch(
            "taskforce.infrastructure.tools.native.url_validator.socket.getaddrinfo",
            return_value=fake_addrinfo,
        ):
            is_safe, error = validate_url_for_ssrf("https://evil-redirect.example.com")
            assert is_safe is False
            assert "private" in error.lower()

    def test_hostname_resolving_to_loopback_blocked(self):
        """Test that a hostname resolving to loopback is blocked."""
        fake_addrinfo = [
            (2, 1, 6, "", ("127.0.0.1", 0)),
        ]
        with patch(
            "taskforce.infrastructure.tools.native.url_validator.socket.getaddrinfo",
            return_value=fake_addrinfo,
        ):
            is_safe, error = validate_url_for_ssrf("https://evil.example.com")
            assert is_safe is False
            assert "private" in error.lower() or "reserved" in error.lower()

    def test_hostname_resolving_to_public_ip_passes(self):
        """Test that a hostname resolving to a public IP passes."""
        fake_addrinfo = [
            (2, 1, 6, "", ("93.184.216.34", 0)),  # example.com public IP
        ]
        with patch(
            "taskforce.infrastructure.tools.native.url_validator.socket.getaddrinfo",
            return_value=fake_addrinfo,
        ):
            is_safe, error = validate_url_for_ssrf("https://safe.example.com")
            assert is_safe is True
            assert error is None

    # -----------------------------------------------------------------------
    # Edge cases
    # -----------------------------------------------------------------------

    def test_case_insensitive_blocked_host(self):
        """Test that blocked host matching is case-insensitive."""
        is_safe, error = validate_url_for_ssrf(
            "http://METADATA.GOOGLE.INTERNAL/computeMetadata/v1/"
        )
        assert is_safe is False
        assert "blocked" in error.lower() or "metadata" in error.lower()

    def test_empty_string(self):
        """Test that an empty string fails validation."""
        is_safe, error = validate_url_for_ssrf("")
        assert is_safe is False

    def test_url_with_userinfo(self):
        """Test a URL with user info in the authority."""
        fake_addrinfo = [
            (2, 1, 6, "", ("93.184.216.34", 0)),
        ]
        with patch(
            "taskforce.infrastructure.tools.native.url_validator.socket.getaddrinfo",
            return_value=fake_addrinfo,
        ):
            is_safe, error = validate_url_for_ssrf("https://user:pass@example.com/path")
            assert is_safe is True
            assert error is None
