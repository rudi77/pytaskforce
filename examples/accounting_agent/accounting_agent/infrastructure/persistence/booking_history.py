"""
Booking History Persistence

GoBD-compliant storage of completed bookings with embedding-based
similarity search for RAG fallback.

Storage format: JSONL (append-only for immutability)
Index: In-memory embedding index for similarity search
"""

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import structlog

logger = structlog.get_logger(__name__)


class BookingHistory:
    """
    Booking history storage with semantic search support.

    Implements BookingHistoryProtocol.

    Storage:
    - JSONL file for append-only booking history (GoBD compliant)
    - In-memory embedding index for fast similarity search

    Each booking entry contains:
    - booking_id: Unique identifier
    - timestamp: ISO 8601 UTC timestamp
    - invoice_data: Original invoice information
    - booking_proposal: The accepted booking
    - confidence: Confidence score at time of booking
    - rule_id: Rule used (if rule-based)
    - is_hitl_correction: Whether this was a HITL correction
    - embedding: Description embedding for similarity search
    """

    def __init__(
        self,
        storage_path: str = ".taskforce_accounting/booking_history.jsonl",
        embedding_service: Optional[Any] = None,
    ):
        """
        Initialize booking history.

        Args:
            storage_path: Path to JSONL storage file
            embedding_service: EmbeddingProviderProtocol for similarity search
        """
        self._storage_path = Path(storage_path)
        self._embedding_service = embedding_service

        # In-memory index for similarity search
        self._bookings: list[dict[str, Any]] = []
        self._embeddings: list[list[float]] = []
        self._loaded = False

        # Ensure storage directory exists
        self._storage_path.parent.mkdir(parents=True, exist_ok=True)

    async def _ensure_loaded(self) -> None:
        """Load bookings from storage if not already loaded."""
        if self._loaded:
            return

        self._bookings = []
        self._embeddings = []

        if not self._storage_path.exists():
            self._loaded = True
            return

        try:
            with open(self._storage_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        booking = json.loads(line)
                        self._bookings.append(booking)
                        # Load pre-computed embedding if available
                        if "embedding" in booking:
                            self._embeddings.append(booking["embedding"])
                        else:
                            self._embeddings.append([])  # Placeholder
                    except json.JSONDecodeError:
                        logger.warning(
                            "booking_history.invalid_line",
                            line=line[:100],
                        )
                        continue

            logger.info(
                "booking_history.loaded",
                count=len(self._bookings),
            )
        except Exception as e:
            logger.error(
                "booking_history.load_error",
                error=str(e),
            )

        self._loaded = True

    async def save_booking(self, booking: dict[str, Any]) -> str:
        """
        Save a completed booking to history.

        Args:
            booking: Booking data including:
                - invoice_data: Invoice information
                - booking_proposal: Accepted booking
                - confidence: Confidence score
                - rule_id: Rule used (optional)
                - is_hitl_correction: Whether HITL corrected

        Returns:
            Unique booking ID
        """
        await self._ensure_loaded()

        booking_id = str(uuid.uuid4())
        timestamp = datetime.now(timezone.utc).isoformat()

        # Create searchable text for embedding
        search_text = self._create_search_text(booking)

        # Compute embedding if service available
        embedding = []
        if self._embedding_service and search_text:
            try:
                embedding = await self._embedding_service.embed_text(search_text)
            except Exception as e:
                logger.warning(
                    "booking_history.embedding_error",
                    error=str(e),
                )

        # Create record
        record = {
            "booking_id": booking_id,
            "timestamp": timestamp,
            "invoice_data": booking.get("invoice_data", {}),
            "booking_proposal": booking.get("booking_proposal", {}),
            "confidence": booking.get("confidence", 0.0),
            "rule_id": booking.get("rule_id"),
            "is_hitl_correction": booking.get("is_hitl_correction", False),
            "search_text": search_text,
            "embedding": embedding,
        }

        # Append to storage (GoBD: append-only)
        try:
            with open(self._storage_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.error(
                "booking_history.save_error",
                error=str(e),
            )
            raise

        # Update in-memory index
        self._bookings.append(record)
        self._embeddings.append(embedding)

        logger.info(
            "booking_history.saved",
            booking_id=booking_id,
            has_embedding=bool(embedding),
        )

        return booking_id

    async def search_similar(
        self,
        query: str,
        vendor_name: Optional[str] = None,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """
        Search for similar historical bookings.

        Uses semantic similarity on item descriptions.

        Args:
            query: Search query (item description or invoice text)
            vendor_name: Optional vendor name to filter by
            limit: Maximum number of results

        Returns:
            List of similar bookings with similarity scores
        """
        await self._ensure_loaded()

        if not self._bookings:
            return []

        results = []

        # If embedding service available, use semantic search
        if self._embedding_service:
            try:
                query_embedding = await self._embedding_service.embed_text(query)

                for i, (booking, embedding) in enumerate(
                    zip(self._bookings, self._embeddings)
                ):
                    # Skip if no embedding
                    if not embedding:
                        continue

                    # Filter by vendor if specified
                    if vendor_name:
                        booking_vendor = (
                            booking.get("invoice_data", {}).get("supplier_name", "")
                        )
                        if vendor_name.lower() not in booking_vendor.lower():
                            continue

                    # Calculate similarity
                    similarity = self._embedding_service.cosine_similarity(
                        query_embedding, embedding
                    )

                    results.append({
                        "booking": booking,
                        "similarity": similarity,
                    })

                # Sort by similarity
                results.sort(key=lambda x: x["similarity"], reverse=True)
                results = results[:limit]

                logger.debug(
                    "booking_history.semantic_search",
                    query=query[:50],
                    results=len(results),
                )

                return [
                    {
                        **r["booking"],
                        "similarity_score": r["similarity"],
                    }
                    for r in results
                ]

            except Exception as e:
                logger.warning(
                    "booking_history.semantic_search_error",
                    error=str(e),
                )
                # Fall back to keyword search

        # Fallback: Simple keyword search
        query_lower = query.lower()
        for booking in self._bookings:
            # Filter by vendor if specified
            if vendor_name:
                booking_vendor = (
                    booking.get("invoice_data", {}).get("supplier_name", "")
                )
                if vendor_name.lower() not in booking_vendor.lower():
                    continue

            # Check search text
            search_text = booking.get("search_text", "").lower()
            if query_lower in search_text:
                results.append({
                    **booking,
                    "similarity_score": 0.7,  # Keyword match score
                })

        results = results[:limit]

        logger.debug(
            "booking_history.keyword_search",
            query=query[:50],
            results=len(results),
        )

        return results

    async def get_booking_by_id(
        self, booking_id: str
    ) -> Optional[dict[str, Any]]:
        """
        Get a specific booking by ID.

        Args:
            booking_id: Unique booking identifier

        Returns:
            Booking data or None if not found
        """
        await self._ensure_loaded()

        for booking in self._bookings:
            if booking.get("booking_id") == booking_id:
                return booking

        return None

    async def get_vendor_history(
        self,
        vendor_name: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """
        Get booking history for a specific vendor.

        Args:
            vendor_name: Vendor name to search for
            limit: Maximum number of results

        Returns:
            List of bookings for this vendor, newest first
        """
        await self._ensure_loaded()

        vendor_lower = vendor_name.lower()
        results = []

        for booking in reversed(self._bookings):  # Newest first
            booking_vendor = (
                booking.get("invoice_data", {}).get("supplier_name", "")
            )
            if vendor_lower in booking_vendor.lower():
                results.append(booking)
                if len(results) >= limit:
                    break

        logger.debug(
            "booking_history.vendor_history",
            vendor=vendor_name,
            results=len(results),
        )

        return results

    async def is_new_vendor(self, vendor_name: str) -> bool:
        """
        Check if a vendor is new (no previous bookings).

        Args:
            vendor_name: Vendor name to check

        Returns:
            True if no previous bookings from this vendor
        """
        history = await self.get_vendor_history(vendor_name, limit=1)
        return len(history) == 0

    def _create_search_text(self, booking: dict[str, Any]) -> str:
        """Create searchable text from booking data."""
        parts = []

        invoice_data = booking.get("invoice_data", {})
        parts.append(invoice_data.get("supplier_name", ""))

        # Add line item descriptions
        for item in invoice_data.get("line_items", []):
            parts.append(item.get("description", ""))

        booking_proposal = booking.get("booking_proposal", {})
        parts.append(booking_proposal.get("description", ""))
        parts.append(booking_proposal.get("debit_account_name", ""))

        return " ".join(filter(None, parts))

    def set_embedding_service(self, embedding_service: Any) -> None:
        """
        Set or update the embedding service.

        Args:
            embedding_service: EmbeddingProviderProtocol implementation
        """
        self._embedding_service = embedding_service

    async def get_stats(self) -> dict[str, Any]:
        """
        Get statistics about booking history.

        Returns:
            Statistics dict with counts and insights
        """
        await self._ensure_loaded()

        total = len(self._bookings)
        hitl_corrections = sum(
            1 for b in self._bookings if b.get("is_hitl_correction", False)
        )
        with_embeddings = sum(1 for e in self._embeddings if e)

        # Count unique vendors
        vendors = set()
        for b in self._bookings:
            vendor = b.get("invoice_data", {}).get("supplier_name", "")
            if vendor:
                vendors.add(vendor.lower())

        return {
            "total_bookings": total,
            "hitl_corrections": hitl_corrections,
            "auto_bookings": total - hitl_corrections,
            "unique_vendors": len(vendors),
            "with_embeddings": with_embeddings,
        }
