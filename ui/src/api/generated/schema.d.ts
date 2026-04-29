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
        /**
         * AgentListResponse
         * @description Response schema for listing all agents.
         */
        AgentListResponse: {
            /** Agents */
            agents: (components["schemas"]["CustomAgentResponse"] | components["schemas"]["ProfileAgentResponse"] | components["schemas"]["PluginAgentResponse"])[];
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
             * @description Agent profile.
             * @default butler
             */
            profile: string;
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
}
