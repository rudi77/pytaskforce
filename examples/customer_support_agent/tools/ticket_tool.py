"""
Custom Ticket Management Tool for Customer Support Agent.

This tool demonstrates how to create a custom tool that integrates
with Taskforce's Clean Architecture. It simulates a simple ticket
management system.

Usage:
    This tool is automatically loaded when specified in the agent's
    YAML configuration or tool allowlist.
"""

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import structlog

from taskforce.core.interfaces.tools import ToolProtocol

logger = structlog.get_logger(__name__)


class TicketTool:
    """
    Ticket management tool for customer support operations.

    Provides capabilities to create, read, update, and list support tickets
    with a simple file-based persistence layer.

    Operations:
    - create_ticket: Create a new support ticket
    - get_ticket: Retrieve ticket details by ID
    - update_ticket: Update ticket status or add notes
    - list_tickets: List all tickets (optionally filtered by status)
    - search_tickets: Search tickets by customer email or keywords
    """

    def __init__(self, tickets_dir: str = ".taskforce_tickets"):
        """
        Initialize TicketTool with storage directory.

        Args:
            tickets_dir: Directory to store ticket JSON files
        """
        self.tickets_dir = Path(tickets_dir)
        self.tickets_dir.mkdir(parents=True, exist_ok=True)
        logger.info("ticket_tool_initialized", tickets_dir=str(self.tickets_dir))

    @property
    def name(self) -> str:
        """Tool name used in LLM function calls."""
        return "ticket_manager"

    @property
    def description(self) -> str:
        """Tool description for LLM understanding."""
        return (
            "Manage customer support tickets. Can create, read, update, list, "
            "and search tickets. Each ticket has an ID, customer email, subject, "
            "description, status (open/in_progress/resolved/closed), priority "
            "(low/medium/high/critical), and creation/update timestamps."
        )

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        """JSON Schema for tool parameters."""
        return {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": [
                        "create_ticket",
                        "get_ticket",
                        "update_ticket",
                        "list_tickets",
                        "search_tickets",
                    ],
                    "description": "Operation to perform",
                },
                "ticket_id": {
                    "type": "string",
                    "description": "Ticket ID (required for get_ticket, update_ticket)",
                },
                "customer_email": {
                    "type": "string",
                    "description": "Customer email address (required for create_ticket)",
                },
                "subject": {
                    "type": "string",
                    "description": "Ticket subject (required for create_ticket)",
                },
                "description": {
                    "type": "string",
                    "description": "Ticket description (required for create_ticket)",
                },
                "priority": {
                    "type": "string",
                    "enum": ["low", "medium", "high", "critical"],
                    "description": "Ticket priority (optional, defaults to 'medium')",
                },
                "status": {
                    "type": "string",
                    "enum": ["open", "in_progress", "resolved", "closed"],
                    "description": "Ticket status (for update_ticket or list_tickets filter)",
                },
                "notes": {
                    "type": "string",
                    "description": "Notes to add when updating ticket",
                },
                "search_query": {
                    "type": "string",
                    "description": "Search query for search_tickets (email or keywords)",
                },
            },
            "required": ["operation"],
        }

    def validate_parameters(self, params: Dict[str, Any]) -> bool:
        """
        Validate parameters for the operation.

        Args:
            params: Parameters dictionary

        Returns:
            True if parameters are valid

        Raises:
            ValueError: If required parameters are missing
        """
        operation = params.get("operation")

        if operation == "create_ticket":
            required = ["customer_email", "subject", "description"]
            missing = [field for field in required if not params.get(field)]
            if missing:
                raise ValueError(f"Missing required fields for create_ticket: {missing}")

        elif operation in ["get_ticket", "update_ticket"]:
            if not params.get("ticket_id"):
                raise ValueError(f"{operation} requires ticket_id parameter")

        elif operation == "search_tickets":
            if not params.get("search_query"):
                raise ValueError("search_tickets requires search_query parameter")

        return True

    async def execute(self, **params) -> Dict[str, Any]:
        """
        Execute the tool operation.

        Args:
            **params: Operation parameters matching parameters_schema

        Returns:
            Dictionary with operation results and status

        Raises:
            ValueError: If parameters are invalid or operation fails
        """
        try:
            # Validate parameters
            self.validate_parameters(params)

            operation = params["operation"]

            # Dispatch to appropriate handler
            if operation == "create_ticket":
                return await self._create_ticket(params)
            elif operation == "get_ticket":
                return await self._get_ticket(params["ticket_id"])
            elif operation == "update_ticket":
                return await self._update_ticket(params)
            elif operation == "list_tickets":
                return await self._list_tickets(params.get("status"))
            elif operation == "search_tickets":
                return await self._search_tickets(params["search_query"])
            else:
                raise ValueError(f"Unknown operation: {operation}")

        except Exception as e:
            logger.error(
                "ticket_tool_execution_failed",
                operation=params.get("operation"),
                error=str(e),
                error_type=type(e).__name__,
            )
            return {
                "success": False,
                "error": str(e),
                "error_type": type(e).__name__,
            }

    async def _create_ticket(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new support ticket."""
        ticket_id = str(uuid.uuid4())[:8]  # Short UUID for readability
        timestamp = datetime.utcnow().isoformat()

        ticket = {
            "ticket_id": ticket_id,
            "customer_email": params["customer_email"],
            "subject": params["subject"],
            "description": params["description"],
            "priority": params.get("priority", "medium"),
            "status": "open",
            "created_at": timestamp,
            "updated_at": timestamp,
            "notes": [],
        }

        # Save to file
        ticket_file = self.tickets_dir / f"{ticket_id}.json"
        with open(ticket_file, "w") as f:
            json.dump(ticket, f, indent=2)

        logger.info(
            "ticket_created",
            ticket_id=ticket_id,
            customer_email=params["customer_email"],
            priority=ticket["priority"],
        )

        return {
            "success": True,
            "message": f"Ticket created successfully: {ticket_id}",
            "ticket": ticket,
        }

    async def _get_ticket(self, ticket_id: str) -> Dict[str, Any]:
        """Retrieve a ticket by ID."""
        ticket_file = self.tickets_dir / f"{ticket_id}.json"

        if not ticket_file.exists():
            return {
                "success": False,
                "error": f"Ticket not found: {ticket_id}",
            }

        with open(ticket_file) as f:
            ticket = json.load(f)

        logger.debug("ticket_retrieved", ticket_id=ticket_id)

        return {
            "success": True,
            "ticket": ticket,
        }

    async def _update_ticket(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Update a ticket's status or add notes."""
        ticket_id = params["ticket_id"]
        ticket_file = self.tickets_dir / f"{ticket_id}.json"

        if not ticket_file.exists():
            return {
                "success": False,
                "error": f"Ticket not found: {ticket_id}",
            }

        with open(ticket_file) as f:
            ticket = json.load(f)

        # Update status if provided
        if "status" in params:
            old_status = ticket["status"]
            ticket["status"] = params["status"]
            logger.info(
                "ticket_status_updated",
                ticket_id=ticket_id,
                old_status=old_status,
                new_status=params["status"],
            )

        # Add notes if provided
        if "notes" in params:
            note_entry = {
                "timestamp": datetime.utcnow().isoformat(),
                "text": params["notes"],
            }
            ticket["notes"].append(note_entry)

        # Update timestamp
        ticket["updated_at"] = datetime.utcnow().isoformat()

        # Save updated ticket
        with open(ticket_file, "w") as f:
            json.dump(ticket, f, indent=2)

        return {
            "success": True,
            "message": f"Ticket updated: {ticket_id}",
            "ticket": ticket,
        }

    async def _list_tickets(self, status_filter: Optional[str] = None) -> Dict[str, Any]:
        """List all tickets, optionally filtered by status."""
        tickets = []

        for ticket_file in self.tickets_dir.glob("*.json"):
            with open(ticket_file) as f:
                ticket = json.load(f)

            # Apply status filter if specified
            if status_filter and ticket["status"] != status_filter:
                continue

            tickets.append(ticket)

        # Sort by creation date (newest first)
        tickets.sort(key=lambda t: t["created_at"], reverse=True)

        logger.debug(
            "tickets_listed",
            total_count=len(tickets),
            status_filter=status_filter,
        )

        return {
            "success": True,
            "count": len(tickets),
            "tickets": tickets,
            "filter": {"status": status_filter} if status_filter else None,
        }

    async def _search_tickets(self, query: str) -> Dict[str, Any]:
        """Search tickets by customer email or keywords in subject/description."""
        query_lower = query.lower()
        matching_tickets = []

        for ticket_file in self.tickets_dir.glob("*.json"):
            with open(ticket_file) as f:
                ticket = json.load(f)

            # Search in email, subject, and description
            searchable_text = " ".join(
                [
                    ticket["customer_email"],
                    ticket["subject"],
                    ticket["description"],
                ]
            ).lower()

            if query_lower in searchable_text:
                matching_tickets.append(ticket)

        # Sort by creation date (newest first)
        matching_tickets.sort(key=lambda t: t["created_at"], reverse=True)

        logger.debug(
            "tickets_searched",
            query=query,
            results_count=len(matching_tickets),
        )

        return {
            "success": True,
            "query": query,
            "count": len(matching_tickets),
            "tickets": matching_tickets,
        }
