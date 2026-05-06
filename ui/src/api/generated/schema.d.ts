/* eslint-disable */
// THIS FILE IS GENERATED. Run `pnpm run generate-api` to refresh.
export interface paths {
    "/api/v1/execute": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Execute Mission
         * @description Execute agent mission synchronously.
         *
         *     Executes the given mission and returns the final result when complete.
         *     This endpoint blocks until execution finishes or fails.
         *
         *     Uses Agent with native OpenAI tool calling.
         *
         *     **RAG Mode:**
         *
         *     When `user_id`, `org_id`, or `scope` is provided, the agent
         *     operates in RAG mode with security-filtered document access.
         *
         *     **Returns:**
         *
         *     - `session_id`: Can be used to resume or reference this session
         *     - `status`: Final execution status
         *     - `message`: Summary of what the agent accomplished
         *
         *     **Error Handling:**
         *
         *     - Returns HTTP 500 with error details on execution failure
         */
        post: operations["execute_mission_api_v1_execute_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/execute/stream": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Execute Mission Stream
         * @description Execute mission with streaming progress via Server-Sent Events.
         *
         *     Streams execution progress as SSE events. Each event is a JSON-encoded
         *     ProgressUpdate: ``{"timestamp", "event_type", "message", "details"}``.
         *
         *     Event types: started, step_start, llm_token, tool_call, tool_result,
         *     plan_updated, ask_user, thought, observation, final_answer, complete, error.
         *
         *     Typical sequence::
         *
         *         started -> step_start -> tool_call -> tool_result
         *                 -> step_start -> llm_token* -> final_answer -> complete
         *
         *     See ``docs/api.md`` for full SSE event reference and client examples.
         */
        post: operations["execute_mission_stream_api_v1_execute_stream_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/execute/{session_id}/cancel": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Cancel Mission
         * @description Request a cooperative pause for a running mission.
         *
         *     The agent completes its current step (LLM call + any in-flight tool
         *     calls), persists state via the same mechanism used by ``ask_user``,
         *     and exits with ``ExecutionStatus.PAUSED``.  Resume by posting a new
         *     mission to ``/execute`` (or ``/execute/stream``) with the same
         *     ``session_id``.
         */
        post: operations["cancel_mission_api_v1_execute__session_id__cancel_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/agents": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List all agents
         * @description List all agents (custom + profile). Corrupt YAML files are skipped.
         */
        get: operations["list_agents_api_v1_agents_get"];
        put?: never;
        /**
         * Create custom agent
         * @description Create a new custom agent definition and persist as YAML
         */
        post: operations["create_agent_api_v1_agents_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/agents/{agent_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get agent by ID
         * @description Retrieve a specific agent definition by ID
         */
        get: operations["get_agent_api_v1_agents__agent_id__get"];
        /**
         * Update custom agent
         * @description Update an existing custom agent definition
         */
        put: operations["update_agent_api_v1_agents__agent_id__put"];
        post?: never;
        /**
         * Delete custom agent
         * @description Delete a custom agent definition
         */
        delete: operations["delete_agent_api_v1_agents__agent_id__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/agents/{agent_id}/deploy": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Deploy a custom agent
         * @description Validate and deploy the current definition of a custom agent. On success the agent becomes the active version for the target environment and is immediately available to ``POST /api/v1/execute``.
         */
        post: operations["deploy_agent_api_v1_agents__agent_id__deploy_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/agents/{agent_id}/rollback": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Roll back to a previously deployed version */
        post: operations["rollback_agent_api_v1_agents__agent_id__rollback_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/agents/{agent_id}/deployments": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List deployment history (newest first) */
        get: operations["list_deployments_api_v1_agents__agent_id__deployments_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/agents/{agent_id}/active": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get the currently active deployment for an environment */
        get: operations["get_active_deployment_api_v1_agents__agent_id__active_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/agent-templates": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List agent templates for the wizard
         * @description Return all wizard templates, filtered to tools the server can resolve.
         */
        get: operations["list_agent_templates_api_v1_agent_templates_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/agent-templates/{template_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get a single agent template */
        get: operations["get_agent_template_api_v1_agent_templates__template_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/agent-templates/compose-prompt": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Compose a system prompt from wizard step 4 inputs
         * @description Turn the user's tone/language/rules into a ready-to-use system prompt.
         *
         *     With ``use_ai=false`` the response is deterministic (no LLM call). With
         *     ``use_ai=true`` the deterministic draft is sent to the LLM for one
         *     refinement pass; if the call fails the deterministic version is returned
         *     so the wizard never blocks on a missing API key. The wizard distinguishes
         *     "AI ran successfully" (``used_ai=true``) from "AI was attempted but
         *     failed" (``ai_attempted=true, used_ai=false, ai_error=...``) so the UI
         *     can show an honest status to the user.
         */
        post: operations["compose_prompt_api_v1_agent_templates_compose_prompt_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/tools": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get tool catalog
         * @description Retrieve the service tool catalog with all available native tools
         */
        get: operations["get_tools_api_v1_tools_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/gateway/{channel}/messages": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Handle Message
         * @description Handle an inbound message from any channel.
         *
         *     The channel path parameter identifies the source (e.g. 'telegram', 'teams',
         *     'rest'). The gateway manages session mapping, conversation history,
         *     agent execution, and outbound reply dispatch.
         */
        post: operations["handle_message_api_v1_gateway__channel__messages_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/gateway/{channel}/webhook": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Handle Webhook
         * @description Handle a raw webhook payload from an external channel.
         *
         *     Uses the channel's InboundAdapter to normalize the raw payload,
         *     verify its signature, and then process it through the gateway.
         *
         *     The ``profile`` and ``plugin_path`` query parameters allow callers
         *     to configure which agent handles messages for this webhook. For
         *     example, when registering a Telegram webhook URL::
         *
         *         https://example.com/gateway/telegram/webhook?profile=accounting_agent&plugin_path=examples/accounting_agent
         */
        post: operations["handle_webhook_api_v1_gateway__channel__webhook_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/gateway/notify": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Send Notification
         * @description Send a proactive push notification to a registered recipient.
         */
        post: operations["send_notification_api_v1_gateway_notify_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/gateway/broadcast": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Broadcast
         * @description Broadcast a message to all registered recipients on a channel.
         */
        post: operations["broadcast_api_v1_gateway_broadcast_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/gateway/channels": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Channels
         * @description List all communication channels with outbound senders configured.
         */
        get: operations["list_channels_api_v1_gateway_channels_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/health": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Health Check
         * @description Liveness probe - is the service running?
         */
        get: operations["health_check_health_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/health/ready": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Readiness Check
         * @description Readiness probe - can the service handle requests?
         *
         *     Verifies that core dependencies are reachable:
         *     - Tool registry can be loaded
         *     - Profile configuration directory exists
         */
        get: operations["readiness_check_health_ready_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/memory/list": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Pages
         * @description List wiki pages for a given profile.
         */
        get: operations["list_pages_api_v1_memory_list_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/memory/page/{name}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Page
         * @description Return one wiki page by its relative path.
         */
        get: operations["get_page_api_v1_memory_page__name__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/conversations": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Active Conversations
         * @description List all active (non-archived) conversations.
         */
        get: operations["list_active_conversations_api_v1_conversations_get"];
        put?: never;
        /**
         * Create Conversation
         * @description Create a new conversation, archiving any existing active one for the channel.
         */
        post: operations["create_conversation_api_v1_conversations_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/conversations/archived": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Archived Conversations
         * @description List archived conversations.
         */
        get: operations["list_archived_conversations_api_v1_conversations_archived_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/conversations/{conversation_id}/messages": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Messages
         * @description Get messages for a conversation.
         */
        get: operations["get_messages_api_v1_conversations__conversation_id__messages_get"];
        put?: never;
        /**
         * Append Message
         * @description Send a message to the agent within a conversation.
         *
         *     Appends the user message, runs the agent, and appends the reply.
         */
        post: operations["append_message_api_v1_conversations__conversation_id__messages_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/conversations/{conversation_id}/messages/stream": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Stream a chat reply via SSE
         * @description Append a user message, run the agent, and stream tokens back as SSE.
         *
         *     The user message is persisted before the stream starts. The
         *     assistant reply is persisted in the ``finally`` block so that even
         *     a cancelled or failed stream leaves the conversation in a sane
         *     state (with a ``[partial]`` marker if the run did not complete).
         */
        post: operations["stream_message_api_v1_conversations__conversation_id__messages_stream_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/conversations/{conversation_id}/archive": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Archive Conversation
         * @description Archive a conversation with an optional summary.
         */
        post: operations["archive_conversation_api_v1_conversations__conversation_id__archive_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/conversations/{conversation_id}/fork": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Fork a conversation into a fresh copy
         * @description Create a new conversation seeded with the source's messages.
         *
         *     Use case: replay a past conversation through a different profile or
         *     LLM model without mutating the original transcript.
         */
        post: operations["fork_conversation_api_v1_conversations__conversation_id__fork_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/workflows/definitions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Workflow Definitions
         * @description List first-class workflow definitions.
         */
        get: operations["list_workflow_definitions_api_v1_workflows_definitions_get"];
        put?: never;
        /**
         * Save Workflow Definition
         * @description Create or update a first-class workflow definition.
         *
         *     ADR-022 §7 / G3: when the definition's trigger is ``schedule``, the
         *     runtime mirror-registers the cron job in the framework's scheduler
         *     so the workflow actually fires on its expression. Re-saving with a
         *     different cron is idempotent — the prior job is removed first.
         *     Removing the schedule trigger entirely also removes the registered
         *     job.
         */
        post: operations["save_workflow_definition_api_v1_workflows_definitions_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/workflows/definitions/{workflow_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Workflow Definition
         * @description Get a first-class workflow definition.
         */
        get: operations["get_workflow_definition_api_v1_workflows_definitions__workflow_id__get"];
        put?: never;
        post?: never;
        /**
         * Delete Workflow Definition
         * @description Delete a first-class workflow definition and its scheduled job.
         */
        delete: operations["delete_workflow_definition_api_v1_workflows_definitions__workflow_id__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/workflows/definitions/{workflow_id}/run": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Run Workflow Definition
         * @description Run a first-class workflow definition sequentially by dependency order.
         */
        post: operations["run_workflow_definition_api_v1_workflows_definitions__workflow_id__run_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/workflows/webhooks/{trigger_path}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Trigger Workflow Webhook
         * @description Run the workflow whose ``webhook`` trigger matches ``trigger_path``.
         *
         *     ADR-022 §7: a workflow definition with::
         *
         *         trigger: webhook
         *         trigger_config:
         *           path: hooks/daily-report
         *           secret_env: GITHUB_WEBHOOK_SECRET   # or: secret: <inline>
         *           signature_header: X-Hub-Signature-256
         *           signature_algo: sha256
         *
         *     becomes reachable at ``POST /api/v1/workflows/webhooks/hooks/daily-report``.
         *     The route bypasses the auth middleware (the path prefix is in
         *     ``exempt_path_prefixes``) and verifies the per-workflow HMAC
         *     signature itself before invoking the runtime. With no secret
         *     configured the webhook is open — that is the operator's choice and
         *     must be made deliberately.
         */
        post: operations["trigger_workflow_webhook_api_v1_workflows_webhooks__trigger_path__post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/workflows/wait": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Create Wait Checkpoint
         * @description Create a waiting checkpoint for a workflow run.
         */
        post: operations["create_wait_checkpoint_api_v1_workflows_wait_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/workflows/{run_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Checkpoint
         * @description Get workflow checkpoint by run id.
         */
        get: operations["get_checkpoint_api_v1_workflows__run_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/workflows/{run_id}/resume": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Resume Workflow
         * @description Resume a waiting workflow with external input payload.
         */
        post: operations["resume_workflow_api_v1_workflows__run_id__resume_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/workflows/{run_id}/resume-and-continue": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Resume And Continue Workflow
         * @description Resume checkpoint and continue workflow by re-invoking activate_skill.
         */
        post: operations["resume_and_continue_workflow_api_v1_workflows__run_id__resume_and_continue_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/acp/peers": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Peers
         * @description List every peer persisted under ``acp_peers.json``.
         */
        get: operations["list_peers_api_v1_acp_peers_get"];
        put?: never;
        /** Register a new ACP peer */
        post: operations["create_peer_api_v1_acp_peers_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/acp/status": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Status Endpoint */
        get: operations["status_endpoint_api_v1_acp_status_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/acp/peers/{name}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /** Replace an ACP peer (creates if missing) */
        put: operations["update_peer_api_v1_acp_peers__name__put"];
        post?: never;
        /** Remove an ACP peer */
        delete: operations["delete_peer_api_v1_acp_peers__name__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/acp/peers/{name}/test": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Probe an ACP peer for connectivity */
        post: operations["test_peer_api_v1_acp_peers__name__test_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/profiles": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List all profiles
         * @description Discover every profile available to the running server.
         */
        get: operations["list_profiles_api_v1_profiles_get"];
        put?: never;
        /**
         * Create a new user profile
         * @description Persist a new YAML profile to the user-profiles directory.
         */
        post: operations["create_profile_api_v1_profiles_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/profiles/available-as-subagent": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List profiles usable as a sub-agent
         * @description Return the same profile catalog minus an optional parent profile.
         */
        get: operations["list_subagent_candidates_api_v1_profiles_available_as_subagent_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/profiles/{name}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get a profile by name
         * @description Return the parsed config and the original source text for ``name``.
         */
        get: operations["get_profile_api_v1_profiles__name__get"];
        /**
         * Update a user profile
         * @description Overwrite a user-owned YAML profile while preserving comments.
         */
        put: operations["update_profile_api_v1_profiles__name__put"];
        post?: never;
        /** Delete a user profile */
        delete: operations["delete_profile_api_v1_profiles__name__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/profiles/{source}/clone": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Clone a (read-only) profile into the user-profiles directory
         * @description Copy ``source`` into the user-profiles directory under ``target_name``.
         *
         *     Lets the UI customize butler / coding_agent / rag_agent profiles without
         *     touching the read-only files shipped by the agent packages.
         */
        post: operations["clone_profile_api_v1_profiles__source__clone_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/skills": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List all available skills
         * @description Return every skill discovered by the global SkillService.
         */
        get: operations["list_skills_api_v1_skills_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/skills/{name}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Read a skill (frontmatter + body)
         * @description Return the parsed skill metadata plus the SKILL.md body.
         */
        get: operations["get_skill_api_v1_skills__name__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/llm/models": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List configured LLM model aliases
         * @description Return every alias from the active ``llm_config.yaml``.
         */
        get: operations["list_llm_models_api_v1_llm_models_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/planning-strategies": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List supported planning strategies */
        get: operations["list_planning_strategies_api_v1_planning_strategies_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/files": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Upload a file */
        post: operations["upload_file_api_v1_files_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/files/{file_id}/meta": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get file metadata */
        get: operations["get_file_meta_api_v1_files__file_id__meta_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/files/{file_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Download a file */
        get: operations["download_file_api_v1_files__file_id__get"];
        put?: never;
        post?: never;
        /** Delete a file */
        delete: operations["delete_file_api_v1_files__file_id__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/analytics/token-usage": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Aggregated token usage over time */
        get: operations["token_usage_api_v1_analytics_token_usage_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/analytics/cost-summary": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Today / week / month cost roll-up */
        get: operations["cost_summary_api_v1_analytics_cost_summary_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/analytics/conversations/{conversation_id}/usage": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Per-conversation token usage breakdown */
        get: operations["conversation_usage_api_v1_analytics_conversations__conversation_id__usage_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/runs/active": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List currently running executions */
        get: operations["list_active_runs_api_v1_runs_active_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/runs/recent": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List recent runs (active + recently finished, captured by the trace store) */
        get: operations["list_recent_runs_api_v1_runs_recent_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/runs/{session_id}/trace": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Return the recorded ReAct trace for a run */
        get: operations["get_run_trace_api_v1_runs__session_id__trace_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/runs/active/stream": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Stream active-runs snapshots via SSE */
        get: operations["stream_active_runs_api_v1_runs_active_stream_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/mcp/probe": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Probe an MCP server and return its tool catalog
         * @description Connect briefly to an MCP server and list its tools.
         *
         *     Used by the agent editor to validate an MCP entry and populate the
         *     ``mcp_tool_allowlist`` multi-select.
         */
        post: operations["probe_mcp_api_v1_mcp_probe_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/evals/runs": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List recent eval runs */
        get: operations["list_eval_runs_api_v1_evals_runs_get"];
        put?: never;
        /** Kick off a comparison run */
        post: operations["create_eval_run_api_v1_evals_runs_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/evals/runs/{run_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Return the matrix of results for a single run */
        get: operations["get_eval_run_api_v1_evals_runs__run_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/ui/manifest": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Ui Manifest
         * @description Return UI manifests contributed by all loaded backend plugins.
         *
         *     Each loaded plugin may implement
         *     :py:meth:`PluginProtocol.get_ui_manifest`; plugins without the
         *     method are silently skipped. Manifests that fail Pydantic
         *     validation (e.g. missing required fields, empty capabilities) are
         *     logged and dropped rather than failing the whole endpoint, so one
         *     misbehaving plugin can never blank out the UI.
         */
        get: operations["get_ui_manifest_api_v1_ui_manifest_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/login": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Login
         * @description Verify ``email`` + ``password`` for ``tenant_id``, return a JWT.
         */
        post: operations["login_api_v1_auth_login_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/signup": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Signup
         * @description Create a tenant and first admin user without prior authentication.
         */
        post: operations["signup_api_v1_signup_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/admin/me": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Admin Me
         * @description Return the authenticated user's profile.
         */
        get: operations["admin_me_api_v1_admin_me_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/admin/agents": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List tenant-visible agents
         * @description List custom agents for the caller's tenant plus shared profile/plugin agents.
         */
        get: operations["list_agents_api_v1_admin_agents_get"];
        put?: never;
        /**
         * Create a tenant-scoped custom agent
         * @description Create a custom agent in the caller's tenant-scoped registry.
         */
        post: operations["create_agent_api_v1_admin_agents_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/admin/agents/{agent_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get a tenant-visible agent
         * @description Retrieve one custom, profile, or plugin agent visible to the caller.
         */
        get: operations["get_agent_api_v1_admin_agents__agent_id__get"];
        /**
         * Update a tenant-scoped custom agent
         * @description Update an existing custom agent in the caller's tenant.
         */
        put: operations["update_agent_api_v1_admin_agents__agent_id__put"];
        post?: never;
        /**
         * Delete a tenant-scoped custom agent
         * @description Delete a custom agent from the caller's tenant.
         */
        delete: operations["delete_agent_api_v1_admin_agents__agent_id__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/admin/users": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Users
         * @description List users in the *caller's* tenant.
         *
         *     Requires ``USER_MANAGE`` permission. Cross-tenant listing is not
         *     permitted — the caller's ``tenant_id`` from the JWT scopes the
         *     query.
         */
        get: operations["list_users_api_v1_admin_users_get"];
        put?: never;
        /**
         * Create User
         * @description Create a user in the caller's tenant.
         *
         *     Requires ``USER_MANAGE`` permission. The created user inherits
         *     ``user.tenant_id`` from the caller's JWT — the route never lets a
         *     caller create users in another tenant.
         */
        post: operations["create_user_api_v1_admin_users_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/admin/users/{user_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get User
         * @description Get a user by ID — denies cross-tenant access with 404 (not 403).
         */
        get: operations["get_user_api_v1_admin_users__user_id__get"];
        /**
         * Update User
         * @description Update a user. Requires ``USER_MANAGE``. Cross-tenant updates → 404.
         */
        put: operations["update_user_api_v1_admin_users__user_id__put"];
        post?: never;
        /**
         * Delete User
         * @description Soft-delete a user. Requires ``USER_MANAGE``. Cross-tenant → 404.
         */
        delete: operations["delete_user_api_v1_admin_users__user_id__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/admin/roles": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Roles
         * @description List all roles. Requires ``ROLE_MANAGE`` permission.
         */
        get: operations["list_roles_api_v1_admin_roles_get"];
        put?: never;
        /** Create Role */
        post: operations["create_role_api_v1_admin_roles_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/admin/roles/permissions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Permissions
         * @description List all available ``Permission`` enum values.
         */
        get: operations["list_permissions_api_v1_admin_roles_permissions_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/admin/roles/{role_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Role
         * @description Get a single role by id.
         */
        get: operations["get_role_api_v1_admin_roles__role_id__get"];
        /** Update Role */
        put: operations["update_role_api_v1_admin_roles__role_id__put"];
        post?: never;
        /** Delete Role */
        delete: operations["delete_role_api_v1_admin_roles__role_id__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/admin/tenants": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Tenants
         * @description List all tenants. Requires ``TENANT_MANAGE`` permission.
         */
        get: operations["list_tenants_api_v1_admin_tenants_get"];
        put?: never;
        /**
         * Create Tenant
         * @description Create a new tenant. Requires ``TENANT_MANAGE`` permission.
         */
        post: operations["create_tenant_api_v1_admin_tenants_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/admin/tenants/{tenant_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Tenant
         * @description Get a tenant by ID. Requires ``TENANT_MANAGE`` permission.
         */
        get: operations["get_tenant_api_v1_admin_tenants__tenant_id__get"];
        /**
         * Update Tenant
         * @description Update a tenant. Requires ``TENANT_MANAGE`` permission.
         */
        put: operations["update_tenant_api_v1_admin_tenants__tenant_id__put"];
        post?: never;
        /**
         * Delete Tenant
         * @description Soft-delete a tenant by clearing ``is_active``.
         *
         *     Requires ``TENANT_MANAGE`` permission. The on-disk
         *     ``${WORK_DIR}/tenants/${tenant_id}/`` directory is intentionally
         *     *not* removed — operators reactivate tenants by re-creating the
         *     row. Hard delete is a separate operator-only path.
         */
        delete: operations["delete_tenant_api_v1_admin_tenants__tenant_id__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/admin/skills": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Create or replace a tenant-scoped skill
         * @description Persist a SKILL.md under the caller's tenant root and refresh the registry.
         *
         *     The destination is whatever the framework's
         *     ``writable_skill_root_provider`` returns — set by
         *     ``factory_extensions._install_skill_providers`` to a per-tenant
         *     directory under ``${WORK_DIR}/tenants/${tenant_id}/skills/``. With
         *     no provider installed (single-tenant build) the skill lands in
         *     ``${TASKFORCE_WORK_DIR}/skills/`` exactly as the legacy framework
         *     route used to write.
         */
        post: operations["write_skill_api_v1_admin_skills_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
}
export type webhooks = Record<string, never>;
export interface components {
    schemas: {
        /**
         * AcpPeerCreate
         * @description Body for ``POST /acp/peers``.
         */
        AcpPeerCreate: {
            /** Name */
            name: string;
            /** Base Url */
            base_url: string;
            /** Agent */
            agent: string;
            /**
             * Description
             * @default
             */
            description: string;
            /** Auth */
            auth?: {
                [key: string]: unknown;
            };
        };
        /** AcpPeerResponse */
        AcpPeerResponse: {
            /** Name */
            name: string;
            /** Agent */
            agent: string;
            /** Base Url */
            base_url: string;
            /**
             * Description
             * @default
             */
            description: string;
            /**
             * Auth Type
             * @default none
             */
            auth_type: string;
            /** Token Env */
            token_env?: string | null;
        };
        /**
         * AcpPeerUpdate
         * @description Body for ``PUT /acp/peers/{name}`` (name comes from the URL).
         */
        AcpPeerUpdate: {
            /** Base Url */
            base_url: string;
            /** Agent */
            agent: string;
            /**
             * Description
             * @default
             */
            description: string;
            /** Auth */
            auth?: {
                [key: string]: unknown;
            };
        };
        /** AcpStatusResponse */
        AcpStatusResponse: {
            /** Configured Peers */
            configured_peers: number;
            /** Peers */
            peers: components["schemas"]["AcpPeerResponse"][];
        };
        /** AcpTestResult */
        AcpTestResult: {
            /** Ok */
            ok: boolean;
            /** Status Code */
            status_code?: number | null;
            /**
             * Latency Ms
             * @default 0
             */
            latency_ms: number;
            /** Agent */
            agent?: string | null;
            /** Base Url */
            base_url?: string | null;
            /** Error */
            error?: string | null;
        };
        /** ActiveRunResponse */
        ActiveRunResponse: {
            /** Session Id */
            session_id: string;
            /** Started At */
            started_at: string;
            /** Profile */
            profile?: string | null;
            /** Agent Id */
            agent_id?: string | null;
            /** Conversation Id */
            conversation_id?: string | null;
            /**
             * Mission Preview
             * @default
             */
            mission_preview: string;
            /**
             * Prompt Tokens
             * @default 0
             */
            prompt_tokens: number;
            /**
             * Completion Tokens
             * @default 0
             */
            completion_tokens: number;
            /**
             * Total Tokens
             * @default 0
             */
            total_tokens: number;
            /**
             * Cost Usd
             * @default 0
             */
            cost_usd: number;
            /**
             * Last Event
             * @default
             */
            last_event: string;
            /** Last Event At */
            last_event_at: string;
        };
        /** ActiveRunsResponse */
        ActiveRunsResponse: {
            /** Runs */
            runs: components["schemas"]["ActiveRunResponse"][];
        };
        /** AdminMeResponse */
        AdminMeResponse: {
            /** Id */
            id: string;
            /** Tenant Id */
            tenant_id: string;
            /** Email */
            email?: string | null;
            /** Roles */
            roles?: string[];
            /** Permissions */
            permissions?: string[];
        };
        /**
         * AgentDeploymentListResponse
         * @description Deployment history response.
         */
        AgentDeploymentListResponse: {
            /** Deployments */
            deployments: components["schemas"]["AgentDeploymentResponse"][];
        };
        /**
         * AgentDeploymentResponse
         * @description Single deployment record returned to the management UI.
         */
        AgentDeploymentResponse: {
            /** Agent Id */
            agent_id: string;
            /** Version */
            version: string;
            status: components["schemas"]["AgentDeploymentStatus"];
            environment: components["schemas"]["DeploymentEnvironment"];
            /** Deployed At */
            deployed_at?: string | null;
            /** Deployed By */
            deployed_by?: string | null;
            /** Message */
            message?: string | null;
            /** Rollback From */
            rollback_from?: string | null;
            /** Error */
            error?: string | null;
            /** Config Snapshot */
            config_snapshot?: {
                [key: string]: unknown;
            };
        };
        /**
         * AgentDeploymentStatus
         * @description Supported deployment lifecycle states.
         * @enum {string}
         */
        AgentDeploymentStatus: "pending" | "validating" | "deployed" | "failed" | "rolled_back";
        /**
         * AgentListResponse
         * @description Response schema for listing all agents.
         */
        AgentListResponse: {
            /** Agents */
            agents: (components["schemas"]["CustomAgentResponse"] | components["schemas"]["ProfileAgentResponse"] | components["schemas"]["PluginAgentResponse"])[];
        };
        /** AgentTemplateListResponse */
        AgentTemplateListResponse: {
            /** Templates */
            templates: components["schemas"]["AgentTemplateResponse"][];
        };
        /**
         * AgentTemplateResponse
         * @description One curated starting point for the wizard.
         */
        AgentTemplateResponse: {
            /** Id */
            id: string;
            /** Name */
            name: string;
            /** Description */
            description: string;
            /** Emoji */
            emoji: string;
            /** Persona Hint */
            persona_hint: string;
            /** Recommended Tools */
            recommended_tools: string[];
            /** Recommended Skills */
            recommended_skills: string[];
            /** System Prompt Template */
            system_prompt_template: string;
            /** Example Prompts */
            example_prompts: string[];
            /** Tone Default */
            tone_default: string;
            /** Language Default */
            language_default: string;
        };
        /** AgentUsageEntry */
        AgentUsageEntry: {
            /** Agent */
            agent: string;
            /** Prompt Tokens */
            prompt_tokens: number;
            /** Completion Tokens */
            completion_tokens: number;
            /** Total Tokens */
            total_tokens: number;
            /** Cost Usd */
            cost_usd: number;
        };
        /**
         * AppendMessageRequest
         * @description Message to send to the agent within a conversation.
         */
        AppendMessageRequest: {
            /**
             * Message
             * @description User message content.
             */
            message: string;
            /**
             * Profile
             * @description Agent profile. When omitted, the server falls back to the same profile the unified CLI would pick (``butler`` if installed, otherwise ``default``).
             */
            profile?: string | null;
            /**
             * Agent Id
             * @description Registered custom-agent id (from the agent catalog / deployments). When set, the agent is loaded via the agent registry and ``profile`` is treated as the base profile fallback.
             */
            agent_id?: string | null;
            /**
             * Attachments
             * @description File ids of previously uploaded attachments (POST /api/v1/files).
             */
            attachments?: components["schemas"]["AttachmentRef"][];
        };
        /**
         * AppendMessageResponse
         * @description Response from the agent after processing a message.
         */
        AppendMessageResponse: {
            /** Conversation Id */
            conversation_id: string;
            /** Reply */
            reply: string;
            /** Status */
            status: string;
            /** Message Count */
            message_count: number;
        };
        /**
         * ArchiveRequest
         * @description Optional summary when archiving a conversation.
         */
        ArchiveRequest: {
            /**
             * Summary
             * @description Optional summary.
             */
            summary?: string | null;
        };
        /**
         * AttachmentRef
         * @description Reference to a previously uploaded file (see /api/v1/files).
         */
        AttachmentRef: {
            /** File Id */
            file_id: string;
        };
        /** Body_upload_file_api_v1_files_post */
        Body_upload_file_api_v1_files_post: {
            /**
             * File
             * Format: binary
             */
            file: string;
        };
        /**
         * BroadcastRequestSchema
         * @description Request to broadcast a message to all recipients on a channel.
         */
        BroadcastRequestSchema: {
            /**
             * Channel
             * @description Target channel.
             */
            channel: string;
            /**
             * Message
             * @description Message text.
             */
            message: string;
            /**
             * Metadata
             * @description Optional formatting.
             */
            metadata?: {
                [key: string]: unknown;
            } | null;
        };
        /**
         * BroadcastResponseSchema
         * @description Response from broadcast.
         */
        BroadcastResponseSchema: {
            /** Total */
            total: number;
            /** Sent */
            sent: number;
            /** Failed */
            failed: number;
            /** Results */
            results: components["schemas"]["NotificationResponseSchema"][];
        };
        /**
         * ChannelsResponseSchema
         * @description List of configured channels.
         */
        ChannelsResponseSchema: {
            /** Channels */
            channels: string[];
        };
        /**
         * ComposePromptRequest
         * @description Inputs from wizard step 4.
         *
         *     Free-text fields are size-capped at the schema layer so the deterministic
         *     compose path stays bounded and ``use_ai=true`` cannot trigger a runaway
         *     LLM bill.
         */
        ComposePromptRequest: {
            /**
             * Template Id
             * @description Template id (the user's starting point) or null for a blank agent.
             */
            template_id?: string | null;
            /**
             * Description
             * @description What the user said the agent should do (free text).
             * @default
             */
            description: string;
            /**
             * Tone
             * @description professionell | locker | formell
             * @default professionell
             * @enum {string}
             */
            tone: "professionell" | "locker" | "formell";
            /**
             * Language
             * @description Output language for the agent.
             * @default Deutsch
             */
            language: string;
            /**
             * Rules
             * @description Additional rules the user typed in (one per line).
             * @default
             */
            rules: string;
            /**
             * Use Ai
             * @description If true, run an LLM call to refine the prompt. Otherwise compose deterministically from template + inputs.
             * @default false
             */
            use_ai: boolean;
        };
        /** ComposePromptResponse */
        ComposePromptResponse: {
            /** System Prompt */
            system_prompt: string;
            /** Used Ai */
            used_ai: boolean;
            /**
             * Ai Attempted
             * @default false
             */
            ai_attempted: boolean;
            /** Ai Error */
            ai_error?: string | null;
        };
        /**
         * ConversationInfoResponse
         * @description Active conversation metadata.
         */
        ConversationInfoResponse: {
            /** Conversation Id */
            conversation_id: string;
            /** Channel */
            channel: string;
            /**
             * Started At
             * Format: date-time
             */
            started_at: string;
            /**
             * Last Activity
             * Format: date-time
             */
            last_activity: string;
            /** Message Count */
            message_count: number;
            /** Topic */
            topic?: string | null;
        };
        /**
         * ConversationSummaryResponse
         * @description Archived conversation summary.
         */
        ConversationSummaryResponse: {
            /** Conversation Id */
            conversation_id: string;
            /** Topic */
            topic: string;
            /** Summary */
            summary: string;
            /**
             * Started At
             * Format: date-time
             */
            started_at: string;
            /**
             * Archived At
             * Format: date-time
             */
            archived_at: string;
            /** Message Count */
            message_count: number;
        };
        /** ConversationUsageCall */
        ConversationUsageCall: {
            /** Model */
            model: string;
            /** Prompt Tokens */
            prompt_tokens: number;
            /** Completion Tokens */
            completion_tokens: number;
            /** Cost Usd */
            cost_usd: number;
            /** Ts */
            ts: string;
        };
        /** ConversationUsageResponse */
        ConversationUsageResponse: {
            /** Conversation Id */
            conversation_id: string;
            /** Total Prompt */
            total_prompt: number;
            /** Total Completion */
            total_completion: number;
            /** Total Cost Usd */
            total_cost_usd: number;
            /** Calls */
            calls: components["schemas"]["ConversationUsageCall"][];
        };
        /** CostSummaryResponse */
        CostSummaryResponse: {
            /** Today Usd */
            today_usd: number;
            /** Week Usd */
            week_usd: number;
            /** Month Usd */
            month_usd: number;
            /** Pricing As Of */
            pricing_as_of?: string | null;
            /** By Agent */
            by_agent: components["schemas"]["AgentUsageEntry"][];
            /** By Model */
            by_model: components["schemas"]["ModelUsageEntry"][];
        };
        /**
         * CreateConversationRequest
         * @description Request to start a new conversation.
         */
        CreateConversationRequest: {
            /**
             * Channel
             * @description Channel identifier.
             * @default rest
             */
            channel: string;
            /**
             * Sender Id
             * @description Sender identifier.
             */
            sender_id?: string | null;
        };
        /**
         * CreateWaitCheckpointRequest
         * @description Payload for creating a waiting workflow checkpoint.
         */
        CreateWaitCheckpointRequest: {
            /** Session Id */
            session_id: string;
            /** Workflow Name */
            workflow_name: string;
            /** Node Id */
            node_id: string;
            /** Blocking Reason */
            blocking_reason: string;
            /** Required Inputs */
            required_inputs?: {
                [key: string]: unknown;
            };
            /** State */
            state?: {
                [key: string]: unknown;
            };
            /** Question */
            question?: string | null;
            /** Run Id */
            run_id?: string | null;
        };
        /**
         * CustomAgentCreate
         * @description Request schema for creating a custom agent.
         */
        CustomAgentCreate: {
            /**
             * Agent Id
             * @description Unique identifier (lowercase alphanumeric, hyphens, underscores)
             */
            agent_id: string;
            /**
             * Name
             * @description Human-readable agent name
             */
            name: string;
            /**
             * Description
             * @description Agent purpose/capabilities
             */
            description: string;
            /**
             * System Prompt
             * @description LLM system prompt
             */
            system_prompt: string;
            /**
             * Tool Allowlist
             * @description List of allowed tool names
             */
            tool_allowlist?: string[];
            /**
             * Mcp Servers
             * @description MCP server configurations
             */
            mcp_servers?: {
                [key: string]: unknown;
            }[];
            /**
             * Mcp Tool Allowlist
             * @description List of allowed MCP tool names
             */
            mcp_tool_allowlist?: string[];
        };
        /**
         * CustomAgentResponse
         * @description Response schema for custom agent (with timestamps).
         *
         *     Deployment status is *not* included here — query
         *     ``GET /api/v1/agents/{agent_id}/active`` for the active deployment
         *     or ``GET /api/v1/agents/{agent_id}/deployments`` for full history.
         *     Keeping the agent definition and the deployment lifecycle as
         *     separate resources mirrors the file layout
         *     (``configs/custom/`` vs ``deployments/``) and keeps both endpoints
         *     independently cacheable.
         */
        CustomAgentResponse: {
            /**
             * Source
             * @default custom
             * @constant
             */
            source: "custom";
            /** Agent Id */
            agent_id: string;
            /** Name */
            name: string;
            /** Description */
            description: string;
            /** System Prompt */
            system_prompt: string;
            /** Tool Allowlist */
            tool_allowlist: string[];
            /** Mcp Servers */
            mcp_servers: {
                [key: string]: unknown;
            }[];
            /** Mcp Tool Allowlist */
            mcp_tool_allowlist: string[];
            /** Created At */
            created_at: string;
            /** Updated At */
            updated_at: string;
        };
        /**
         * CustomAgentUpdate
         * @description Request schema for updating a custom agent.
         */
        CustomAgentUpdate: {
            /**
             * Name
             * @description Human-readable agent name
             */
            name: string;
            /**
             * Description
             * @description Agent purpose/capabilities
             */
            description: string;
            /**
             * System Prompt
             * @description LLM system prompt
             */
            system_prompt: string;
            /**
             * Tool Allowlist
             * @description List of allowed tool names
             */
            tool_allowlist?: string[];
            /**
             * Mcp Servers
             * @description MCP server configurations
             */
            mcp_servers?: {
                [key: string]: unknown;
            }[];
            /**
             * Mcp Tool Allowlist
             * @description List of allowed MCP tool names
             */
            mcp_tool_allowlist?: string[];
        };
        /**
         * DeployRequest
         * @description Body for ``POST /agents/{agent_id}/deploy``.
         *
         *     All fields are optional. Defaults match the most common case
         *     (deploy the current agent definition to ``local`` with no message).
         */
        DeployRequest: {
            /** @default local */
            environment: components["schemas"]["DeploymentEnvironment"];
            /** Deployed By */
            deployed_by?: string | null;
            /** Message */
            message?: string | null;
        };
        /**
         * DeploymentEnvironment
         * @description Supported deployment target environments.
         * @enum {string}
         */
        DeploymentEnvironment: "local" | "staging" | "prod";
        /**
         * ErrorResponse
         * @description Standard error response schema.
         */
        ErrorResponse: {
            /** Code */
            code: string;
            /** Message */
            message: string;
            /** Details */
            details?: {
                [key: string]: unknown;
            } | null;
            /** Detail */
            detail?: string | null;
        };
        /** EvalRunCreated */
        EvalRunCreated: {
            /** Run Id */
            run_id: string;
            /** Cell Count */
            cell_count: number;
        };
        /** EvalRunRequest */
        EvalRunRequest: {
            /** Missions */
            missions: string[];
            /** Profiles */
            profiles: string[];
            /**
             * Parallelism
             * @default 2
             */
            parallelism: number;
            /**
             * Cell Timeout S
             * @description Per-cell wall-clock cap in seconds.
             * @default 120
             */
            cell_timeout_s: number;
        };
        /**
         * ExecuteMissionRequest
         * @description Request body for mission execution.
         *
         *     Used by both `/execute` and `/execute/stream` endpoints.
         *
         *     Attributes:
         *         mission: The task description for the agent to execute.
         *         session_id: Optional session identifier. If provided, agent
         *             attempts to resume existing session. If omitted, new UUID.
         *         conversation_history: Optional prior conversation for context.
         *             Useful for chat integrations.
         *         user_id: User identifier for RAG security filtering (optional).
         *         org_id: Organization identifier for RAG security filtering.
         *         scope: Access scope for RAG security filtering (optional).
         *         profile: Agent profile to use (default: "butler").
         *         planning_strategy: Optional Agent planning strategy override.
         *         planning_strategy_params: Optional parameters for planning strategy.
         *
         *     Example::
         *
         *         {
         *             "mission": "Search for recent news about AI",
         *             "conversation_history": [
         *                 {"role": "user", "content": "I'm interested in AI"},
         *                 {"role": "assistant", "content": "What to know?"}
         *             ]
         *         }
         */
        ExecuteMissionRequest: {
            /**
             * Mission
             * @description The task description for the agent to execute.
             * @example Search for recent news about AI and summarize findings
             */
            mission: string;
            /**
             * Session Id
             * @deprecated
             * @description Deprecated: Use conversation_id instead (ADR-016). Session ID to resume. Auto-generated if omitted.
             * @example 550e8400-e29b-41d4-a716-446655440000
             */
            session_id?: string | null;
            /**
             * Conversation Id
             * @description Conversation ID for persistent agent mode (ADR-016). When provided, conversation history is managed automatically via the ConversationManager. Mutually exclusive with conversation_history.
             * @example telegram:user-1:abc123
             */
            conversation_id?: string | null;
            /**
             * Conversation History
             * @description Optional conversation history for chat context.
             * @example [
             *       {
             *         "content": "Previous user message",
             *         "role": "user"
             *       },
             *       {
             *         "content": "Previous assistant response",
             *         "role": "assistant"
             *       }
             *     ]
             */
            conversation_history?: {
                [key: string]: unknown;
            }[] | null;
            /**
             * User Id
             * @description User ID for RAG security filtering.
             */
            user_id?: string | null;
            /**
             * Org Id
             * @description Organization ID for RAG security filtering.
             */
            org_id?: string | null;
            /**
             * Scope
             * @description Access scope for RAG security filtering.
             */
            scope?: string | null;
            /**
             * Profile
             * @description Agent profile to use (e.g., butler, coding_agent, rag_agent).
             * @default butler
             */
            profile: string;
            /**
             * Agent Id
             * @description Agent ID to use. Can be: - Custom agent ID (loads from configs/custom/{agent_id}.yaml), - Plugin agent ID (automatically loads plugin from examples/ or plugins/). Agent definitions supply their own configuration; the API uses the default infrastructure profile internally.
             * @example research_agent
             * @example accounting_agent
             */
            agent_id?: string | null;
            /**
             * Planning Strategy
             * @description Agent planning strategy override (native_react, plan_and_execute, plan_and_react, or spar).
             */
            planning_strategy?: string | null;
            /**
             * Planning Strategy Params
             * @description Optional parameters for the selected planning strategy.
             */
            planning_strategy_params?: {
                [key: string]: unknown;
            } | null;
        };
        /**
         * ExecuteMissionResponse
         * @description Response from synchronous mission execution.
         *
         *     Attributes:
         *         session_id: Unique identifier for this execution session.
         *         conversation_id: Conversation ID when using persistent agent mode.
         *         status: Execution status. Possible values:
         *             - "completed": Mission finished successfully
         *             - "failed": Mission execution failed
         *             - "paused": Waiting for user input (ask_user action)
         *             - "pending": Execution incomplete (timeout/max steps)
         *         message: Human-readable summary of the execution result.
         */
        ExecuteMissionResponse: {
            /**
             * Session Id
             * @description Unique session identifier.
             */
            session_id: string;
            /**
             * Conversation Id
             * @description Conversation ID (persistent agent mode, ADR-016).
             */
            conversation_id?: string | null;
            /**
             * Status
             * @description Execution status: completed, failed, paused, or pending.
             */
            status: string;
            /**
             * Message
             * @description Human-readable execution result summary.
             */
            message: string;
        };
        /** FileMetadataResponse */
        FileMetadataResponse: {
            /**
             * File Id
             * @description 32-character hex identifier
             */
            file_id: string;
            /** Name */
            name: string;
            /** Mime */
            mime: string;
            /**
             * Size
             * @description Bytes
             */
            size: number;
            /** Sha256 */
            sha256: string;
            /** Created At */
            created_at: string;
        };
        /**
         * ForkConversationRequest
         * @description Body for ``POST /conversations/{id}/fork``.
         */
        ForkConversationRequest: {
            /**
             * Up To Index
             * @description Number of messages to copy from the source. ``None`` means copy the full transcript.
             */
            up_to_index?: number | null;
            /**
             * Channel
             * @default rest
             */
            channel: string;
        };
        /** ForkConversationResponse */
        ForkConversationResponse: {
            /** Conversation Id */
            conversation_id: string;
            /** Source Id */
            source_id: string;
            /** Messages Copied */
            messages_copied: number;
        };
        /**
         * GatewayMessageRequest
         * @description Inbound message payload for the gateway.
         */
        GatewayMessageRequest: {
            /**
             * Conversation Id
             * @description Channel-specific conversation identifier.
             * @example 123456789
             * @example 19:abc123@thread.v2
             */
            conversation_id: string;
            /**
             * Message
             * @description User message content.
             * @example Wie ist der aktuelle Status?
             */
            message: string;
            /**
             * Sender Id
             * @description Sender identifier for recipient auto-registration.
             */
            sender_id?: string | null;
            /**
             * Session Id
             * @description Optional session ID override.
             */
            session_id?: string | null;
            /**
             * Profile
             * @description Agent profile to use.
             * @default butler
             */
            profile: string;
            /**
             * User Id
             * @description User ID for RAG security filtering.
             */
            user_id?: string | null;
            /**
             * Org Id
             * @description Organization ID for RAG security filtering.
             */
            org_id?: string | null;
            /**
             * Scope
             * @description Access scope for RAG security filtering.
             */
            scope?: string | null;
            /**
             * Agent Id
             * @description Optional agent ID override.
             */
            agent_id?: string | null;
            /**
             * Planning Strategy
             * @description Optional planning strategy override.
             */
            planning_strategy?: string | null;
            /**
             * Planning Strategy Params
             * @description Optional planning strategy parameters.
             */
            planning_strategy_params?: {
                [key: string]: unknown;
            } | null;
            /**
             * Plugin Path
             * @description Optional plugin path.
             */
            plugin_path?: string | null;
            /**
             * Metadata
             * @description Optional channel-specific metadata.
             */
            metadata?: {
                [key: string]: unknown;
            } | null;
        };
        /**
         * GatewayMessageResponse
         * @description Response from gateway message handling.
         */
        GatewayMessageResponse: {
            /**
             * Session Id
             * @description Resolved session identifier.
             */
            session_id: string;
            /**
             * Status
             * @description Execution status.
             */
            status: string;
            /**
             * Reply
             * @description Agent reply message.
             */
            reply: string;
            /**
             * History Length
             * @description Total history entries for this conversation.
             */
            history_length: number;
            /**
             * Conversation Id
             * @description Persistent conversation ID (ADR-016). Null when ConversationManager is not configured.
             */
            conversation_id?: string | null;
        };
        /** HTTPValidationError */
        HTTPValidationError: {
            /** Detail */
            detail?: components["schemas"]["ValidationError"][];
        };
        /**
         * HealthResponse
         * @description Health check response.
         */
        HealthResponse: {
            /** Status */
            status: string;
            /** Version */
            version: string;
            /** Checks */
            checks?: {
                [key: string]: string;
            } | null;
            /** Default Profile */
            default_profile?: string | null;
        };
        /**
         * InterruptResponse
         * @description Response from POST /execute/{session_id}/cancel.
         */
        InterruptResponse: {
            /**
             * Session Id
             * @description Session that was signalled.
             */
            session_id: string;
            /**
             * Status
             * @description Request status: ``interrupt_requested`` when the active agent was signalled to pause at the next ReAct loop boundary.
             */
            status: string;
        };
        /** LLMModelEntry */
        LLMModelEntry: {
            /**
             * Alias
             * @description Short alias used in profile YAMLs
             */
            alias: string;
            /**
             * Model Id
             * @description LiteLLM model string (provider/model)
             */
            model_id: string;
            /**
             * Provider
             * @description Inferred provider prefix
             */
            provider: string;
        };
        /** LLMModelsResponse */
        LLMModelsResponse: {
            /** Default Model */
            default_model: string;
            /** Models */
            models: components["schemas"]["LLMModelEntry"][];
        };
        /**
         * LoginRequest
         * @description Request body for ``POST /auth/login``.
         *
         *     ``tenant_id`` is required because the same email can belong to
         *     different tenants — the schema's ``UNIQUE (tenant_id, email)``
         *     enforces uniqueness *per tenant*, not globally.
         */
        LoginRequest: {
            /** Tenant Id */
            tenant_id: string;
            /** Email */
            email: string;
            /** Password */
            password: string;
        };
        /** LoginResponse */
        LoginResponse: {
            /** Access Token */
            access_token: string;
            /**
             * Token Type
             * @default bearer
             */
            token_type: string;
        };
        /** McpProbeRequest */
        McpProbeRequest: {
            /**
             * Type
             * @enum {string}
             */
            type: "stdio" | "sse";
            /**
             * Command
             * @description stdio: command to run
             */
            command?: string | null;
            /**
             * Args
             * @description stdio: args
             */
            args?: string[];
            /**
             * Env
             * @description stdio: env vars
             */
            env?: {
                [key: string]: string;
            };
            /**
             * Url
             * @description sse: server URL
             */
            url?: string | null;
        };
        /** McpProbeResponse */
        McpProbeResponse: {
            /** Ok */
            ok: boolean;
            /** Elapsed Ms */
            elapsed_ms: number;
            /** Tools */
            tools?: components["schemas"]["McpToolEntry"][];
            /** Error */
            error?: string | null;
        };
        /** McpToolEntry */
        McpToolEntry: {
            /** Name */
            name: string;
            /**
             * Description
             * @default
             */
            description: string;
            /** Input Schema */
            input_schema?: {
                [key: string]: unknown;
            } | null;
        };
        /**
         * MessageResponse
         * @description A single message in the conversation.
         */
        MessageResponse: {
            /** Role */
            role: string;
            /** Content */
            content: string;
            /** Attachments */
            attachments?: {
                [key: string]: unknown;
            }[];
        };
        /** ModelUsageEntry */
        ModelUsageEntry: {
            /** Model */
            model: string;
            /** Prompt Tokens */
            prompt_tokens: number;
            /** Completion Tokens */
            completion_tokens: number;
            /** Total Tokens */
            total_tokens: number;
            /** Cost Usd */
            cost_usd: number;
        };
        /**
         * NotificationRequestSchema
         * @description Request to send a proactive push notification.
         */
        NotificationRequestSchema: {
            /**
             * Channel
             * @description Target channel (e.g. 'telegram', 'teams').
             */
            channel: string;
            /**
             * Recipient Id
             * @description Application-level user ID.
             */
            recipient_id: string;
            /**
             * Message
             * @description Notification message text.
             */
            message: string;
            /**
             * Metadata
             * @description Optional channel-specific formatting.
             */
            metadata?: {
                [key: string]: unknown;
            } | null;
        };
        /**
         * NotificationResponseSchema
         * @description Response from notification dispatch.
         */
        NotificationResponseSchema: {
            /** Success */
            success: boolean;
            /** Channel */
            channel: string;
            /** Recipient Id */
            recipient_id: string;
            /** Error */
            error?: string | null;
        };
        /** PermissionListResponse */
        PermissionListResponse: {
            /** Permissions */
            permissions: components["schemas"]["PermissionResponse"][];
            /** Total */
            total: number;
        };
        /** PermissionResponse */
        PermissionResponse: {
            /** Name */
            name: string;
            /** Value */
            value: string;
            /** Description */
            description: string;
        };
        /** PlanningStrategiesResponse */
        PlanningStrategiesResponse: {
            /** Strategies */
            strategies: components["schemas"]["PlanningStrategy"][];
        };
        /** PlanningStrategy */
        PlanningStrategy: {
            /** Id */
            id: string;
            /** Label */
            label: string;
            /** Description */
            description: string;
        };
        /**
         * PluginAgentResponse
         * @description Response schema for plugin agent (from external plugin dir).
         */
        PluginAgentResponse: {
            /**
             * Source
             * @default plugin
             * @constant
             */
            source: "plugin";
            /** Agent Id */
            agent_id: string;
            /** Name */
            name: string;
            /** Description */
            description: string;
            /** Plugin Path */
            plugin_path: string;
            /** Tool Classes */
            tool_classes: string[];
            /** Specialist */
            specialist?: string | null;
            /** Mcp Servers */
            mcp_servers: {
                [key: string]: unknown;
            }[];
        };
        /**
         * ProfileAgentResponse
         * @description Response schema for profile agent (from YAML config).
         */
        ProfileAgentResponse: {
            /**
             * Source
             * @default profile
             * @constant
             */
            source: "profile";
            /** Profile */
            profile: string;
            /** Specialist */
            specialist?: string | null;
            /** Tools */
            tools: (string | {
                [key: string]: unknown;
            })[];
            /** Mcp Servers */
            mcp_servers: {
                [key: string]: unknown;
            }[];
            /** Llm */
            llm: {
                [key: string]: unknown;
            };
            /** Persistence */
            persistence: {
                [key: string]: unknown;
            };
        };
        /**
         * ProfileClonePayload
         * @description Body for ``POST /profiles/{source}/clone``.
         */
        ProfileClonePayload: {
            /**
             * Target Name
             * @description Name of the new user-owned profile
             */
            target_name: string;
        };
        /**
         * ProfileCreatePayload
         * @description Create body — adds the profile name.
         */
        ProfileCreatePayload: {
            /**
             * Config
             * @description Structured configuration that the backend will write as YAML
             */
            config: {
                [key: string]: unknown;
            };
            /**
             * Name
             * @description Profile identifier (filename minus extension)
             */
            name: string;
        };
        /**
         * ProfileDefinitionPayload
         * @description Body for create/update operations.
         *
         *     Accepts either a structured ``config`` dict (preferred — gets
         *     serialised by the backend with comment-preserving YAML) or an
         *     explicit ``yaml_text`` string for power-users.
         */
        ProfileDefinitionPayload: {
            /**
             * Config
             * @description Structured configuration that the backend will write as YAML
             */
            config: {
                [key: string]: unknown;
            };
        };
        /**
         * ProfileDetail
         * @description Full configuration plus raw text for a single profile.
         */
        ProfileDetail: {
            /** Name */
            name: string;
            /** Path */
            path: string;
            /**
             * Format
             * @enum {string}
             */
            format: "agent_md" | "yaml";
            /**
             * Description
             * @default
             */
            description: string;
            /** Specialist */
            specialist?: string | null;
            /**
             * Is Writable
             * @description True if the API can update or delete this file
             * @default false
             */
            is_writable: boolean;
            /**
             * Config
             * @description Parsed and merged configuration dict
             */
            config: {
                [key: string]: unknown;
            };
            /**
             * Yaml Text
             * @description Original on-disk text (frontmatter + body for .agent.md)
             */
            yaml_text: string;
        };
        /**
         * ProfileListResponse
         * @description Wrapper around the list of profile summaries.
         */
        ProfileListResponse: {
            /** Profiles */
            profiles: components["schemas"]["ProfileSummary"][];
        };
        /**
         * ProfileSummary
         * @description Lightweight metadata for a single profile (used in list views).
         */
        ProfileSummary: {
            /**
             * Name
             * @description Profile identifier (filename minus extension)
             */
            name: string;
            /**
             * Path
             * @description Absolute path to the source file
             */
            path: string;
            /**
             * Format
             * @description Source file format
             * @enum {string}
             */
            format: "agent_md" | "yaml";
            /**
             * Description
             * @description Best-effort description for previews
             * @default
             */
            description: string;
            /**
             * Specialist
             * @description Value of the top-level ``specialist`` field
             */
            specialist?: string | null;
            /**
             * Name Label
             * @description Human-friendly label declared in the file
             */
            name_label?: string | null;
            /**
             * Is Custom
             * @description True if the profile lives under a ``custom/`` directory
             * @default false
             */
            is_custom: boolean;
        };
        /**
         * ResumeAndContinueRequest
         * @description Payload for resuming and immediately continuing workflow execution.
         */
        ResumeAndContinueRequest: {
            /**
             * Input Type
             * @default human_reply
             */
            input_type: string;
            /** Payload */
            payload?: {
                [key: string]: unknown;
            };
            /** Sender Metadata */
            sender_metadata?: {
                [key: string]: unknown;
            };
            /**
             * Profile
             * @default butler
             */
            profile: string;
        };
        /**
         * ResumeWorkflowRequest
         * @description Payload for resuming a paused workflow.
         */
        ResumeWorkflowRequest: {
            /**
             * Input Type
             * @default human_reply
             */
            input_type: string;
            /** Payload */
            payload?: {
                [key: string]: unknown;
            };
            /** Sender Metadata */
            sender_metadata?: {
                [key: string]: unknown;
            };
        };
        /** RoleListResponse */
        RoleListResponse: {
            /** Roles */
            roles: components["schemas"]["RoleResponse"][];
            /** Total */
            total: number;
        };
        /** RoleResponse */
        RoleResponse: {
            /** Role Id */
            role_id: string;
            /** Name */
            name: string;
            /** Description */
            description: string;
            /** Permissions */
            permissions: string[];
            /** Is System */
            is_system: boolean;
        };
        /**
         * RollbackRequest
         * @description Body for ``POST /agents/{agent_id}/rollback``.
         */
        RollbackRequest: {
            /** To Version */
            to_version: string;
            /** @default local */
            environment: components["schemas"]["DeploymentEnvironment"];
            /** Deployed By */
            deployed_by?: string | null;
            /** Message */
            message?: string | null;
        };
        /**
         * RunWorkflowDefinitionRequest
         * @description Payload for running a stored workflow definition.
         */
        RunWorkflowDefinitionRequest: {
            /** Session Id */
            session_id?: string | null;
        };
        /**
         * SignupRequest
         * @description Payload for creating a fresh tenant and first admin user.
         */
        SignupRequest: {
            /** Tenant Name */
            tenant_name: string;
            /**
             * Tenant Id
             * @description Optional tenant slug. Derived from tenant_name when omitted.
             */
            tenant_id?: string | null;
            /** Admin Email */
            admin_email: string;
            /** Password */
            password: string;
        };
        /**
         * SignupResponse
         * @description Response returned after self-signup creates the tenant admin.
         */
        SignupResponse: {
            /** Tenant Id */
            tenant_id: string;
            /** User Id */
            user_id: string;
            /** Email */
            email: string;
            /** Verification Required */
            verification_required: boolean;
            /** Verification Sent */
            verification_sent: boolean;
        };
        /**
         * SkillDetail
         * @description Skill summary plus the SKILL.md body so the UI can preview it.
         */
        SkillDetail: {
            /** Name */
            name: string;
            /** Description */
            description: string;
            /**
             * Skill Type
             * @enum {string}
             */
            skill_type: "context" | "prompt" | "agent" | "library" | "integration";
            /**
             * Slash Name
             * @description Slash command name for prompt/agent skills (without leading `/`)
             */
            slash_name?: string | null;
            /** File Path */
            file_path?: string | null;
            /** Allowed Tools */
            allowed_tools?: string[];
            /**
             * Body
             * @description Markdown body of the skill file
             * @default
             */
            body: string;
        };
        /** SkillListResponse */
        SkillListResponse: {
            /** Skills */
            skills: components["schemas"]["SkillSummary"][];
        };
        /**
         * SkillSummary
         * @description One entry in the skill catalog.
         */
        SkillSummary: {
            /** Name */
            name: string;
            /** Description */
            description: string;
            /**
             * Skill Type
             * @enum {string}
             */
            skill_type: "context" | "prompt" | "agent" | "library" | "integration";
            /**
             * Slash Name
             * @description Slash command name for prompt/agent skills (without leading `/`)
             */
            slash_name?: string | null;
            /** File Path */
            file_path?: string | null;
            /** Allowed Tools */
            allowed_tools?: string[];
        };
        /**
         * SkillWriteRequest
         * @description Payload for creating or replacing a tenant-scoped skill.
         */
        SkillWriteRequest: {
            /** Name */
            name: string;
            /**
             * Content
             * @description Full SKILL.md content
             */
            content: string;
        };
        /**
         * TenantCreate
         * @description Request model for creating a tenant.
         */
        TenantCreate: {
            /** Tenant Id */
            tenant_id: string;
            /** Name */
            name: string;
        };
        /** TenantListResponse */
        TenantListResponse: {
            /** Tenants */
            tenants: components["schemas"]["TenantResponse"][];
            /** Total */
            total: number;
            /** Limit */
            limit: number;
            /** Offset */
            offset: number;
        };
        /**
         * TenantResponse
         * @description Response model for tenant data.
         */
        TenantResponse: {
            /** Tenant Id */
            tenant_id: string;
            /** Name */
            name: string;
            /** Settings */
            settings?: {
                [key: string]: unknown;
            };
            /** Metadata */
            metadata?: {
                [key: string]: unknown;
            };
            /** Created At */
            created_at?: string | null;
        };
        /**
         * TenantUpdate
         * @description Request model for updating a tenant.
         */
        TenantUpdate: {
            /** Name */
            name?: string | null;
        };
        /** TokenUsageBucket */
        TokenUsageBucket: {
            /**
             * Bucket
             * @description ISO timestamp prefix (day/hour/minute)
             */
            bucket: string;
            /** Prompt Tokens */
            prompt_tokens: number;
            /** Completion Tokens */
            completion_tokens: number;
            /** Total Tokens */
            total_tokens: number;
            /** Cost Usd */
            cost_usd: number;
            /** Call Count */
            call_count: number;
        };
        /** TokenUsageResponse */
        TokenUsageResponse: {
            /** Granularity */
            granularity: string;
            /** Pricing As Of */
            pricing_as_of?: string | null;
            /** Buckets */
            buckets: components["schemas"]["TokenUsageBucket"][];
        };
        /**
         * ToolCatalogResponse
         * @description Response schema for tool catalog endpoint.
         */
        ToolCatalogResponse: {
            /** Tools */
            tools: {
                [key: string]: unknown;
            }[];
        };
        /**
         * UIManifestEntry
         * @description One plugin's contribution to the UI manifest.
         */
        UIManifestEntry: {
            /**
             * Id
             * @description Stable plugin identifier (e.g. 'enterprise')
             */
            id: string;
            /**
             * Capabilities
             * @description Capability flags this plugin reports as active. Must be non-empty.
             */
            capabilities: string[];
            /**
             * Version
             * @description Plugin version for diagnostics
             * @default 0.0.0
             */
            version: string;
            /**
             * Display Name
             * @description Human-readable plugin name
             * @default
             */
            display_name: string;
            /**
             * Npm Package
             * @description Optional npm package name that ships matching React components
             */
            npm_package?: string | null;
            /**
             * Min Ui Version
             * @description Optional semver range for the host UI shell version
             */
            min_ui_version?: string | null;
        };
        /**
         * UIManifestResponse
         * @description Envelope returned by ``GET /api/v1/ui/manifest``.
         *
         *     The response is intentionally minimal: it lists which optional UI
         *     plugins are active so the React shell can decide which sidebar
         *     entries and routes to mount. We deliberately do **not** include
         *     the server version here — the endpoint is unauthenticated and
         *     server-version disclosure is reconnaissance gold for fingerprinting.
         *     Authenticated callers can use ``GET /health`` for that.
         */
        UIManifestResponse: {
            /**
             * Plugins
             * @description UI manifests contributed by loaded backend plugins
             */
            plugins?: components["schemas"]["UIManifestEntry"][];
        };
        /**
         * UserCreate
         * @description Request model for creating a user.
         *
         *     ``password`` is mandatory in iter-2; the bcrypt hash lives in
         *     ``users.password_hash``. ``roles`` are short role ids (``admin``,
         *     ``operator``, ``viewer``, ``agent_designer``, ``auditor``).
         */
        UserCreate: {
            /** Email */
            email: string;
            /** Password */
            password: string;
            /** Roles */
            roles?: string[];
        };
        /** UserListResponse */
        UserListResponse: {
            /** Users */
            users: components["schemas"]["UserResponse"][];
            /** Total */
            total: number;
            /** Limit */
            limit: number;
            /** Offset */
            offset: number;
        };
        /** UserResponse */
        UserResponse: {
            /** User Id */
            user_id: string;
            /** Tenant Id */
            tenant_id: string;
            /** Username */
            username: string;
            /** Email */
            email?: string | null;
            /** Roles */
            roles?: string[];
            /** Permissions */
            permissions?: string[];
            /** Attributes */
            attributes?: {
                [key: string]: unknown;
            };
        };
        /**
         * UserUpdate
         * @description Request model for updating a user.
         */
        UserUpdate: {
            /** Email */
            email?: string | null;
            /** Password */
            password?: string | null;
            /** Roles */
            roles?: string[] | null;
            /** Is Active */
            is_active?: boolean | null;
        };
        /** ValidationError */
        ValidationError: {
            /** Location */
            loc: (string | number)[];
            /** Message */
            msg: string;
            /** Error Type */
            type: string;
        };
        /**
         * WikiPageDetail
         * @description Full wiki page payload.
         */
        WikiPageDetail: {
            /** Name */
            name: string;
            /** Title */
            title: string;
            /** Kind */
            kind: string;
            /** Tags */
            tags: string[];
            /** Updated At */
            updated_at: string;
            /** Body */
            body: string;
            /** Created At */
            created_at: string;
        };
        /**
         * WikiPageSummary
         * @description One-line summary of a wiki page.
         */
        WikiPageSummary: {
            /** Name */
            name: string;
            /** Title */
            title: string;
            /** Kind */
            kind: string;
            /** Tags */
            tags: string[];
            /** Updated At */
            updated_at: string;
        };
        /**
         * WorkflowDefinitionRequest
         * @description API payload for saving a workflow definition.
         */
        WorkflowDefinitionRequest: {
            /** Workflow Id */
            workflow_id: string;
            /** Name */
            name: string;
            /**
             * Description
             * @default
             */
            description: string;
            /**
             * Trigger
             * @default manual
             */
            trigger: string;
            /** Trigger Config */
            trigger_config?: {
                [key: string]: unknown;
            };
            /** Steps */
            steps?: components["schemas"]["WorkflowStepRequest"][];
            /** Metadata */
            metadata?: {
                [key: string]: unknown;
            };
        };
        /**
         * WorkflowStepRequest
         * @description API payload for one workflow step.
         */
        WorkflowStepRequest: {
            /** Step Id */
            step_id: string;
            /** Agent */
            agent: string;
            /** Task */
            task: string;
            /** Depends On */
            depends_on?: string[];
            /** Metadata */
            metadata?: {
                [key: string]: unknown;
            };
            /** Acp Peer */
            acp_peer?: string | null;
        };
        /** _NotImplementedBody */
        _NotImplementedBody: {
            /**
             * Detail
             * @default custom roles are not implemented in iter-2
             */
            detail: string;
        };
    };
    responses: never;
    parameters: never;
    requestBodies: never;
    headers: never;
    pathItems: never;
}
export type $defs = Record<string, never>;
export interface operations {
    execute_mission_api_v1_execute_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ExecuteMissionRequest"];
            };
        };
        responses: {
            /** @description Mission result. */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ExecuteMissionResponse"];
                };
            };
            /** @description Invalid request or config. */
            400: {
                headers: {
                    /** @description Indicates standardized Taskforce error payload. */
                    "X-Taskforce-Error"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Agent or profile not found. */
            404: {
                headers: {
                    /** @description Indicates standardized Taskforce error payload. */
                    "X-Taskforce-Error"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Execution cancelled. */
            409: {
                headers: {
                    /** @description Indicates standardized Taskforce error payload. */
                    "X-Taskforce-Error"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
            /** @description Unexpected server error. */
            500: {
                headers: {
                    /** @description Indicates standardized Taskforce error payload. */
                    "X-Taskforce-Error"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Upstream dependency failed. */
            502: {
                headers: {
                    /** @description Indicates standardized Taskforce error payload. */
                    "X-Taskforce-Error"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
        };
    };
    execute_mission_stream_api_v1_execute_stream_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ExecuteMissionRequest"];
            };
        };
        responses: {
            /** @description Server-Sent Events stream of updates. */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                    "text/event-stream": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    cancel_mission_api_v1_execute__session_id__cancel_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                session_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Interrupt was requested. The running agent will finish the current step, persist its state, and emit an ``interrupted`` event followed by a ``complete`` event with ``status=paused``. */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["InterruptResponse"];
                };
            };
            /** @description No active execution found for this session_id. */
            404: {
                headers: {
                    /** @description Indicates standardized Taskforce error payload. */
                    "X-Taskforce-Error"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_agents_api_v1_agents_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AgentListResponse"];
                };
            };
        };
    };
    create_agent_api_v1_agents_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CustomAgentCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CustomAgentResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_agent_api_v1_agents__agent_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                agent_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CustomAgentResponse"] | components["schemas"]["ProfileAgentResponse"] | components["schemas"]["PluginAgentResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    update_agent_api_v1_agents__agent_id__put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                agent_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CustomAgentUpdate"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CustomAgentResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    delete_agent_api_v1_agents__agent_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                agent_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    deploy_agent_api_v1_agents__agent_id__deploy_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                agent_id: string;
            };
            cookie?: never;
        };
        requestBody?: {
            content: {
                "application/json": components["schemas"]["DeployRequest"] | null;
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AgentDeploymentResponse"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    rollback_agent_api_v1_agents__agent_id__rollback_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                agent_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["RollbackRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AgentDeploymentResponse"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_deployments_api_v1_agents__agent_id__deployments_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                agent_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AgentDeploymentListResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_active_deployment_api_v1_agents__agent_id__active_get: {
        parameters: {
            query?: {
                environment?: components["schemas"]["DeploymentEnvironment"];
            };
            header?: never;
            path: {
                agent_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AgentDeploymentResponse"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_agent_templates_api_v1_agent_templates_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AgentTemplateListResponse"];
                };
            };
        };
    };
    get_agent_template_api_v1_agent_templates__template_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                template_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AgentTemplateResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    compose_prompt_api_v1_agent_templates_compose_prompt_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ComposePromptRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ComposePromptResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_tools_api_v1_tools_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ToolCatalogResponse"];
                };
            };
        };
    };
    handle_message_api_v1_gateway__channel__messages_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                channel: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["GatewayMessageRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GatewayMessageResponse"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    handle_webhook_api_v1_gateway__channel__webhook_post: {
        parameters: {
            query?: {
                /** @description Agent profile to use for this channel's webhook. */
                profile?: string;
                /** @description Optional plugin path for external agent tools. */
                plugin_path?: string | null;
            };
            header?: never;
            path: {
                channel: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GatewayMessageResponse"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    send_notification_api_v1_gateway_notify_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["NotificationRequestSchema"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["NotificationResponseSchema"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    broadcast_api_v1_gateway_broadcast_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["BroadcastRequestSchema"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BroadcastResponseSchema"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_channels_api_v1_gateway_channels_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ChannelsResponseSchema"];
                };
            };
        };
    };
    health_check_health_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HealthResponse"];
                };
            };
        };
    };
    readiness_check_health_ready_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HealthResponse"];
                };
            };
        };
    };
    list_pages_api_v1_memory_list_get: {
        parameters: {
            query?: {
                profile?: string;
                limit?: number;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["WikiPageSummary"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_page_api_v1_memory_page__name__get: {
        parameters: {
            query?: {
                profile?: string;
            };
            header?: never;
            path: {
                name: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["WikiPageDetail"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_active_conversations_api_v1_conversations_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ConversationInfoResponse"][];
                };
            };
        };
    };
    create_conversation_api_v1_conversations_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CreateConversationRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ConversationInfoResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_archived_conversations_api_v1_conversations_archived_get: {
        parameters: {
            query?: {
                limit?: number;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ConversationSummaryResponse"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_messages_api_v1_conversations__conversation_id__messages_get: {
        parameters: {
            query?: {
                limit?: number | null;
            };
            header?: never;
            path: {
                conversation_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MessageResponse"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    append_message_api_v1_conversations__conversation_id__messages_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                conversation_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["AppendMessageRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AppendMessageResponse"];
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    stream_message_api_v1_conversations__conversation_id__messages_stream_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                conversation_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["AppendMessageRequest"];
            };
        };
        responses: {
            /** @description Server-Sent Events stream of agent progress. */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                    "text/event-stream": unknown;
                };
            };
            /** @description Bad Request */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    archive_conversation_api_v1_conversations__conversation_id__archive_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                conversation_id: string;
            };
            cookie?: never;
        };
        requestBody?: {
            content: {
                "application/json": components["schemas"]["ArchiveRequest"] | null;
            };
        };
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    fork_conversation_api_v1_conversations__conversation_id__fork_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                conversation_id: string;
            };
            cookie?: never;
        };
        requestBody?: {
            content: {
                "application/json": components["schemas"]["ForkConversationRequest"] | null;
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ForkConversationResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_workflow_definitions_api_v1_workflows_definitions_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
        };
    };
    save_workflow_definition_api_v1_workflows_definitions_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["WorkflowDefinitionRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_workflow_definition_api_v1_workflows_definitions__workflow_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                workflow_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    delete_workflow_definition_api_v1_workflows_definitions__workflow_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                workflow_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    run_workflow_definition_api_v1_workflows_definitions__workflow_id__run_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                workflow_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["RunWorkflowDefinitionRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    trigger_workflow_webhook_api_v1_workflows_webhooks__trigger_path__post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                trigger_path: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    create_wait_checkpoint_api_v1_workflows_wait_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CreateWaitCheckpointRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_checkpoint_api_v1_workflows__run_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                run_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    resume_workflow_api_v1_workflows__run_id__resume_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                run_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ResumeWorkflowRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    resume_and_continue_workflow_api_v1_workflows__run_id__resume_and_continue_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                run_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ResumeAndContinueRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_peers_api_v1_acp_peers_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AcpPeerResponse"][];
                };
            };
        };
    };
    create_peer_api_v1_acp_peers_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["AcpPeerCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AcpPeerResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    status_endpoint_api_v1_acp_status_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AcpStatusResponse"];
                };
            };
        };
    };
    update_peer_api_v1_acp_peers__name__put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                name: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["AcpPeerUpdate"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AcpPeerResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    delete_peer_api_v1_acp_peers__name__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                name: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    test_peer_api_v1_acp_peers__name__test_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                name: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AcpTestResult"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_profiles_api_v1_profiles_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProfileListResponse"];
                };
            };
        };
    };
    create_profile_api_v1_profiles_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ProfileCreatePayload"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProfileDetail"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_subagent_candidates_api_v1_profiles_available_as_subagent_get: {
        parameters: {
            query?: {
                /** @description Profile name to exclude (typically the agent being edited) */
                exclude?: string | null;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProfileListResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_profile_api_v1_profiles__name__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                name: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProfileDetail"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    update_profile_api_v1_profiles__name__put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                name: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ProfileDefinitionPayload"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProfileDetail"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    delete_profile_api_v1_profiles__name__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                name: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    clone_profile_api_v1_profiles__source__clone_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                source: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ProfileClonePayload"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProfileDetail"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_skills_api_v1_skills_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SkillListResponse"];
                };
            };
        };
    };
    get_skill_api_v1_skills__name__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                name: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SkillDetail"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_llm_models_api_v1_llm_models_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["LLMModelsResponse"];
                };
            };
        };
    };
    list_planning_strategies_api_v1_planning_strategies_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PlanningStrategiesResponse"];
                };
            };
        };
    };
    upload_file_api_v1_files_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "multipart/form-data": components["schemas"]["Body_upload_file_api_v1_files_post"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["FileMetadataResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_file_meta_api_v1_files__file_id__meta_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                file_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["FileMetadataResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    download_file_api_v1_files__file_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                file_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Binary file content (streamed). */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                    "application/octet-stream": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    delete_file_api_v1_files__file_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                file_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    token_usage_api_v1_analytics_token_usage_get: {
        parameters: {
            query?: {
                granularity?: string;
                from?: string | null;
                to?: string | null;
                agent?: string | null;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TokenUsageResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    cost_summary_api_v1_analytics_cost_summary_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CostSummaryResponse"];
                };
            };
        };
    };
    conversation_usage_api_v1_analytics_conversations__conversation_id__usage_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                conversation_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ConversationUsageResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_active_runs_api_v1_runs_active_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ActiveRunsResponse"];
                };
            };
        };
    };
    list_recent_runs_api_v1_runs_recent_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
        };
    };
    get_run_trace_api_v1_runs__session_id__trace_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                session_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    stream_active_runs_api_v1_runs_active_stream_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                    "text/event-stream": unknown;
                };
            };
        };
    };
    probe_mcp_api_v1_mcp_probe_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["McpProbeRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["McpProbeResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_eval_runs_api_v1_evals_runs_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
        };
    };
    create_eval_run_api_v1_evals_runs_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["EvalRunRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["EvalRunCreated"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_eval_run_api_v1_evals_runs__run_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                run_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_ui_manifest_api_v1_ui_manifest_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["UIManifestResponse"];
                };
            };
        };
    };
    login_api_v1_auth_login_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["LoginRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["LoginResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    signup_api_v1_signup_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["SignupRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SignupResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    admin_me_api_v1_admin_me_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AdminMeResponse"];
                };
            };
        };
    };
    list_agents_api_v1_admin_agents_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AgentListResponse"];
                };
            };
        };
    };
    create_agent_api_v1_admin_agents_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CustomAgentCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CustomAgentResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_agent_api_v1_admin_agents__agent_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                agent_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CustomAgentResponse"] | components["schemas"]["ProfileAgentResponse"] | components["schemas"]["PluginAgentResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    update_agent_api_v1_admin_agents__agent_id__put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                agent_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CustomAgentUpdate"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CustomAgentResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    delete_agent_api_v1_admin_agents__agent_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                agent_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_users_api_v1_admin_users_get: {
        parameters: {
            query?: {
                limit?: number;
                offset?: number;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["UserListResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    create_user_api_v1_admin_users_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["UserCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["UserResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_user_api_v1_admin_users__user_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                user_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["UserResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    update_user_api_v1_admin_users__user_id__put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                user_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["UserUpdate"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["UserResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    delete_user_api_v1_admin_users__user_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                user_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_roles_api_v1_admin_roles_get: {
        parameters: {
            query?: {
                include_system?: boolean;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RoleListResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    create_role_api_v1_admin_roles_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            501: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["_NotImplementedBody"];
                };
            };
        };
    };
    list_permissions_api_v1_admin_roles_permissions_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PermissionListResponse"];
                };
            };
        };
    };
    get_role_api_v1_admin_roles__role_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                role_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RoleResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    update_role_api_v1_admin_roles__role_id__put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                role_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
            /** @description Successful Response */
            501: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["_NotImplementedBody"];
                };
            };
        };
    };
    delete_role_api_v1_admin_roles__role_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                role_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
            /** @description Successful Response */
            501: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
        };
    };
    list_tenants_api_v1_admin_tenants_get: {
        parameters: {
            query?: {
                limit?: number;
                offset?: number;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TenantListResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    create_tenant_api_v1_admin_tenants_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["TenantCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TenantResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_tenant_api_v1_admin_tenants__tenant_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                tenant_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TenantResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    update_tenant_api_v1_admin_tenants__tenant_id__put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                tenant_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["TenantUpdate"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TenantResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    delete_tenant_api_v1_admin_tenants__tenant_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                tenant_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    write_skill_api_v1_admin_skills_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["SkillWriteRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SkillSummary"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
}
