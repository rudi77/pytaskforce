"""
Core Agent Domain Logic

This module implements the core ReAct (Reason + Act) execution loop for the agent.
The Agent class orchestrates the execution of missions by:
1. Loading/creating TodoLists (plans)
2. Iterating through TodoItems
3. For each item: Generate Thought → Execute Action → Record Observation
4. Persisting state and plan updates

The Agent is dependency-injected with protocol interfaces, making it testable
without any infrastructure dependencies (no I/O, no external services).
"""

import json
from dataclasses import asdict
from typing import Any

import structlog

from taskforce.core.domain.events import (
    Action,
    ActionType,
    Observation,
    Thought
)
from taskforce.core.domain.router import (
    QueryRouter,
    RouteDecision,
    RouterContext,
    RouterResult,
)

from taskforce.core.domain.models import ExecutionResult
from taskforce.core.domain.replanning import (
    REPLAN_PROMPT_TEMPLATE,
    ReplanStrategy,
    StrategyType,
    extract_failure_context,
    validate_strategy,
)
from taskforce.core.interfaces.llm import LLMProviderProtocol
from taskforce.core.interfaces.state import StateManagerProtocol
from taskforce.core.interfaces.todolist import (
    TaskStatus,
    TodoItem,
    TodoList,
    TodoListManagerProtocol,
)
from taskforce.core.interfaces.tools import ToolProtocol

# Type hint import for optional cache (avoid circular import)
if False:  # TYPE_CHECKING workaround for runtime
    from taskforce.infrastructure.cache.tool_cache import ToolResultCache


class Agent:
    """
    Core ReAct agent with protocol-based dependencies.

    The Agent implements the ReAct (Reason + Act) execution pattern:
    1. Load state and TodoList
    2. For each pending TodoItem:
       a. Generate Thought (reasoning + action decision)
       b. Execute Action (tool call, ask user, complete, or replan)
       c. Record Observation (success/failure + result data)
    3. Update state and persist changes
    4. Repeat until all items complete or mission goal achieved

    All dependencies are injected via protocol interfaces, enabling
    pure business logic testing without infrastructure concerns.
    """

    MAX_ITERATIONS = 50  # Safety limit to prevent infinite loops

    # Whitelist of cacheable (read-only) tools
    CACHEABLE_TOOLS = frozenset({
        "wiki_get_page",
        "wiki_get_page_tree",
        "wiki_search",
        "file_read",
        "semantic_search",
        "web_search",
        "get_document",
        "list_documents",
    })

    def __init__(
        self,
        state_manager: StateManagerProtocol,
        llm_provider: LLMProviderProtocol,
        tools: list[ToolProtocol],
        todolist_manager: TodoListManagerProtocol,
        system_prompt: str,
        model_alias: str = "main",
        tool_cache: "ToolResultCache | None" = None,
        router: QueryRouter | None = None,
        enable_fast_path: bool = False,
    ):
        """
        Initialize Agent with injected dependencies.

        Args:
            state_manager: Protocol for session state persistence
            llm_provider: Protocol for LLM completions
            tools: List of available tools implementing ToolProtocol
            todolist_manager: Protocol for TodoList management
            system_prompt: Base system prompt for LLM interactions
            model_alias: Model alias for LLM calls (default: "main")
            tool_cache: Optional cache for tool results (session-scoped)
            router: Optional QueryRouter for fast-path routing
            enable_fast_path: Whether to enable fast-path for follow-up queries
        """
        self.state_manager = state_manager
        self.llm_provider = llm_provider
        self.tools = {tool.name: tool for tool in tools}
        self.todolist_manager = todolist_manager
        self.system_prompt = system_prompt
        self.model_alias = model_alias
        self._tool_cache = tool_cache
        self._router = router
        self._enable_fast_path = enable_fast_path
        self.logger = structlog.get_logger().bind(component="agent")

    async def execute(self, mission: str, session_id: str) -> ExecutionResult:
        """
        Execute ReAct loop for given mission.

        Main entry point for agent execution. Orchestrates the complete
        ReAct cycle from mission initialization through plan execution
        to final result.

        Workflow:
        1. Load or initialize session state
        2. Create or load TodoList for mission
        3. Execute ReAct loop until completion or pause
        4. Return execution result with status and history

        Args:
            mission: User's mission description (what to accomplish)
            session_id: Unique session identifier for state persistence

        Returns:
            ExecutionResult with status, message, and execution history

        Raises:
            RuntimeError: If LLM calls fail or critical errors occur
        """
        self.logger.info("execute_start", session_id=session_id, mission=mission[:100])

        # 1. Load or initialize state
        state = await self.state_manager.load_state(session_id)
        execution_history: list[dict[str, Any]] = []

        # 1a. Fast-path routing for follow-up queries
        if self._router and self._enable_fast_path:
            route_result = await self._route_query(mission, state, session_id)

            if route_result.decision == RouteDecision.FOLLOW_UP:
                self.logger.info(
                    "fast_path_activated",
                    session_id=session_id,
                    confidence=route_result.confidence,
                    rationale=route_result.rationale,
                )
                return await self._execute_fast_path(
                    mission, state, session_id, execution_history
                )

        # 2. Standard path: full planning and execution
        self.logger.info("full_path_activated", session_id=session_id)
        return await self._execute_full_path(mission, state, session_id, execution_history)

    async def _replan(
        self, current_step: TodoItem, thought: Thought, todolist: TodoList, state: dict[str, Any], session_id: str
    ) -> TodoList:
        """
        Intelligent Replanning: Modifies the plan based on failure context.
        """
        self.logger.info("replanning_start", session_id=session_id, step=current_step.position)
        
        # 1. Ask LLM for a recovery strategy
        strategy = await self._generate_replan_strategy(current_step, todolist)
        
        if not strategy:
             self.logger.warning("replan_failed_no_strategy", session_id=session_id)
             # Fallback to skip if strategy generation failed
             current_step.status = TaskStatus.SKIPPED
             await self.todolist_manager.update_todolist(todolist)
             return todolist

        self.logger.info("replan_strategy_selected", 
                        session_id=session_id, 
                        type=strategy.strategy_type.value,
                        reasoning=strategy.rationale)

        # 2. Apply the strategy to the TodoList entity (In-Memory)
        if strategy.strategy_type == StrategyType.RETRY_WITH_PARAMS:
            # Modify the current step (e.g. clarify description or criteria)
            new_params = strategy.modifications.get("new_parameters", {})
            if new_params:
                 current_step.tool_input = new_params
            current_step.status = TaskStatus.PENDING # Reset status
            current_step.replan_count += 1
            
        elif strategy.strategy_type == StrategyType.SWAP_TOOL:
             current_step.chosen_tool = strategy.modifications.get("new_tool")
             current_step.tool_input = strategy.modifications.get("new_parameters", {})
             current_step.status = TaskStatus.PENDING
             current_step.replan_count += 1
             
        elif strategy.strategy_type == StrategyType.DECOMPOSE_TASK:
            # Replace current step with multiple smaller steps
            new_items = []
            start_pos = current_step.position
            
            # Create new sub-items
            subtasks = strategy.modifications.get("subtasks", [])
            for i, item_data in enumerate(subtasks):
                new_item = TodoItem(
                    position=start_pos + i,
                    description=item_data["description"],
                    acceptance_criteria=item_data["acceptance_criteria"],
                    dependencies=current_step.dependencies, # Inherit dependencies
                    status=TaskStatus.PENDING
                )
                new_items.append(new_item)
            
            if new_items:
                # Remove old item and insert new ones
                # We need to shift positions of all subsequent items
                shift_offset = len(new_items) - 1
                
                # 1. Remove current
                if current_step in todolist.items:
                    todolist.items.remove(current_step)
                
                # 2. Shift subsequent items
                for item in todolist.items:
                    if item.position > start_pos:
                        item.position += shift_offset
                        
                # 3. Add new items
                todolist.items.extend(new_items)
                todolist.items.sort(key=lambda x: x.position)
            
        elif strategy.strategy_type == StrategyType.SKIP:
            current_step.status = TaskStatus.SKIPPED
            
        # 3. Persist the modified plan
        await self.todolist_manager.update_todolist(todolist)
        
        return todolist

    async def _generate_replan_strategy(
        self, current_step: TodoItem, todolist: TodoList
    ) -> ReplanStrategy | None:
        """
        Asks the LLM how to fix the broken plan.
        """
        # Context building (tools are already in the system prompt's <ToolsDescription> section)
        context = extract_failure_context(current_step)
        
        # Render prompt
        user_prompt = REPLAN_PROMPT_TEMPLATE.format(**context)
        
        result = await self.llm_provider.complete(
            messages=[
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            model=self.model_alias,
            response_format={"type": "json_object"},
            temperature=0.1
        )
        
        if not result.get("success"):
            self.logger.error("replan_llm_failed", error=result.get("error"))
            return None
            
        try:
            data = json.loads(result["content"])
            strategy = ReplanStrategy.from_dict(data)
            
            if validate_strategy(strategy, self.logger):
                return strategy
            else:
                self.logger.warning("invalid_replan_strategy", strategy=data)
                return None
                
        except (json.JSONDecodeError, ValueError) as e:
            self.logger.error("replan_parse_failed", error=str(e), content=result["content"])
            return None

    async def _get_or_create_todolist(
        self, state: dict[str, Any], mission: str, session_id: str
    ) -> TodoList:
        """Get existing TodoList or create new one."""
        todolist_id = state.get("todolist_id")

        if todolist_id:
            try:
                todolist = await self.todolist_manager.load_todolist(todolist_id)
                
                # --- FIX START: Prüfen, ob die Liste schon fertig ist ---
                # Wir prüfen, ob alle Items den Status COMPLETED haben (oder SKIPPED)
                all_items_done = all(
                    item.status.value in ["COMPLETED", "SKIPPED"] 
                    for item in todolist.items
                )

                # Wenn die Liste noch NICHT fertig ist, machen wir damit weiter.
                # (Das passiert z.B., wenn der Agent mehrere Steps nacheinander macht)
                if not all_items_done:
                    self.logger.info("todolist_loaded_resuming", session_id=session_id, todolist_id=todolist_id)
                    return todolist
                
                # Wenn die Liste fertig IST, bedeutet der neue User-Input eine NEUE Mission.
                # Wir ignorieren die alte Liste und lassen den Code unten eine neue erstellen.
                self.logger.info("todolist_completed_starting_new_mission", session_id=session_id, old_id=todolist_id)
                
                # Optional: State bereinigen, damit wir sauber starten
                # state["todolist_id"] = None 
                
                # --- FIX END ---

            except FileNotFoundError:
                self.logger.warning(
                    "todolist_not_found", session_id=session_id, todolist_id=todolist_id
                )

        # Create new TodoList (Wird ausgeführt, wenn keine ID da ist ODER die alte Liste fertig war)
        self.logger.info("creating_new_todolist_for_mission", mission=mission)
        
        tools_desc = self._get_tools_description()
        
        # WICHTIG: Wenn wir eine neue Mission starten, sollten wir evtl. 
        # alte "answers" nicht blind übernehmen, es sei denn, es sind persistente Fakten.
        # Für diesen Fix lassen wir es erstmal so.
        answers = state.get("answers", {})
        
        todolist = await self.todolist_manager.create_todolist(
            mission=mission, tools_desc=tools_desc, answers=answers, model=self.model_alias
        )

        state["todolist_id"] = todolist.todolist_id
        await self.state_manager.save_state(session_id, state)

        self.logger.info(
            "todolist_created",
            session_id=session_id,
            todolist_id=todolist.todolist_id,
            items=len(todolist.items),
        )

        return todolist

    def _get_tools_description(self) -> str:
        """Build formatted description of available tools."""
        descriptions = []
        for tool in self.tools.values():
            params = json.dumps(tool.parameters_schema, indent=2)
            descriptions.append(f"Tool: {tool.name}\nDescription: {tool.description}\nParameters: {params}")
        return "\n\n".join(descriptions)

    def _get_next_actionable_step(self, todolist: TodoList) -> TodoItem | None:
        """Find next step that can be executed."""
        for step in sorted(todolist.items, key=lambda s: s.position):
            # Skip completed steps
            if step.status == TaskStatus.COMPLETED:
                continue

            # Check if pending with dependencies met
            if step.status == TaskStatus.PENDING:
                deps_met = all(
                    any(s.position == dep and s.status == TaskStatus.COMPLETED for s in todolist.items)
                    for dep in step.dependencies
                )
                if deps_met:
                    return step

            # Check if failed but has retries remaining
            if step.status == TaskStatus.FAILED and step.attempts < step.max_attempts:
                return step

        return None

    def _build_thought_context(
        self, step: TodoItem, todolist: TodoList, state: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Build enriched context for thought generation.

        Includes full previous results (not truncated), conversation history,
        and cache information to help the LLM avoid redundant tool calls.

        Args:
            step: Current TodoItem being executed
            todolist: Full TodoList with all items
            state: Session state dictionary

        Returns:
            Context dictionary for LLM thought generation
        """
        # Collect ALL results from completed steps (not truncated)
        previous_results = [
            {
                "step": s.position,
                "description": s.description,
                "tool": s.chosen_tool,
                "result": s.execution_result,
                "status": s.status.value,
            }
            for s in todolist.items
            if s.execution_result and s.position < step.position
        ]

        # Extract error from current step if this is a retry
        current_error = None
        if step.execution_result and not step.execution_result.get("success"):
            current_error = {
                "error": step.execution_result.get("error"),
                "type": step.execution_result.get("type"),
                "hints": step.execution_result.get("hints", []),
                "attempt": step.attempts,
                "max_attempts": step.max_attempts,
            }

        # Include full conversation history from state
        conversation_history = state.get("conversation_history", [])

        # Include cache info for transparency
        cache_info = None
        if self._tool_cache:
            cache_info = {
                "enabled": True,
                "stats": self._tool_cache.stats,
                "hint": "Check PREVIOUS_RESULTS before calling tools - data may already be available",
            }

        return {
            "current_step": step,
            "current_error": current_error,
            "previous_results": previous_results,  # Full results, not truncated
            "conversation_history": conversation_history,
            "cache_info": cache_info,
            "user_answers": state.get("answers", {}),
        }

    def _extract_summary_from_invalid_json(self, raw_content: str) -> str | None:
        """
        Extract summary field from invalid JSON using regex.
        
        When LLM returns malformed JSON that still contains a valid summary,
        we extract it rather than showing the raw JSON to the user.
        
        Returns:
            Extracted summary string, or None if not found
        """
        import re
        # Look for "summary": "..." pattern, handling escaped quotes
        pattern = r'"summary"\s*:\s*"((?:[^"\\]|\\.)*)"\s*[,}]'
        match = re.search(pattern, raw_content, re.DOTALL)
        if match:
            # Unescape the string
            summary = match.group(1)
            summary = summary.replace('\\"', '"')
            summary = summary.replace('\\n', '\n')
            summary = summary.replace('\\t', '\t')
            return summary
        return None

    async def _generate_thought(self, context: dict[str, Any]) -> Thought:
        """Generate thought using LLM."""
        current_step = context["current_step"]

        # Build prompt with MINIMAL schema
        schema_hint = {
            "action": "tool_call|respond|ask_user",
            "tool": "string (only for tool_call)",
            "tool_input": "object (only for tool_call)",
            "question": "string (only for ask_user)",
            "answer_key": "string (only for ask_user)",
            "summary": "string (only for respond - final answer)",
        }

        # Build error context if retry
        error_context = ""
        if context.get("current_error"):
            error = context["current_error"]
            error_context = f"""
PREVIOUS ATTEMPT FAILED (Attempt {error['attempt']}/{error['max_attempts']}):
Error Type: {error.get('type', 'Unknown')}
Error Message: {error.get('error', 'Unknown error')}
"""
            if error.get("hints"):
                error_context += "\nHints to fix:\n"
                for hint in error["hints"]:
                    error_context += f"  - {hint}\n"
            
            # Add hint to replan if persistent failure
            error_context += "\nIf the error persists or the tool is unsuitable, choose 'replan' action to modify the task structure.\n"

        user_prompt = (
            "You are the ReAct Execution Agent.\n"
            "Analyze the current step and choose the best action.\n\n"
            f"CURRENT_STEP:\n{json.dumps(asdict(current_step), indent=2)}\n\n"
            f"{error_context}"
            f"PREVIOUS_RESULTS:\n{json.dumps(context.get('previous_results', []), indent=2)}\n\n"
            f"USER_ANSWERS:\n{json.dumps(context.get('user_answers', {}), indent=2)}\n\n"
            "Rules:\n"
            "- Choose the appropriate tool from the <ToolsDescription> section to fulfill the step's acceptance criteria.\n"
            "- If this is a retry, FIX the previous error using the hints provided.\n"
            "- If information is missing, use ask_user action.\n"
            "- If you have enough information to answer, use respond action with your answer in summary.\n"
            "- IMPORTANT: After a tool succeeds, you may continue iterating (e.g., run tests).\n"
            "  Only use respond when you have VERIFIED the step's acceptance criteria are met.\n"
            "- Return STRICT JSON only matching this MINIMAL schema:\n"
            f"{json.dumps(schema_hint, indent=2)}\n"
        )

        # Build messages with optional conversation history
        messages = [{"role": "system", "content": self.system_prompt}]
        
        # Add conversation history if available in context
        conversation_history = context.get("conversation_history")
        if conversation_history:
            # Filter out system messages from history (we already have one)
            for msg in conversation_history:
                if msg.get("role") != "system":
                    messages.append(msg)
        
        # Add current user prompt
        messages.append({"role": "user", "content": user_prompt})

        self.logger.info("llm_call_thought_start", step=current_step.position)

        result = await self.llm_provider.complete(
            messages=messages, model=self.model_alias, response_format={"type": "json_object"}, temperature=0.2
        )

        if not result.get("success"):
            self.logger.error(
                "thought_generation_failed", step=current_step.position, error=result.get("error")
            )
            raise RuntimeError(f"LLM completion failed: {result.get('error')}")

        raw_content = result["content"]
        self.logger.info("llm_call_thought_end", step=current_step.position)

        # Parse thought from JSON - supports both minimal and legacy schema
        try:
            data = json.loads(raw_content)
            
            # Detect schema format: minimal has "action" as string, legacy has "action" as dict
            if isinstance(data.get("action"), str):
                # MINIMAL SCHEMA: {"action": "tool_call", "tool": "...", ...}
                action_type_raw = data["action"]
                
                # Normalize: finish_step -> respond (same semantics: complete current step)
                # Note: "complete" is NOT mapped - it has different semantics (early exit)
                if action_type_raw == "finish_step":
                    action_type_raw = "respond"
                
                # FALLBACK: LLM may confuse tool name with action type
                # E.g., {"action": "list_wiki", "tool": "list_wiki", ...}
                # If "action" is not a valid ActionType but looks like a tool_call, correct it
                valid_action_types = {a.value for a in ActionType}
                if action_type_raw not in valid_action_types:
                    # Check if LLM provided tool info (clear sign of tool_call intent)
                    if data.get("tool") or data.get("tool_input"):
                        self.logger.warning(
                            "llm_action_type_corrected",
                            original_action=action_type_raw,
                            corrected_to="tool_call",
                        )
                        # If tool field is missing but action looks like tool name, use it
                        if not data.get("tool"):
                            data["tool"] = action_type_raw
                        action_type_raw = "tool_call"
                    else:
                        # No tool info - raise original error for clarity
                        raise ValueError(f"'{action_type_raw}' is not a valid ActionType")
                
                action = Action(
                    type=ActionType(action_type_raw),
                    tool=data.get("tool"),
                    tool_input=data.get("tool_input"),
                    question=data.get("question"),
                    answer_key=data.get("answer_key"),
                    summary=data.get("summary"),
                    replan_reason=data.get("replan_reason"),
                )
                
                # Build Thought with defaults for optional fields
                thought = Thought(
                    step_ref=current_step.position,  # Use current step as default
                    rationale="",  # Not required in minimal schema
                    action=action,
                    expected_outcome="",  # Not required in minimal schema
                    confidence=1.0,
                )
            else:
                # LEGACY SCHEMA: {"action": {"type": "...", "tool": "..."}, "step_ref": ...}
                action_data = data["action"]
                action_type_raw = action_data["type"]
                
                # Normalize: finish_step -> respond (same semantics: complete current step)
                # Note: "complete" is NOT mapped - it has different semantics (early exit)
                if action_type_raw == "finish_step":
                    action_type_raw = "respond"
                
                action = Action(
                    type=ActionType(action_type_raw),
                    tool=action_data.get("tool"),
                    tool_input=action_data.get("tool_input"),
                    question=action_data.get("question"),
                    answer_key=action_data.get("answer_key"),
                    summary=action_data.get("summary"),
                    replan_reason=action_data.get("replan_reason"),
                )
                thought = Thought(
                    step_ref=data.get("step_ref", current_step.position),
                    rationale=data.get("rationale", ""),
                    action=action,
                    expected_outcome=data.get("expected_outcome", ""),
                    confidence=data.get("confidence", 1.0),
                )
            return thought
        except (json.JSONDecodeError, KeyError) as e:
            # FALLBACK: JSON parsing failed.
            # Try to extract the summary field from invalid JSON
            extracted_summary = self._extract_summary_from_invalid_json(raw_content)
            
            if extracted_summary:
                self.logger.warning(
                    "thought_parse_failed_extracted_summary",
                    step=current_step.position,
                    error=str(e),
                    summary_preview=extracted_summary[:100],
                )
                fallback_summary = extracted_summary
            else:
                # NIEMALS raw_content als User-Output verwenden!
                # Log raw_content auf DEBUG für spätere Analyse
                self.logger.debug(
                    "thought_parse_raw_content",
                    step=current_step.position,
                    raw_content=raw_content[:500] if raw_content else "(empty)",
                )
                self.logger.warning(
                    "thought_parse_failed_using_fallback",
                    step=current_step.position,
                    error=str(e),
                )
                fallback_summary = (
                    "Es ist ein interner Verarbeitungsfehler aufgetreten. "
                    "Bitte versuchen Sie es erneut oder formulieren Sie Ihre Anfrage anders."
                )

            fallback_action = Action(
                type=ActionType.COMPLETE,
                summary=fallback_summary,
            )

            return Thought(
                step_ref=current_step.position,
                rationale="LLM response parsing failed. Returning user-friendly fallback.",
                action=fallback_action,
                expected_outcome="User receives a friendly error message instead of raw JSON.",
                confidence=0.0,
            )

    async def _generate_fast_path_thought(self, context: dict[str, Any]) -> Thought:
        """
        Lightweight iterative thought generation.
        """
        current_step = context["current_step"]
        mission = current_step.description

        # --- DYNAMIC HISTORY INJECTION ---
        # Core of loop: Agent sees its own steps
        fast_path_history = context.get("fast_path_history", [])
        history_text = ""
        if fast_path_history:
            history_text = "### ACTIONS YOU JUST TOOK (DO NOT REPEAT):\n"
            # Show last steps
            for item in fast_path_history[-6:]:
                tool = item.get("tool", "unknown")
                res = str(item.get("result", ""))
                # Truncate to save tokens but keep enough info
                preview = res[:600] + "..." if len(res) > 600 else res
                history_text += f"- Called `{tool}` -> Result: {preview}\n"
        # ---------------------------------

        mini_system_prompt = (
            "You are a fast, autonomous researcher (Cursor-like).\n"
            "Your goal is to answer the user's question comprehensively.\n\n"
            "STRATEGY:\n"
            "1. **Explore First:** If you don't have the answer yet, "
            "use tools to find it.\n"
            "2. **Handle Empty Pages:** If a wiki page is empty "
            "(isParentPage=true) or search fails, IMMEDIATELY try another "
            "path (e.g., list subpages, search again).\n"
            "3. **Chain Actions:** You can perform multiple tool calls in "
            "sequence.\n"
            "   - Example: list_wiki -> get_tree -> get_page -> respond.\n"
            "4. **Respond:** ONLY use 'respond' when you have gathered "
            "enough information to give a good answer.\n\n"
            "PARAMETER RULES:\n"
            "- Use IDs from history (e.g. Wiki UUIDs), never names.\n"
            "- Check conversation history for context.\n\n"
            "Available Tools:\n"
        )
        mini_system_prompt += self._get_tools_description()

        user_prompt = f"""
User Query: "{mission}"

{history_text}

Decide the next immediate action.
Return JSON matching this schema:
{{
  "action": "tool_call" | "respond",
  "tool": "<tool_name>",
  "tool_input": {{<params>}},
  "summary": "<content if respond>"
}}
"""
        
        # Add conversation history context (the "old" history)
        messages = [{"role": "system", "content": mini_system_prompt}]
        chat_history = context.get("conversation_history", [])[-6:]
        for msg in chat_history:
            if msg.get("role") != "system":
                messages.append(msg)
        
        messages.append({"role": "user", "content": user_prompt})

        self.logger.info("fast_path_thought_start")

        result = await self.llm_provider.complete(
            messages=messages,
            model="fast",  # Or "fast" for GPT-4o-mini
            response_format={"type": "json_object"},
            temperature=0.0
        )

        if not result.get("success"):
            raise RuntimeError(f"Fast thought failed: {result.get('error')}")

        # JSON Cleaning & Parsing (Robust)
        try:
            content = result["content"].strip()
            # Clean Markdown if present
            if "```" in content:
                import re
                match = re.search(
                    r"```(?:json)?\s*(\{.*?\})\s*```",
                    content,
                    re.DOTALL
                )
                if match:
                    content = match.group(1)

            data = json.loads(content)

            # Action Mapping logic (same as before)
            action_type_raw = data.get("action")
            if action_type_raw == "finish_step":
                action_type_raw = "respond"

            # Fallback for tool confusion
            if (
                action_type_raw not in {a.value for a in ActionType}
                and (data.get("tool") or data.get("tool_input"))
            ):
                action_type_raw = "tool_call"

            action = Action(
                type=ActionType(action_type_raw),
                tool=data.get("tool"),
                tool_input=data.get("tool_input"),
                question=data.get("question"),
                summary=data.get("summary")
            )

            return Thought(
                step_ref=1,
                rationale="Fast loop",
                action=action,
                confidence=1.0
            )

        except Exception as e:
            self.logger.error(
                "fast_thought_parse_error",
                error=str(e),
                content=result["content"]
            )
            return Thought(
                step_ref=1,
                rationale="Error",
                action=Action(
                    type=ActionType.RESPOND,
                    summary="Internal Error"
                ),
                confidence=0.0
            )

    async def _generate_markdown_response(
        self,
        context: dict[str, Any],
        previous_results: list[dict],
    ) -> str:
        """
        Generate final markdown response without JSON constraints.

        Called after ActionType.RESPOND to produce clean user output.
        This is Phase 2 of the two-phase response flow.

        Args:
            context: Response context with mission, conversation history, etc.
            previous_results: Results from previous tool executions

        Returns:
            Clean markdown-formatted response string
        """
        results_summary = self._summarize_results_for_response(previous_results)

        prompt = f"""Formuliere eine klare, gut strukturierte Antwort für den User.

## Kontext
{context.get('mission', 'Keine Mission angegeben')}

## Ergebnisse aus vorherigen Schritten
{results_summary}

## Anweisungen
- Antworte in Markdown
- Nutze Bullet-Points für Listen
- Fasse die wichtigsten Erkenntnisse zusammen
- KEIN JSON, keine Code-Blöcke außer wenn inhaltlich nötig
"""

        result = await self.llm_provider.complete(
            messages=[
                {"role": "system", "content": "Du bist ein hilfreicher Assistent."},
                {"role": "user", "content": prompt},
            ],
            model=self.model_alias,
            response_format=None,  # KEIN JSON-Mode!
            temperature=0.3,
        )

        if not result.get("success"):
            self.logger.error(
                "markdown_response_generation_failed",
                error=result.get("error"),
            )
            return "Entschuldigung, ich konnte keine Antwort generieren."

        return result["content"]

    def _build_response_context_for_respond(
        self, state: dict[str, Any], step: TodoItem
    ) -> dict[str, Any]:
        """
        Build context for markdown response generation.

        Args:
            state: Current session state
            step: Current TodoItem being executed

        Returns:
            Context dictionary for response generation
        """
        return {
            "mission": state.get("mission", step.description),
            "conversation_history": state.get("conversation_history", [])[-5:],
            "user_answers": state.get("answers", {}),
        }

    def _summarize_results_for_response(self, previous_results: list[dict]) -> str:
        """
        Summarize previous tool results for response context.

        Args:
            previous_results: List of previous execution results

        Returns:
            Formatted summary string
        """
        if not previous_results:
            return "Keine vorherigen Ergebnisse."

        summaries = []
        # NOTE: Increased limit from 200 to 4000 chars to avoid truncation bug
        # that caused data loss (e.g., 9 documents truncated to 1)
        MAX_PREVIEW_LENGTH = 4000
        
        for i, result in enumerate(previous_results[-5:], 1):
            tool = result.get("tool", "unknown")
            success = "✓" if result.get("success") or result.get("result", {}).get("success") else "✗"
            
            # Extract content from result data - prioritize 'summary' for formatted output
            data = result.get("result", result.get("data", {}))
            data_content = ""
            
            if isinstance(data, dict):
                # Prioritize 'summary' key as it contains the agent's formatted response
                if "summary" in data and data["summary"]:
                    data_content = str(data["summary"])
                else:
                    # Try other common content keys
                    for key in ["content", "response", "output", "data"]:
                        if key in data and data[key]:
                            data_content = str(data[key])
                            break
                    else:
                        data_content = str(data)
            else:
                data_content = str(data)
            
            # Only truncate if really necessary
            if len(data_content) > MAX_PREVIEW_LENGTH:
                data_content = data_content[:MAX_PREVIEW_LENGTH] + "... [truncated]"
            
            summaries.append(f"{i}. [{success}] {tool}: {data_content}")

        return "\n".join(summaries)

    async def _execute_action(
        self,
        action: Action,
        step: TodoItem,
        state: dict[str, Any],
        session_id: str,
        todolist: TodoList | None = None,
    ) -> Observation:
        """Execute action and return observation."""
        if action.type == ActionType.TOOL_CALL:
            return await self._execute_tool(action, step)

        elif action.type == ActionType.ASK_USER:
            # Store pending question in state
            answer_key = action.answer_key or f"step_{step.position}_q{step.attempts}"
            state["pending_question"] = {
                "answer_key": answer_key,
                "question": action.question,
                "for_step": step.position,
            }
            await self.state_manager.save_state(session_id, state)

            return Observation(
                success=True,
                data={"question": action.question, "answer_key": answer_key},
                requires_user=True,
            )

        elif action.type == ActionType.RESPOND:
            # OPTIMIZATION: If agent already provided a good summary, use it directly
            # This avoids an extra LLM call (~11s) and potential data loss from truncation
            if action.summary and len(action.summary) > 50:
                self.logger.info(
                    "using_direct_summary",
                    summary_length=len(action.summary),
                    hint="Agent provided summary directly, skipping two-phase LLM call",
                )
                return Observation(
                    success=True,
                    data={"summary": action.summary},
                )
            
            # Fallback to Two-Phase Response only if no good summary provided
            self.logger.info(
                "using_two_phase_response",
                hint="No direct summary, generating via separate LLM call",
            )
            context = self._build_response_context_for_respond(state, step)
            
            # Extract previous results from todolist if available
            # IMPORTANT: Include current step's result (position <= step.position)
            # because the current step may have already executed a tool in this iteration
            previous_results = []
            if todolist:
                previous_results = [
                    {
                        "step": s.position,
                        "description": s.description,
                        "tool": s.chosen_tool,
                        "result": s.execution_result,
                        "success": s.execution_result.get("success", False) if s.execution_result else False,
                    }
                    for s in todolist.items
                    if s.execution_result and s.position <= step.position
                ]

            markdown_response = await self._generate_markdown_response(
                context, previous_results
            )

            return Observation(
                success=True,
                data={"summary": markdown_response},
            )

        elif action.type == ActionType.COMPLETE:
            # COMPLETE = Early exit, use summary directly (no two-phase)
            return Observation(success=True, data={"summary": action.summary})

        elif action.type == ActionType.REPLAN:
            # Replanning would be handled by todolist_manager
            return Observation(success=True, data={"replan_reason": action.replan_reason})

        elif action.type == ActionType.FINISH_STEP:
            # Explicit signal that agent has verified and completed the step
            # Pass through the summary so _extract_final_message can find it
            return Observation(success=True, data={"summary": action.summary})

        else:
            return Observation(success=False, error=f"Unknown action type: {action.type}")

    async def _execute_tool(self, action: Action, step: TodoItem) -> Observation:
        """
        Execute tool with caching support.

        Before executing, checks the cache for identical requests.
        After successful execution of cacheable tools, stores results.

        Args:
            action: Action containing tool name and input
            step: Current TodoItem being executed

        Returns:
            Observation with tool result or cached result
        """
        tool = self.tools.get(action.tool)
        if not tool:
            return Observation(success=False, error=f"Tool not found: {action.tool}")

        tool_input = action.tool_input or {}

        # Check cache first for cacheable tools
        if self._tool_cache and self._is_cacheable_tool(action.tool):
            cached = self._tool_cache.get(action.tool, tool_input)
            if cached is not None:
                self.logger.info(
                    "tool_cache_hit",
                    tool=action.tool,
                    step=step.position,
                    cache_stats=self._tool_cache.stats,
                )
                return Observation(
                    success=cached.get("success", True),
                    data=cached,
                    error=cached.get("error"),
                )

        try:
            self.logger.info("tool_execution_start", tool=action.tool, step=step.position)
            result = await tool.execute(**tool_input)
            self.logger.info("tool_execution_end", tool=action.tool, step=step.position)

            # Cache successful results for cacheable tools
            if self._tool_cache and result.get("success", False):
                if self._is_cacheable_tool(action.tool):
                    self._tool_cache.put(action.tool, tool_input, result)
                    self.logger.debug(
                        "tool_result_cached",
                        tool=action.tool,
                        step=step.position,
                        cache_size=self._tool_cache.size,
                    )

            return Observation(
                success=result.get("success", False),
                data=result,
                error=result.get("error"),
            )
        except Exception as e:
            self.logger.error("tool_execution_exception", tool=action.tool, error=str(e))
            return Observation(success=False, error=str(e))

    def _is_cacheable_tool(self, tool_name: str) -> bool:
        """
        Determine if tool results should be cached.

        Only read-only tools are cacheable. Write operations (file_write,
        git commit, etc.) should never be cached as they have side effects.

        Args:
            tool_name: Name of the tool

        Returns:
            True if tool results can be safely cached
        """
        return tool_name in self.CACHEABLE_TOOLS

    async def _process_observation(
        self,
        step: TodoItem,
        observation: Observation,
        action: Action,
        todolist: TodoList,
        state: dict[str, Any],
        session_id: str,
    ) -> None:
        """
        Process observation and update step status.

        Key behavior: Tool success does NOT auto-complete a step. The agent must
        explicitly emit FINISH_STEP to mark a step as completed. This allows
        the agent to iterate (e.g., run tests after writing code) and self-heal
        errors before declaring the task done.
        """
        # Update step with execution details (only set tool/input if action has them)
        if action.tool:
            step.chosen_tool = action.tool
            step.tool_input = action.tool_input
        step.execution_result = observation.data
        step.attempts += 1

        # Initialize execution history if needed
        if step.execution_history is None:
            step.execution_history = []

        # Track execution history
        step.execution_history.append(
            {
                "tool": action.tool,
                "success": observation.success,
                "error": observation.error,
                "attempt": step.attempts,
            }
        )

        # Update status based on action type and observation
        if action.type in (ActionType.FINISH_STEP, ActionType.RESPOND):
            # Explicit completion signal from agent (RESPOND is the new name)
            step.status = TaskStatus.COMPLETED
            self.logger.info(
                "step_completed_explicitly",
                session_id=session_id,
                step=step.position,
                total_attempts=step.attempts,
            )
        elif observation.success:
            # Tool succeeded but step is NOT complete - agent must continue iterating
            step.status = TaskStatus.PENDING
            step.attempts = 0  # Reset attempts for extended workflows
            self.logger.info(
                "tool_success_continuing_iteration",
                session_id=session_id,
                step=step.position,
                tool=action.tool,
            )
        else:
            # Tool execution failed
            if step.attempts >= step.max_attempts:
                step.status = TaskStatus.FAILED
                self.logger.error("step_exhausted", session_id=session_id, step=step.position)
            else:
                # Reset to PENDING for retry
                step.status = TaskStatus.PENDING
                self.logger.info(
                    "retry_step", session_id=session_id, step=step.position, attempt=step.attempts
                )

        # Persist changes
        await self.todolist_manager.update_todolist(todolist)
        await self.state_manager.save_state(session_id, state)

    def _is_plan_complete(self, todolist: TodoList) -> bool:
        """Check if all steps are completed or skipped.
        
        An empty plan is NOT complete - it indicates a planning failure
        that requires recovery.
        """
        if not todolist.items:
            return False  # Empty plan is broken, not complete
            
        return all(s.status in (TaskStatus.COMPLETED, TaskStatus.SKIPPED) for s in todolist.items)

    async def _route_query(
        self, mission: str, state: dict[str, Any], session_id: str
    ) -> RouterResult:
        """
        Route query through classifier to determine execution path.

        Args:
            mission: User's mission/query
            state: Current session state
            session_id: Session identifier for logging

        Returns:
            RouterResult with decision, confidence, and rationale
        """
        todolist_id = state.get("todolist_id")
        todolist = None
        todolist_completed = False

        if todolist_id:
            try:
                todolist = await self.todolist_manager.load_todolist(todolist_id)
                todolist_completed = self._is_plan_complete(todolist)
            except FileNotFoundError:
                pass

        context = RouterContext(
            query=mission,
            has_active_todolist=todolist is not None,
            todolist_completed=todolist_completed,
            previous_results=self._get_previous_results(todolist) if todolist else [],
            conversation_history=state.get("conversation_history", []),
            last_query=state.get("last_query"),
        )

        result = await self._router.classify(context)

        self.logger.info(
            "route_decision",
            session_id=session_id,
            decision=result.decision.value,
            confidence=result.confidence,
            rationale=result.rationale,
        )

        return result

    def _get_previous_results(self, todolist: TodoList) -> list[dict[str, Any]]:
        """
        Extract previous execution results from todolist.

        Args:
            todolist: TodoList to extract results from

        Returns:
            List of result dictionaries from completed steps
        """
        results = []
        for step in todolist.items:
            if step.execution_result and step.status == TaskStatus.COMPLETED:
                results.append({
                    "step": step.position,
                    "description": step.description,
                    "tool": step.chosen_tool,
                    "result": step.execution_result,
                })
        return results

    async def _execute_fast_path(
        self,
        mission: str,
        state: dict[str, Any],
        session_id: str,
        execution_history: list[dict[str, Any]],
    ) -> ExecutionResult:
        """
        Execute query using a fast ReAct loop (Cursor-Style).
        Allows multiple steps (max 5) to explore/research before answering.
        """
        # 1. Synthetic Step initialization
        synthetic_step = TodoItem(
            position=1,
            description=mission,
            acceptance_criteria="User query answered",
            dependencies=[],
            status=TaskStatus.PENDING,
        )

        # Initial context loading
        todolist_id = state.get("todolist_id")
        previous_results = []
        if todolist_id:
            try:
                previous_todolist = await self.todolist_manager.load_todolist(todolist_id)
                previous_results = self._get_previous_results(previous_todolist)
            except FileNotFoundError:
                pass

        # Prompt Injection: Force research behavior
        user_answers = dict(state.get("answers", {}))
        user_answers["IMPORTANT_INSTRUCTION"] = (
            "Do NOT ask clarifying questions. If a page is empty/folder, find subpages. "
            "Read multiple pages if necessary to give a comprehensive answer."
        )

        MAX_FAST_STEPS = 5  # The "Cursor Limit"
        current_loop = 0
        
        self.logger.info("fast_path_loop_start", session_id=session_id)

        # --- THE FAST LOOP ---
        while current_loop < MAX_FAST_STEPS:
            current_loop += 1
            
            # Build Context: Include history of THIS fast session
            # Crucial: agent sees "I just read Page X and it was empty"
            current_session_history = [
                {
                    "tool": h["data"]["action"]["tool"],
                    "result": str(
                        h["data"]["action"].get("summary")
                        or "Tool executed"
                    )
                }
                if (
                    h["type"] == "thought"
                    and h.get("data")
                    and isinstance(h["data"], dict)
                    and "action" in h["data"]
                )
                else {
                    "tool": "unknown",
                    "result": str(
                        h.get("data", {}).get("data")
                        if h.get("data")
                        else "No data"
                    )
                }
                for h in execution_history
                if h["type"] in ("observation", "thought")
            ]

            context = {
                "current_step": synthetic_step,
                "previous_results": previous_results,  # Old stuff
                "fast_path_history": current_session_history,  # Current
                "conversation_history": state.get(
                    "conversation_history", []
                ),
                "user_answers": user_answers,
                "fast_path": True,
            }

            # 2. Think
            thought = await self._generate_fast_path_thought(context)
            
            execution_history.append({
                "type": "thought",
                "step": current_loop,
                "data": asdict(thought),
                "fast_path": True,
            })

            # 3. Act based on Decision

            # CASE A: Respond / Finish (Exit Loop)
            if thought.action.type in (
                ActionType.COMPLETE,
                ActionType.FINISH_STEP,
                ActionType.RESPOND
            ):

                # Check if we actually have a summary. If not, generate one
                final_msg = thought.action.summary
                if not final_msg:
                    # Generate response from gathered tools
                    final_msg = await self._generate_fast_path_completion(
                        mission, "fast_path_tools", execution_history
                    )

                self.logger.info(
                    "fast_path_direct_completion",
                    session_id=session_id,
                    steps_taken=current_loop
                )
                return ExecutionResult(
                    session_id=session_id,
                    status="completed",
                    final_message=final_msg,
                    execution_history=execution_history,
                    todolist_id=state.get("todolist_id"),
                )

            # CASE B: Ask User (Break Loop)
            if thought.action.type == ActionType.ASK_USER:
                return ExecutionResult(
                    session_id=session_id,
                    status="paused",
                    final_message=thought.action.question,
                    execution_history=execution_history,
                    todolist_id=None,
                    pending_question={"question": thought.action.question}
                )

            # CASE C: Tool Call (Continue Loop)
            if thought.action.type == ActionType.TOOL_CALL:
                observation = await self._execute_tool(
                    thought.action, synthetic_step
                )

                execution_history.append({
                    "type": "observation",
                    "step": current_loop,
                    "data": asdict(observation),
                    "fast_path": True,
                })

                if not observation.success:
                    self.logger.warning(
                        "fast_path_tool_failed",
                        tool=thought.action.tool,
                        error=observation.error
                    )
                    # Loop continues! Agent sees error in next step

                # Loop automatically continues to next iteration...

        # Fallback if loop exhausted
        self.logger.warning(
            "fast_path_loop_exhausted", session_id=session_id
        )
        # Try to summarize whatever we have
        final_summary = await self._generate_fast_path_completion(
            mission, "exhausted", execution_history
        )
        return ExecutionResult(
            session_id=session_id,
            status="completed",
            final_message=final_summary,
            execution_history=execution_history,
            todolist_id=state.get("todolist_id"),
        )

    async def _execute_full_path(
        self,
        mission: str,
        state: dict[str, Any],
        session_id: str,
        execution_history: list[dict[str, Any]],
    ) -> ExecutionResult:
        """
        Execute full planning path (standard ReAct loop).

        This is extracted from execute() to support fast-path fallback.
        Creates a TodoList and executes the full ReAct loop.

        Args:
            mission: User's mission/query
            state: Current session state
            session_id: Session identifier
            execution_history: List to record execution events

        Returns:
            ExecutionResult with status and final message
        """
        # Check if we have a completed todolist and should reset for new query
        if not state.get("pending_question"):
            todolist_id = state.get("todolist_id")
            if todolist_id:
                try:
                    existing_todolist = await self.todolist_manager.load_todolist(todolist_id)
                    if self._is_plan_complete(existing_todolist):
                        self.logger.info(
                            "completed_todolist_detected_resetting",
                            session_id=session_id,
                            old_todolist_id=todolist_id,
                        )
                        state.pop("todolist_id", None)
                        await self.state_manager.save_state(session_id, state)
                except FileNotFoundError:
                    self.logger.warning(
                        "todolist_file_not_found",
                        session_id=session_id,
                        todolist_id=todolist_id,
                    )

        # Get or create TodoList
        todolist = await self._get_or_create_todolist(state, mission, session_id)

        # Empty plan recovery
        if not todolist.items:
            self.logger.warning(
                "empty_plan_detected_injecting_recovery",
                session_id=session_id,
                todolist_id=todolist.todolist_id,
            )
            recovery_step = TodoItem(
                position=1,
                description="Analyze the mission and create a valid execution plan.",
                acceptance_criteria="A plan with at least one actionable step is created.",
                dependencies=[],
                status=TaskStatus.PENDING,
            )
            todolist.items.append(recovery_step)
            await self.todolist_manager.update_todolist(todolist)

        # Execute ReAct loop
        iteration = 0
        while not self._is_plan_complete(todolist) and iteration < self.MAX_ITERATIONS:
            iteration += 1
            self.logger.info("react_iteration", session_id=session_id, iteration=iteration)

            current_step = self._get_next_actionable_step(todolist)
            if not current_step:
                self.logger.info("no_actionable_steps", session_id=session_id)
                break

            self.logger.info(
                "step_start",
                session_id=session_id,
                step=current_step.position,
                description=current_step.description[:50],
            )

            context = self._build_thought_context(current_step, todolist, state)
            if state.get("conversation_history"):
                context["conversation_history"] = state.get("conversation_history")
            thought = await self._generate_thought(context)
            execution_history.append(
                {"type": "thought", "step": current_step.position, "data": asdict(thought)}
            )

            if thought.action.type == ActionType.REPLAN:
                self.logger.info("executing_replan", session_id=session_id)
                todolist = await self._replan(current_step, thought, todolist, state, session_id)
                observation = Observation(success=True, data={"replan": "executed"})
                execution_history.append({
                    "type": "observation",
                    "step": current_step.position,
                    "data": asdict(observation),
                })
                continue
            else:
                observation = await self._execute_action(
                    thought.action, current_step, state, session_id, todolist
                )

            execution_history.append({
                "type": "observation",
                "step": current_step.position,
                "data": asdict(observation),
            })

            await self._process_observation(
                current_step, observation, thought.action, todolist, state, session_id
            )

            if observation.requires_user:
                self.logger.info("execution_paused_for_user", session_id=session_id)
                pending_q = state.get("pending_question")
                return ExecutionResult(
                    session_id=session_id,
                    status="paused",
                    final_message=pending_q.get("question", "Waiting for user input")
                    if pending_q
                    else "Waiting for user input",
                    execution_history=execution_history,
                    todolist_id=todolist.todolist_id,
                    pending_question=pending_q,
                )

            if thought.action.type == ActionType.COMPLETE:
                # COMPLETE = Early exit, skip all remaining steps
                self.logger.info("early_completion", session_id=session_id)
                current_step.status = TaskStatus.COMPLETED
                current_step.execution_result = {"summary": thought.action.summary}
                for step in todolist.items:
                    if step.status == TaskStatus.PENDING:
                        step.status = TaskStatus.SKIPPED
                await self.todolist_manager.update_todolist(todolist)
                await self.state_manager.save_state(session_id, state)

                return ExecutionResult(
                    session_id=session_id,
                    status="completed",
                    final_message=thought.action.summary or "Mission completed",
                    execution_history=execution_history,
                    todolist_id=todolist.todolist_id,
                )
            # Note: RESPOND and FINISH_STEP are handled via _process_observation,
            # they only complete the current step, not the entire mission

        # Determine final status
        if self._is_plan_complete(todolist):
            status = "completed"
            final_message = self._extract_final_message(todolist, execution_history)
            # DEBUG: Log what _extract_final_message returned
            self.logger.info(
                "full_path_final_message",
                session_id=session_id,
                final_message_preview=final_message[:200] if final_message else "None",
                final_message_type=type(final_message).__name__,
            )
        elif iteration >= self.MAX_ITERATIONS:
            status = "failed"
            final_message = f"Exceeded maximum iterations ({self.MAX_ITERATIONS})"
        else:
            status = "failed"
            final_message = "Execution stopped with incomplete tasks"

        self.logger.info("execute_complete", session_id=session_id, status=status)

        return ExecutionResult(
            session_id=session_id,
            status=status,
            final_message=final_message,
            execution_history=execution_history,
            todolist_id=todolist.todolist_id,
        )

    def _extract_summary_from_data(self, data: Any) -> str:
        """
        Extract human-readable summary from observation data.
        
        Never returns raw JSON - always extracts meaningful text or
        returns a generic completion message.
        """
        if isinstance(data, str):
            return data
        
        if isinstance(data, dict):
            # Priority keys for extracting text
            for key in ["summary", "content", "response", "result", "message"]:
                if key in data and isinstance(data[key], str):
                    return data[key].strip()
            
            # Check nested 'data' dict
            if "data" in data and isinstance(data["data"], dict):
                for key in ["summary", "content", "response", "result"]:
                    if key in data["data"] and isinstance(data["data"][key], str):
                        return data["data"][key].strip()
        
        # Fallback - never return raw JSON
        return "Task completed successfully."

    async def _generate_fast_path_completion(
        self, query: str, tool_name: str, execution_history: Any
    ) -> str:
        """
        Generate final answer from execution history.

        Bypasses the heavy 'Thought' process for better large context
        handling without system prompt overhead.

        Args:
            query: The user's original query/mission
            tool_name: Name of tool executed or "exhausted"/"fast_path_tools"
            execution_history: The execution history with observations

        Returns:
            Generated response message as string
        """
        # Extract tool results from execution history
        tool_results = []
        if isinstance(execution_history, list):
            for entry in execution_history:
                if entry.get("type") == "observation":
                    data = entry.get("data", {})
                    tool_results.append(str(data))
        else:
            # Fallback for old signature compatibility
            tool_results.append(str(execution_history))

        results_str = (
            "\n\n".join(tool_results)
            if tool_results
            else "No results available"
        )

        # Lean prompt focused only on answer
        prompt = f"""
Du beantwortest die User-Frage basierend auf den folgenden Tool-Ergebnissen.

User Frage: "{query}"

Tool-Ergebnisse:
{results_str}

Anweisung:
- Antworte direkt und präzise auf die Frage.
- Nutze Markdown.
- Zitiere Quellen, falls im Ergebnis vorhanden.
- Wenn das Ergebnis die Frage nicht beantwortet, sage das ehrlich.
"""

        result = await self.llm_provider.complete(
            messages=[
                {
                    "role": "system",
                    "content": "Du bist ein hilfreicher Assistent."
                },
                {"role": "user", "content": prompt}
            ],
            model="fast",
            temperature=0.3,
            # IMPORTANT: No JSON Mode! Allows model to breathe freely
        )

        if result.get("success"):
            return result["content"]
        return "Task completed (could not generate summary)."

    def _extract_final_message(
        self, todolist: TodoList, execution_history: list[dict[str, Any]]
    ) -> str:
        """
        Extract meaningful final message from completed plan.

        Aggregates summaries from all completed steps to form a cohesive answer.
        For multi-step plans, combines results with step headers.

        Args:
            todolist: Completed TodoList
            execution_history: Execution history with thoughts and observations

        Returns:
            Aggregated message from all steps or default completion message
        """
        messages = []
        # Priority list of keys to extract text from
        # 'summary' is top priority because FINISH_STEP uses it
        keys_to_check = [
            "summary", "generated_text", "response", "content", "result"
        ]

        # Iterate through ALL completed steps to gather the full story
        for step in todolist.items:
            if step.status == TaskStatus.COMPLETED and step.execution_result:
                result = step.execution_result
                text = None
                
                # DEBUG: Log what execution_result contains
                self.logger.debug(
                    "extract_final_message_step",
                    step_position=step.position,
                    result_type=type(result).__name__,
                    result_keys=list(result.keys()) if isinstance(result, dict) else "N/A",
                    result_preview=str(result)[:200] if result else "None",
                )

                if isinstance(result, dict):
                    # Check top-level keys
                    for key in keys_to_check:
                        if key in result:
                            val = result[key]
                            if isinstance(val, str) and val.strip():
                                text = val.strip()
                                break

                    # Check inside 'data' sub-dict (standard tool result format)
                    if not text and result.get("success"):
                        data = result.get("data")
                        if isinstance(data, dict):
                            for key in keys_to_check:
                                if key in data:
                                    val = data[key]
                                    if isinstance(val, str) and val.strip():
                                        text = val.strip()
                                        break

                if text:
                    # Add step header for multi-step plans
                    if len(todolist.items) > 1:
                        messages.append(f"**Step {step.position}:** {text}")
                    else:
                        messages.append(text)

        if messages:
            return "\n\n".join(messages)

        # Fallback: return default message
        return "All tasks completed successfully."

    async def close(self) -> None:
        """
        Clean up agent resources, especially MCP client connections.

        This method must be called when the agent is no longer needed to
        properly close MCP client context managers. Failing to call this
        can result in 'cancel scope in different task' errors from anyio.

        The method is idempotent and safe to call multiple times.
        """
        import asyncio
        
        # Close MCP contexts if they exist (set by factory)
        mcp_contexts = getattr(self, "_mcp_contexts", None)
        if mcp_contexts:
            for ctx in mcp_contexts:
                try:
                    await ctx.__aexit__(None, None, None)
                except (RuntimeError, asyncio.CancelledError) as e:
                    # Suppress cancel scope errors during shutdown - these occur when
                    # anyio TaskGroups are being cleaned up in different task contexts.
                    # This is expected during CLI shutdown and harmless.
                    if "cancel scope" in str(e).lower() or isinstance(e, asyncio.CancelledError):
                        self.logger.debug(
                            "mcp_context_close_cancelled",
                            error=str(e),
                            hint="Expected during shutdown, harmless",
                        )
                    else:
                        self.logger.warning(
                            "mcp_context_close_error",
                            error=str(e),
                            error_type=type(e).__name__,
                        )
                except Exception as e:
                    self.logger.warning(
                        "mcp_context_close_error",
                        error=str(e),
                        error_type=type(e).__name__,
                    )
            # Clear the list to prevent double-close
            self._mcp_contexts = []
