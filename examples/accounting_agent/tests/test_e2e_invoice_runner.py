"""
End-to-End Invoice Test Runner for Accounting Agent

Runs invoice scenarios through the accounting agent and validates results.
Supports automated HITL responses for testing.

Usage:
    # Run all scenarios (with verbose tool output, no debug logs)
    uv run python examples/accounting_agent/tests/test_e2e_invoice_runner.py

    # Run with debug logging (shows LLM calls, tool execution, etc.)
    uv run python examples/accounting_agent/tests/test_e2e_invoice_runner.py --debug

    # Run specific scenario
    uv run python examples/accounting_agent/tests/test_e2e_invoice_runner.py --scenario IN-DE-001

    # Interactive mode (pause for HITL)
    uv run python examples/accounting_agent/tests/test_e2e_invoice_runner.py --interactive

    # Quiet mode (minimal output)
    uv run python examples/accounting_agent/tests/test_e2e_invoice_runner.py --quiet

    # Combine flags
    uv run python examples/accounting_agent/tests/test_e2e_invoice_runner.py --scenario IN-DE-002 --interactive --debug

Options:
    --scenario, -s    Run specific scenario by ID (e.g., IN-DE-001)
    --interactive, -i Pause for manual HITL responses
    --quiet, -q       Minimal output (no tool arguments/results)
    --debug, -d       Enable debug logging (LLM calls, etc.)
    --incoming-only   Only run incoming invoice scenarios
    --outgoing-only   Only run outgoing invoice scenarios
    --output, -o      Output file for results (default: test_results.json)
"""

import asyncio
import io
import json
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

# Fix Windows console encoding for Unicode characters (box drawing, emojis)
# line_buffering=True ensures output is flushed after each newline (required for live streaming)
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace', line_buffering=True)

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from test_scenarios_invoice import SCENARIOS, TestInvoice, InvoiceDirection


@dataclass
class TestResult:
    """Result of a single test scenario."""
    scenario_id: str
    scenario_name: str
    success: bool
    prompt: str
    agent_response: str
    tools_called: list[str]
    hitl_triggered: bool
    hitl_response: Optional[str]
    detected_debit_account: Optional[str]
    detected_credit_account: Optional[str]
    expected_debit_account: Optional[str]
    expected_credit_account: Optional[str]
    account_match: bool
    error: Optional[str]
    duration_ms: int
    booking_proposals: Optional[list[dict]] = None  # Captured from semantic_rule_engine results


class AccountingAgentTestRunner:
    """
    Automated test runner for accounting agent scenarios.

    Handles HITL responses automatically for testing.
    """

    def __init__(
        self,
        plugin_path: str = "examples/accounting_agent",
        profile: str = "accounting_agent",
        interactive: bool = False,
        auto_confirm_hitl: bool = True,
        verbose: bool = True,
        fresh_agent_per_scenario: bool = True,
    ):
        """
        Initialize test runner.

        Args:
            plugin_path: Path to accounting agent plugin
            profile: Profile name
            interactive: If True, pause for manual HITL responses
            auto_confirm_hitl: If True, auto-confirm HITL requests
            verbose: If True, show detailed tool call info
            fresh_agent_per_scenario: If True, create new agent per scenario
                                      to avoid MCP cancel scope issues
        """
        self.plugin_path = plugin_path
        self.profile = profile
        self.interactive = interactive
        self.auto_confirm_hitl = auto_confirm_hitl
        self.verbose = verbose
        self.fresh_agent_per_scenario = fresh_agent_per_scenario
        self.results: list[TestResult] = []

    async def setup(self) -> None:
        """Initialize the agent and executor."""
        from taskforce.application.factory import AgentFactory
        from taskforce.application.executor import AgentExecutor

        self.factory = AgentFactory()
        self.executor = AgentExecutor()

        # Only create shared agent if not using fresh agents per scenario
        if not self.fresh_agent_per_scenario:
            self.agent = await self.factory.create_agent_with_plugin(
                plugin_path=self.plugin_path,
                profile=self.profile,
            )
        else:
            self.agent = None

        print(f"Agent initialized with profile: {self.profile}")
        print(f"Plugin: {self.plugin_path}")
        print(f"Fresh agent per scenario: {self.fresh_agent_per_scenario}")

    async def _create_fresh_agent(self):
        """Create a fresh agent for the current scenario."""
        return await self.factory.create_agent_with_plugin(
            plugin_path=self.plugin_path,
            profile=self.profile,
        )

    async def run_scenario(self, scenario: TestInvoice) -> TestResult:
        """
        Run a single test scenario.

        Args:
            scenario: Test invoice scenario

        Returns:
            TestResult with outcome
        """
        print(f"\n{'='*60}")
        print(f"SCENARIO: {scenario.scenario_id} - {scenario.scenario_name}")
        print(f"{'='*60}")

        prompt = scenario.to_prompt()
        print(f"\nPrompt:\n{prompt[:200]}...")

        start_time = datetime.now()
        tools_called: list[str] = []
        hitl_triggered = False
        hitl_response: Optional[str] = None
        agent_response = ""
        error: Optional[str] = None
        booking_proposals: list[dict] = []  # Capture from semantic_rule_engine results
        pending_hitl_review: Optional[dict] = None  # Capture HITL review data for auto rule learning

        # Create fresh agent if configured (avoids MCP cancel scope issues)
        scenario_agent = None
        if self.fresh_agent_per_scenario:
            scenario_agent = await self._create_fresh_agent()
        else:
            scenario_agent = self.agent

        try:
            # Create unique session for this test
            session_id = f"test-{scenario.scenario_id}-{datetime.now().strftime('%H%M%S')}"

            # Execute mission with streaming to capture tool calls
            async for update in self.executor.execute_mission_streaming(
                mission=prompt,
                profile=self.profile,
                session_id=session_id,
                agent=scenario_agent,
                plugin_path=self.plugin_path,
            ):
                event_type = update.event_type

                if event_type == "tool_call":
                    tool_name = update.details.get("tool", "unknown")
                    tools_called.append(tool_name)
                    # Note: StreamEvent uses "args" not "arguments"
                    args = update.details.get("args", {})
                    if self.verbose:
                        print(f"\n  ┌─ 🔧 TOOL CALL: {tool_name}")
                        self._print_tool_args(tool_name, args)
                    else:
                        print(f"  🔧 {tool_name}")

                elif event_type == "tool_result":
                    tool_name = update.details.get("tool", "unknown")
                    success = update.details.get("success", True)
                    # Note: StreamEvent uses "output" not "result"
                    result = update.details.get("output", {})
                    # Also get args for context
                    result_args = update.details.get("args", {})
                    status = "✅" if success else "❌"
                    if self.verbose:
                        print(f"  └─ {status} RESULT: {tool_name}")
                        self._print_tool_result(tool_name, result, success)
                    else:
                        print(f"  {status} {tool_name}")

                    # Capture booking proposals from semantic_rule_engine
                    if tool_name == "semantic_rule_engine" and success:
                        result_data = result
                        if isinstance(result_data, str):
                            try:
                                result_data = json.loads(result_data)
                            except (json.JSONDecodeError, TypeError) as e:
                                if self.verbose:
                                    print(f"       ⚠️ JSON parse error: {e}")
                                    print(f"       Raw result (first 200 chars): {str(result)[:200]}")
                                result_data = {}
                        if isinstance(result_data, dict):
                            proposals = result_data.get("booking_proposals", [])
                            if proposals:
                                booking_proposals.extend(proposals)
                                if self.verbose:
                                    print(f"       📋 Captured {len(proposals)} booking proposals")
                            elif self.verbose:
                                bp_value = result_data.get("booking_proposals", "MISSING")
                                print(f"       ⚠️ booking_proposals empty or missing. Value: {type(bp_value).__name__}={bp_value}")

                    # Capture HITL review data for auto rule learning
                    if tool_name == "hitl_review" and success:
                        # Parse result - might be dict or JSON string
                        result_data = result
                        if isinstance(result_data, str):
                            try:
                                result_data = json.loads(result_data)
                            except (json.JSONDecodeError, TypeError):
                                result_data = {}
                        if not isinstance(result_data, dict):
                            result_data = {}

                        if self.verbose:
                            print(f"       🔍 HITL result status: {result_data.get('status')}")

                        if result_data.get("status") == "pending":
                            # Store HITL review data for later rule learning
                            pending_hitl_review = {
                                "review_id": result_data.get("review_id"),
                                "invoice_data": result_args.get("invoice_data", {}),
                                "booking_proposal": result_args.get("booking_proposal", {}),
                            }
                            if self.verbose:
                                print(f"       📝 Captured HITL review: {pending_hitl_review.get('review_id')}")

                elif event_type == "ask_user":
                    hitl_triggered = True
                    question = update.details.get("question", "")
                    options = update.details.get("options", [])
                    print(f"\n  ╔{'═'*56}╗")
                    print(f"  ║ ❓ HITL REQUEST{' '*40}║")
                    print(f"  ╟{'─'*56}╢")
                    # Word wrap question
                    for line in self._wrap_text(question, 54):
                        print(f"  ║ {line:<54} ║")
                    if options:
                        print(f"  ╟{'─'*56}╢")
                        for i, opt in enumerate(options, 1):
                            opt_text = opt[:52] if len(opt) > 52 else opt
                            print(f"  ║ {i}. {opt_text:<51} ║")
                    print(f"  ╚{'═'*56}╝")

                    if self.interactive:
                        # Wait for manual input
                        hitl_response = input("  Your response: ").strip()
                    elif self.auto_confirm_hitl:
                        # Auto-confirm for testing - use expected account from scenario
                        expected_account = scenario.expected_debit_account or "4930"
                        hitl_response = f"Bestätigen mit Konto {expected_account}"
                        print(f"  → Auto-response: {hitl_response}")

                    # Resume agent execution with user's response
                    # The new planning_strategy resume mechanism handles this
                    if hitl_response:
                        print(f"  → Resuming agent with response: {hitl_response}")
                        # Continue agent execution with the user's response as the new mission
                        # The session_id is preserved, so the agent will resume from paused state
                        async for resume_update in self.executor.execute_mission_streaming(
                            mission=hitl_response,
                            profile=self.profile,
                            session_id=session_id,
                            agent=scenario_agent,
                            plugin_path=self.plugin_path,
                        ):
                            resume_event_type = resume_update.event_type

                            if resume_event_type == "tool_call":
                                tool_name = resume_update.details.get("tool", "unknown")
                                tools_called.append(tool_name)
                                args = resume_update.details.get("args", {})
                                if self.verbose:
                                    print(f"\n  ┌─ 🔧 TOOL CALL: {tool_name}")
                                    self._print_tool_args(tool_name, args)
                                else:
                                    print(f"  🔧 {tool_name}")

                            elif resume_event_type == "tool_result":
                                tool_name = resume_update.details.get("tool", "unknown")
                                success = resume_update.details.get("success", True)
                                result = resume_update.details.get("output", {})
                                status = "✅" if success else "❌"
                                if self.verbose:
                                    print(f"  └─ {status} RESULT: {tool_name}")
                                    self._print_tool_result(tool_name, result, success)
                                else:
                                    print(f"  {status} {tool_name}")

                            elif resume_event_type == "final_answer":
                                agent_response = resume_update.details.get("content", "")

                            elif resume_event_type == "llm_token":
                                token = resume_update.details.get("content", "")
                                agent_response += token

                            elif resume_event_type == "ask_user":
                                # Nested ask_user - for simplicity, auto-confirm
                                nested_question = resume_update.details.get("question", "")
                                print(f"  ⚠️ Nested HITL request (auto-confirming): {nested_question[:80]}...")
                                # Note: Would need recursive handling for full support

                elif event_type == "plan_updated":
                    action = update.details.get("action", "unknown")
                    plan = update.details.get("plan", "")
                    if self.verbose and plan:
                        print(f"\n  ╔{'═'*56}╗")
                        print(f"  ║ 📋 PLAN ({action}){' '*(43-len(action))}║")
                        print(f"  ╟{'─'*56}╢")
                        # Show plan steps
                        plan_lines = str(plan).split('\n')
                        for line in plan_lines[:10]:
                            line = line.strip()
                            if line:
                                display_line = line[:54]
                                print(f"  ║ {display_line:<54} ║")
                        if len(plan_lines) > 10:
                            print(f"  ║ ... ({len(plan_lines) - 10} more steps){' '*34}║")
                        print(f"  ╚{'═'*56}╝")

                elif event_type == "final_answer":
                    agent_response = update.details.get("content", "")

                elif event_type == "llm_token":
                    token = update.details.get("content", "")
                    agent_response += token

                elif event_type == "thought":
                    thought = update.details.get("content", update.message or "")
                    if thought:
                        print(f"\n  💭 Agent: {thought[:150]}{'...' if len(thought) > 150 else ''}")

                elif event_type == "error":
                    error = update.message
                    print(f"\n  ❌ ERROR: {error}")

        except Exception as e:
            error = str(e)
            print(f"  ❌ Exception: {error}")

        finally:
            # Close fresh agent to release MCP connections
            if self.fresh_agent_per_scenario and scenario_agent:
                try:
                    await scenario_agent.close()
                except Exception as close_err:
                    print(f"  ⚠️ Agent cleanup warning: {close_err}")

        duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)

        # Extract accounts from booking proposals first (most reliable)
        detected_debit = None
        detected_credit = None

        if booking_proposals:
            for proposal in booking_proposals:
                if isinstance(proposal, dict):
                    # Debit accounts from type="debit" proposals
                    if proposal.get("type") == "debit" and not detected_debit:
                        detected_debit = proposal.get("debit_account")
                    # Credit account from type="credit" proposal (Verbindlichkeiten)
                    if proposal.get("type") == "credit" and not detected_credit:
                        detected_credit = proposal.get("credit_account")

        # Fallback: parse response text if no proposals captured
        if not detected_debit:
            detected_debit = self._extract_account(agent_response, "debit", "soll")
        if not detected_credit:
            detected_credit = self._extract_account(agent_response, "credit", "haben", "verbindlichkeiten")

        # Check if accounts match expectations
        account_match = (
            (detected_debit == scenario.expected_debit_account or scenario.expected_debit_account is None)
            and (detected_credit == scenario.expected_credit_account or scenario.expected_credit_account is None)
        )

        result = TestResult(
            scenario_id=scenario.scenario_id,
            scenario_name=scenario.scenario_name,
            success=error is None,
            prompt=prompt,
            agent_response=agent_response[:500],
            tools_called=tools_called,
            hitl_triggered=hitl_triggered,
            hitl_response=hitl_response,
            detected_debit_account=detected_debit,
            detected_credit_account=detected_credit,
            expected_debit_account=scenario.expected_debit_account,
            expected_credit_account=scenario.expected_credit_account,
            account_match=account_match,
            error=error,
            duration_ms=duration_ms,
            booking_proposals=booking_proposals,
        )

        self.results.append(result)

        # Print scenario summary
        print(f"\n  {'─'*56}")
        print(f"  📊 SCENARIO SUMMARY: {scenario.scenario_id}")
        print(f"  {'─'*56}")
        print(f"  ⏱️  Duration: {duration_ms}ms")
        print(f"  🔧 Tools used: {len(tools_called)}")
        if self.verbose:
            for tool in tools_called:
                print(f"       - {tool}")
        print(f"  🔔 HITL triggered: {'Yes' if hitl_triggered else 'No'}")
        print(f"  📋 Account detection:")
        print(f"       Detected: Soll={detected_debit or 'N/A'} | Haben={detected_credit or 'N/A'}")
        print(f"       Expected: Soll={scenario.expected_debit_account or 'N/A'} | Haben={scenario.expected_credit_account or 'N/A'}")
        if booking_proposals and self.verbose:
            print(f"  📄 Booking proposals captured: {len(booking_proposals)}")
            for i, prop in enumerate(booking_proposals[:3]):
                prop_type = prop.get("type", "?")
                if prop_type == "debit":
                    print(f"       [{i+1}] Soll: {prop.get('debit_account')} ({prop.get('debit_account_name', '')})")
                elif prop_type == "credit":
                    print(f"       [{i+1}] Haben: {prop.get('credit_account')} ({prop.get('credit_account_name', '')})")
        print(f"  {'✅ PASSED' if account_match else '❌ FAILED'}")

        # Show agent response preview in verbose mode
        if self.verbose and agent_response:
            print(f"\n  💬 Agent Response (preview):")
            response_lines = agent_response[:300].split('\n')
            for line in response_lines[:5]:
                if line.strip():
                    print(f"       {line[:70]}{'...' if len(line) > 70 else ''}")
            if len(agent_response) > 300:
                print(f"       ... ({len(agent_response)} chars total)")

        return result

    async def _auto_learn_rule_from_hitl_confirmation(self, pending_hitl_review: dict, target_account: str = "4930") -> None:
        """
        Automatically learn a rule when HITL is confirmed.

        This is a workaround for agents that don't properly call hitl_review(action="process")
        after the user confirms a booking. We trigger rule learning directly from the test runner.

        Args:
            pending_hitl_review: Captured HITL review data with invoice_data and booking_proposal
            target_account: Default account to use if no booking_proposal exists (default: 4930 Bürobedarf)
        """
        try:
            from accounting_agent.tools.rule_learning_tool import RuleLearningTool

            rule_learning = RuleLearningTool()

            invoice_data = pending_hitl_review.get("invoice_data", {})
            booking_proposal = pending_hitl_review.get("booking_proposal", {})

            if not invoice_data:
                if self.verbose:
                    print(f"       ⚠️ Cannot auto-learn rule: missing invoice_data")
                return

            # If no booking_proposal exists (no rule match case), create one with default/provided account
            if not booking_proposal or not booking_proposal.get("debit_account"):
                booking_proposal = {
                    "debit_account": target_account,
                    "debit_account_name": self._get_account_name(target_account),
                    "type": "debit",
                }
                if self.verbose:
                    print(f"       📝 Created booking proposal with account: {target_account}")

            result = await rule_learning.execute(
                action="create_from_booking",
                invoice_data=invoice_data,
                booking_proposal=booking_proposal,
                confidence=1.0,  # User confirmed = 100% confidence
            )

            if result.get("success"):
                print(f"       ✅ Auto-learned rule: {result.get('rule_id')}")
            else:
                if self.verbose:
                    print(f"       ⚠️ Rule not created: {result.get('error', 'unknown')}")

        except Exception as e:
            if self.verbose:
                print(f"       ⚠️ Auto rule learning failed: {e}")

    async def _auto_learn_rule_with_correction(self, pending_hitl_review: dict, corrected_account: str) -> None:
        """
        Learn a rule with user-corrected account.

        Args:
            pending_hitl_review: Captured HITL review data
            corrected_account: The account number provided by the user
        """
        await self._auto_learn_rule_from_hitl_confirmation(pending_hitl_review, target_account=corrected_account)

    def _get_account_name(self, account: str) -> str:
        """Get account name for common SKR03 accounts."""
        account_names = {
            "4930": "Bürobedarf",
            "4940": "Zeitschriften, Bücher",
            "4950": "Rechts- und Beratungskosten",
            "4960": "Miete",
            "4970": "Porto",
            "4980": "Telefon",
            "6800": "Abschreibungen",
            "1576": "Vorsteuer 19%",
            "1571": "Vorsteuer 7%",
            "1600": "Verbindlichkeiten aus Lieferungen und Leistungen",
        }
        return account_names.get(account, f"Konto {account}")

    def _wrap_text(self, text: str, width: int) -> list[str]:
        """Wrap text to specified width."""
        words = text.split()
        lines = []
        current_line = ""
        for word in words:
            if len(current_line) + len(word) + 1 <= width:
                current_line += (" " if current_line else "") + word
            else:
                if current_line:
                    lines.append(current_line)
                current_line = word[:width] if len(word) > width else word
        if current_line:
            lines.append(current_line)
        return lines or [""]

    def _print_tool_args(self, tool_name: str, args: dict) -> None:
        """Print tool arguments in a readable format."""
        if not args:
            return

        # Tool-specific argument formatting
        if tool_name == "invoice_extract":
            if "invoice_text" in args:
                text = args["invoice_text"]
                print(f"  │   📄 Invoice text: {len(text)} chars")
                # Show first few lines
                lines = text.split('\n')[:5]
                for line in lines:
                    if line.strip():
                        print(f"  │      {line[:60]}{'...' if len(line) > 60 else ''}")

        elif tool_name == "semantic_rule_engine":
            # Handle invoice_data structure
            invoice_data = args.get("invoice_data", {})
            if isinstance(invoice_data, dict):
                if "supplier_name" in invoice_data:
                    print(f"  │   🏢 Supplier: {invoice_data['supplier_name']}")
                if "line_items" in invoice_data:
                    items = invoice_data["line_items"]
                    if isinstance(items, list):
                        print(f"  │   📦 Items: {len(items)} position(s)")
                        for item in items[:3]:
                            if isinstance(item, dict):
                                desc = item.get("description", str(item))[:50]
                                amt = item.get("net_amount", "")
                                print(f"  │      - {desc}: {amt}")
                if "total_net" in invoice_data:
                    print(f"  │   💰 Total net: {invoice_data['total_net']}")
            if "chart_of_accounts" in args:
                print(f"  │   📋 Chart: {args['chart_of_accounts']}")

        elif tool_name == "confidence_evaluator":
            if "rule_match" in args:
                rm = args["rule_match"]
                if isinstance(rm, dict):
                    print(f"  │   📊 Rule: {rm.get('rule_id', 'N/A')}")
                    print(f"  │   🎯 Match type: {rm.get('match_type', 'N/A')}")
                    print(f"  │   📈 Similarity: {rm.get('similarity_score', 'N/A')}")
            if "extraction_confidence" in args:
                print(f"  │   📋 Extraction confidence: {args['extraction_confidence']}")

        elif tool_name == "hitl_review":
            if "action" in args:
                print(f"  │   🎬 Action: {args['action']}")
            if "reason" in args:
                print(f"  │   💡 Reason: {args['reason'][:80]}")
            if "proposed_booking" in args:
                pb = args["proposed_booking"]
                if isinstance(pb, dict):
                    print(f"  │   📝 Proposed: Soll={pb.get('debit_account')} | Haben={pb.get('credit_account')}")

        elif tool_name == "rule_learning":
            if "action" in args:
                print(f"  │   🎬 Action: {args['action']}")
            if "vendor_name" in args:
                print(f"  │   🏢 Vendor: {args['vendor_name']}")
            if "target_account" in args:
                print(f"  │   🎯 Target account: {args['target_account']}")
            if "source" in args:
                print(f"  │   📚 Source: {args['source']}")

        elif tool_name == "check_compliance":
            if "invoice_data" in args:
                inv = args["invoice_data"]
                if isinstance(inv, dict):
                    print(f"  │   💰 Amount: {inv.get('total_gross', 'N/A')} {inv.get('currency', 'EUR')}")
                    print(f"  │   🏢 Vendor: {inv.get('vendor_name', 'N/A')}")

        elif tool_name == "ask_user":
            if "question" in args:
                q = args["question"][:100]
                print(f"  │   ❓ Question: {q}{'...' if len(args.get('question', '')) > 100 else ''}")
            if "options" in args:
                opts = args["options"]
                if isinstance(opts, list):
                    print(f"  │   📋 Options: {len(opts)}")

        else:
            # Generic argument display
            for key, value in list(args.items())[:5]:
                val_str = str(value)[:60]
                print(f"  │   {key}: {val_str}{'...' if len(str(value)) > 60 else ''}")

    def _print_tool_result(self, tool_name: str, result: Any, success: bool) -> None:
        """Print tool result with business-relevant information."""
        if not result:
            return

        if isinstance(result, str):
            # Try to parse as JSON
            try:
                result = json.loads(result)
            except (json.JSONDecodeError, TypeError):
                if len(result) > 100:
                    print(f"       {result[:100]}...")
                return

        if not isinstance(result, dict):
            # For planner, result might be a string with the plan
            if tool_name == "planner" and isinstance(result, str):
                print(f"       {result[:100]}..." if len(result) > 100 else f"       {result}")
            return

        # Tool-specific result formatting
        if tool_name == "planner":
            # Show plan summary
            plan = result.get("plan") or result.get("output", "")
            if plan:
                print(f"       ┌─ PLAN ─┐")
                plan_lines = str(plan).split('\n')
                for line in plan_lines[:8]:
                    line = line.strip()
                    if line:
                        print(f"       │ {line[:60]}{'...' if len(line) > 60 else ''}")
                if len(plan_lines) > 8:
                    print(f"       │ ... (+{len(plan_lines) - 8} more)")
                print(f"       └{'─'*8}┘")
            return

        elif tool_name == "invoice_extract":
            print(f"       ┌─ EXTRACTED INVOICE DATA ─┐")
            if "vendor_name" in result:
                print(f"       │ 🏢 Vendor: {result['vendor_name']}")
            if "invoice_number" in result:
                print(f"       │ 📋 Invoice #: {result['invoice_number']}")
            if "invoice_date" in result:
                print(f"       │ 📅 Date: {result['invoice_date']}")
            if "total_gross" in result:
                currency = result.get("currency", "EUR")
                print(f"       │ 💰 Total: {result['total_gross']} {currency}")
            if "total_vat" in result:
                print(f"       │ 📊 VAT: {result['total_vat']}")
            if "items" in result:
                items = result["items"]
                if isinstance(items, list):
                    print(f"       │ 📦 Items: {len(items)}")
                    for item in items[:2]:
                        if isinstance(item, dict):
                            desc = item.get("description", "")[:40]
                            amt = item.get("amount", item.get("total", ""))
                            print(f"       │    - {desc}: {amt}")
            print(f"       └{'─'*26}┘")

        elif tool_name == "semantic_rule_engine":
            print(f"       ┌─ RULE MATCHING RESULT ─┐")
            if "matched" in result:
                matched = result["matched"]
                print(f"       │ 🎯 Matched: {'Yes' if matched else 'No'}")
            if "rule_id" in result:
                print(f"       │ 📋 Rule ID: {result['rule_id']}")
            if "match_type" in result:
                print(f"       │ 🔍 Match type: {result['match_type']}")
            if "similarity_score" in result:
                score = result["similarity_score"]
                bar = "█" * int(score * 10) + "░" * (10 - int(score * 10))
                print(f"       │ 📊 Similarity: [{bar}] {score:.2f}")
            if "target_account" in result:
                print(f"       │ 🎯 Account: {result['target_account']}")
            if "target_account_name" in result:
                print(f"       │ 📝 Account name: {result['target_account_name']}")
            if "is_ambiguous" in result:
                print(f"       │ ⚠️  Ambiguous: {result['is_ambiguous']}")
            print(f"       └{'─'*24}┘")

        elif tool_name == "confidence_evaluator":
            print(f"       ┌─ CONFIDENCE EVALUATION ─┐")
            if "overall_confidence" in result:
                conf = result["overall_confidence"]
                bar = "█" * int(conf * 10) + "░" * (10 - int(conf * 10))
                print(f"       │ 📊 Confidence: [{bar}] {conf:.1%}")
            if "recommendation" in result:
                rec = result["recommendation"]
                emoji = "🤖" if rec == "auto_book" else "👤"
                print(f"       │ {emoji} Recommendation: {rec}")
            if "requires_hitl" in result:
                print(f"       │ 🔔 HITL required: {result['requires_hitl']}")
            if "hard_gate_triggered" in result:
                gate = result["hard_gate_triggered"]
                if gate:
                    print(f"       │ 🚨 Hard gate: {gate}")
            if "signals" in result:
                signals = result["signals"]
                if isinstance(signals, dict):
                    print(f"       │ 📈 Signals:")
                    for sig, val in list(signals.items())[:4]:
                        print(f"       │    {sig}: {val:.2f}" if isinstance(val, float) else f"       │    {sig}: {val}")
            print(f"       └{'─'*25}┘")

        elif tool_name == "check_compliance":
            print(f"       ┌─ COMPLIANCE CHECK ─┐")
            if "compliant" in result:
                status = "✅ Compliant" if result["compliant"] else "❌ Not compliant"
                print(f"       │ {status}")
            if "issues" in result:
                issues = result["issues"]
                if isinstance(issues, list) and issues:
                    print(f"       │ ⚠️  Issues:")
                    for issue in issues[:3]:
                        print(f"       │    - {issue[:50]}")
            if "warnings" in result:
                warnings = result["warnings"]
                if isinstance(warnings, list) and warnings:
                    print(f"       │ ⚡ Warnings:")
                    for warn in warnings[:3]:
                        print(f"       │    - {warn[:50]}")
            print(f"       └{'─'*20}┘")

        elif tool_name == "hitl_review":
            print(f"       ┌─ HITL REVIEW ─┐")
            if "status" in result:
                print(f"       │ 📋 Status: {result['status']}")
            if "review_id" in result:
                print(f"       │ 🆔 Review ID: {result['review_id']}")
            if "action_taken" in result:
                print(f"       │ ✅ Action: {result['action_taken']}")
            print(f"       └{'─'*15}┘")

        elif tool_name == "rule_learning":
            print(f"       ┌─ RULE LEARNING ─┐")
            if "action" in result:
                print(f"       │ 🎬 Action: {result['action']}")
            if "rule_id" in result:
                print(f"       │ 🆔 Rule ID: {result['rule_id']}")
            if "status" in result:
                print(f"       │ 📋 Status: {result['status']}")
            if "message" in result:
                print(f"       │ 💬 {result['message'][:40]}")
            print(f"       └{'─'*17}┘")

        elif not success:
            if "error" in result:
                print(f"       ❌ Error: {result['error']}")

    def _extract_account(self, text: str, *keywords: str) -> Optional[str]:
        """Extract account number from response text.

        Looks for explicit account number patterns and filters out dates.
        """
        import re

        text_lower = text.lower()

        # Pattern 1: Explicit account mentions (highest priority)
        # Matches: "Konto 4930", "Soll-Konto: 4930", "Haben: 1600", "Account 4930"
        explicit_patterns = [
            r'(?:soll|debit)[\s\-]*(?:konto)?[\s:]*(\d{4})\b',
            r'(?:haben|credit)[\s\-]*(?:konto)?[\s:]*(\d{4})\b',
            r'konto[\s:]*(\d{4})\b',
            r'account[\s:]*(\d{4})\b',
        ]

        for keyword in keywords:
            if keyword in text_lower:
                # Try explicit patterns first
                for pattern in explicit_patterns:
                    if keyword in pattern or any(k in pattern for k in keywords):
                        matches = re.findall(pattern, text_lower)
                        if matches:
                            return matches[0]

        # Pattern 2: SKR account number patterns (4 digits not in date context)
        # Filter out dates like "27.01.2026" or "2026-01-27"
        def is_year_in_date(text: str, match_pos: int, number: str) -> bool:
            """Check if a 4-digit number appears to be a year in a date."""
            # Check for patterns: DD.MM.YYYY, YYYY-MM-DD, DD/MM/YYYY
            before = text[max(0, match_pos - 6):match_pos]
            after = text[match_pos + 4:match_pos + 7]

            # Date patterns before (DD.MM. or DD/)
            if re.search(r'\d{1,2}[./]\d{1,2}[./]$', before):
                return True
            # Date patterns after (-MM-DD or .MM.DD)
            if re.search(r'^[.\-/]\d{1,2}[.\-/]', after):
                return True
            # Year at start of ISO date
            if re.search(r'^[.\-/]\d{1,2}', after):
                return True
            return False

        # Find all 4-digit numbers and filter
        all_matches = []
        for match in re.finditer(r'\b([1-9]\d{3})\b', text):
            number = match.group(1)
            pos = match.start()
            if not is_year_in_date(text, pos, number):
                all_matches.append(number)

        # Look for matches near keywords
        for keyword in keywords:
            keyword_pos = text_lower.find(keyword)
            if keyword_pos >= 0:
                # Find account numbers within 100 chars of keyword
                for match in re.finditer(r'\b([1-9]\d{3})\b', text):
                    number = match.group(1)
                    pos = match.start()
                    if abs(pos - keyword_pos) < 100 and not is_year_in_date(text, pos, number):
                        return number

        # Fallback: return first non-date 4-digit number
        return all_matches[0] if all_matches else None

    async def run_all(self, scenarios: Optional[list[TestInvoice]] = None) -> None:
        """Run all scenarios."""
        scenarios = scenarios or SCENARIOS

        print("\n" + "=" * 60)
        print("ACCOUNTING AGENT E2E TEST RUNNER")
        print("=" * 60)
        print(f"Total scenarios: {len(scenarios)}")
        print(f"Interactive: {self.interactive}")
        print(f"Auto-confirm HITL: {self.auto_confirm_hitl}")
        print(f"Verbose output: {self.verbose}")

        await self.setup()

        try:
            for scenario in scenarios:
                await self.run_scenario(scenario)
        finally:
            # Cleanup shared agent if not using fresh agents
            if not self.fresh_agent_per_scenario and self.agent:
                try:
                    await self.agent.close()
                except Exception as e:
                    print(f"⚠️ Shared agent cleanup warning: {e}")

        self.print_summary()

    def print_summary(self) -> None:
        """Print test summary."""
        print("\n" + "=" * 60)
        print("TEST SUMMARY")
        print("=" * 60)

        total = len(self.results)
        passed = sum(1 for r in self.results if r.success and r.account_match)
        failed = total - passed

        print(f"\nTotal: {total}")
        print(f"Passed: {passed} ✅")
        print(f"Failed: {failed} ❌")
        print(f"Pass rate: {passed/total*100:.1f}%")

        if failed > 0:
            print("\nFailed scenarios:")
            for r in self.results:
                if not r.success or not r.account_match:
                    print(f"  - {r.scenario_id}: {r.scenario_name}")
                    if r.error:
                        print(f"    Error: {r.error}")
                    if not r.account_match:
                        print(f"    Expected: {r.expected_debit_account} | Got: {r.detected_debit_account}")

        # HITL statistics
        hitl_scenarios = [r for r in self.results if r.hitl_triggered]
        print(f"\nHITL triggered: {len(hitl_scenarios)}/{total}")

        # Tool usage statistics
        all_tools = []
        for r in self.results:
            all_tools.extend(r.tools_called)
        tool_counts = {}
        for tool in all_tools:
            tool_counts[tool] = tool_counts.get(tool, 0) + 1

        print("\nTool usage:")
        for tool, count in sorted(tool_counts.items(), key=lambda x: -x[1]):
            print(f"  {tool}: {count}")

    def save_results(self, output_path: str = "test_results.json") -> None:
        """Save results to JSON file."""
        data = {
            "timestamp": datetime.now().isoformat(),
            "total": len(self.results),
            "passed": sum(1 for r in self.results if r.success and r.account_match),
            "results": [
                {
                    "scenario_id": r.scenario_id,
                    "scenario_name": r.scenario_name,
                    "success": r.success,
                    "account_match": r.account_match,
                    "tools_called": r.tools_called,
                    "hitl_triggered": r.hitl_triggered,
                    "detected_debit": r.detected_debit_account,
                    "detected_credit": r.detected_credit_account,
                    "expected_debit": r.expected_debit_account,
                    "expected_credit": r.expected_credit_account,
                    "duration_ms": r.duration_ms,
                    "error": r.error,
                    "booking_proposals_count": len(r.booking_proposals) if r.booking_proposals else 0,
                }
                for r in self.results
            ],
        }

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        print(f"\nResults saved to: {output_path}")


def configure_logging(debug: bool = False) -> None:
    """Configure logging based on debug flag."""
    import logging
    import structlog

    if debug:
        # Debug mode: show all logs
        logging.basicConfig(
            level=logging.DEBUG,
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        )
        structlog.configure(
            wrapper_class=structlog.make_filtering_bound_logger(logging.DEBUG),
        )
    else:
        # Quiet mode: only show warnings and errors
        logging.basicConfig(
            level=logging.WARNING,
            format="%(message)s",
        )
        structlog.configure(
            wrapper_class=structlog.make_filtering_bound_logger(logging.WARNING),
        )
        # Suppress noisy loggers
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("httpcore").setLevel(logging.WARNING)
        logging.getLogger("openai").setLevel(logging.WARNING)
        logging.getLogger("litellm").setLevel(logging.WARNING)


async def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Run accounting agent E2E tests")
    parser.add_argument(
        "--scenario", "-s",
        help="Run specific scenario by ID (e.g., IN-DE-001)",
    )
    parser.add_argument(
        "--interactive", "-i",
        action="store_true",
        help="Interactive mode - pause for HITL responses",
    )
    parser.add_argument(
        "--no-auto-confirm",
        action="store_true",
        help="Don't auto-confirm HITL requests",
    )
    parser.add_argument(
        "--output", "-o",
        default="test_results.json",
        help="Output file for results",
    )
    parser.add_argument(
        "--incoming-only",
        action="store_true",
        help="Only run incoming invoice scenarios",
    )
    parser.add_argument(
        "--outgoing-only",
        action="store_true",
        help="Only run outgoing invoice scenarios",
    )
    parser.add_argument(
        "--debug", "-d",
        action="store_true",
        help="Enable debug logging (shows all LLM and tool logs)",
    )
    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Quiet mode - minimal tool output (no arguments/results)",
    )
    parser.add_argument(
        "--reuse-agent",
        action="store_true",
        help="Reuse single agent for all scenarios (faster but may cause MCP issues)",
    )

    args = parser.parse_args()

    # Configure logging BEFORE importing taskforce modules
    configure_logging(debug=args.debug)

    # Filter scenarios
    scenarios = SCENARIOS

    if args.scenario:
        scenarios = [s for s in scenarios if s.scenario_id == args.scenario]
        if not scenarios:
            print(f"Scenario not found: {args.scenario}")
            print("Available scenarios:")
            for s in SCENARIOS:
                print(f"  {s.scenario_id}: {s.scenario_name}")
            return

    if args.incoming_only:
        scenarios = [s for s in scenarios if s.direction == InvoiceDirection.INCOMING]

    if args.outgoing_only:
        scenarios = [s for s in scenarios if s.direction == InvoiceDirection.OUTGOING]

    # Create runner
    runner = AccountingAgentTestRunner(
        interactive=args.interactive,
        auto_confirm_hitl=not args.no_auto_confirm,
        verbose=not args.quiet,
        fresh_agent_per_scenario=not args.reuse_agent,
    )

    # Run tests
    await runner.run_all(scenarios)

    # Save results
    runner.save_results(args.output)


if __name__ == "__main__":
    asyncio.run(main())
