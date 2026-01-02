# Section 12: Open Questions & Future Considerations

Outstanding questions and planned enhancements beyond MVP scope:

---

### **Open Questions (Require Decision)**

#### **1. Multi-Tenancy Strategy**

**Question**: How should Taskforce handle multiple users/organizations in production?

**Options**:
- **Option A**: Single-tenant deployment (one instance per customer)
  - Pros: Simple, strong isolation, easier security
  - Cons: Higher infrastructure cost, harder to maintain multiple instances
  
- **Option B**: Multi-tenant with row-level security (RLS)
  - Pros: Efficient resource usage, single deployment
  - Cons: More complex, risk of data leakage, performance impact
  
- **Option C**: Hybrid (multi-tenant for small customers, dedicated for enterprise)
  - Pros: Flexible, cost-effective
  - Cons: Operational complexity

**Recommendation**: Start with Option A (single-tenant) for MVP, evaluate Option C for v2.0 based on customer demand.

**Impacts**: Database schema (add tenant_id columns), authentication (JWT with tenant claims), deployment strategy (Kubernetes namespaces per tenant).

---

#### **2. LLM Cost Management**

**Question**: How should we prevent runaway LLM costs?

**Current State**: No hard cost limits, only token logging.

**Options**:
- **Option A**: Per-session token limits (e.g., 50K tokens max)
- **Option B**: Per-user monthly budget with alerting
- **Option C**: Rate limiting (e.g., 10 missions per hour per user)
- **Option D**: Graceful degradation (use cheaper models for simple tasks)

**Recommendation**: Implement Option A + Option C for MVP, add Option B for production.

**Unresolved**: How to communicate limits to users? How to handle limit exhaustion mid-mission?

---

#### **3. State Size Growth**

**Question**: How should we handle sessions with very large execution histories?

**Current State**: All execution steps stored in single JSONB column, loaded on every state read.

**Problem**: After 100+ ReAct iterations, state size could exceed 1MB, slowing queries.

**Options**:
- **Option A**: Pagination (only load last N steps)
- **Option B**: Separate table for execution history (don't load with state)
- **Option C**: Compression (gzip state_json)
- **Option D**: Archival (move old sessions to cold storage after 30 days)

**Recommendation**: Implement Option B (separate execution_history table) in MVP, add Option D post-launch.

**Impacts**: Database schema changes, state loading logic, API responses (pagination required).

---

#### **4. Tool Security Model**

**Question**: How should we prevent malicious tool usage?

**Current State**: Basic validation (file path checks, timeout limits), but tools can still execute arbitrary code/commands.

**Concerns**:
- Python tool can import dangerous modules (e.g., `subprocess`, `os`)
- Shell tool can run destructive commands (e.g., `rm -rf`)
- File tool could read sensitive files (e.g., `/etc/passwd`)

**Options**:
- **Option A**: Whitelist approach (only allow specific imports/commands)
  - Pros: Secure
  - Cons: Limits agent capabilities, high maintenance
  
- **Option B**: Sandbox execution (Docker containers, seccomp profiles)
  - Pros: Strong isolation
  - Cons: Performance overhead, complexity
  
- **Option C**: Human-in-the-loop approval for dangerous operations
  - Pros: User control
  - Cons: Breaks automation, poor UX
  
- **Option D**: Trust-based (current approach + audit logging)
  - Pros: Full capabilities
  - Cons: High risk

**Recommendation**: Start with Option D (trust-based) for MVP with clear documentation, evaluate Option B (sandboxing) for enterprise customers.

**Unresolved**: Define "dangerous operation" criteria? Should we scan code for patterns before execution?

---

#### **5. RAG Index Management**

**Question**: Who manages the Azure AI Search index for RAG features?

**Current State**: Assumes pre-existing index, no management capabilities in Taskforce.

**Options**:
- **Option A**: External tool (users manage with Azure portal/SDK)
  - Pros: Separation of concerns
  - Cons: Poor UX, requires external knowledge
  
- **Option B**: Built-in indexing (Taskforce provides CLI commands to index documents)
  - Pros: Better UX, self-contained
  - Cons: Scope creep, complexity
  
- **Option C**: Hybrid (basic management in Taskforce, advanced via Azure)
  - Pros: Balance of convenience and flexibility
  - Cons: May confuse users

**Recommendation**: Option A for MVP (document external setup), consider Option C for v2.0.

**Unresolved**: How to handle index schema changes? How to validate index compatibility?

---

### **Future Enhancements (Post-MVP)**

#### **Phase 2: Advanced Planning**

**Parallel Task Execution**:
- Allow TodoList to execute independent tasks concurrently
- Modify PlanGenerator to identify parallelizable steps
- Update Agent execution loop to use `asyncio.TaskGroup`

**Benefit**: 2-3x faster execution for missions with independent subtasks
**Effort**: Medium (2-3 weeks)
**Risk**: Increased complexity, potential race conditions

---

**Dynamic Replanning**:
- Allow agent to revise TodoList mid-execution when context changes
- Add `replan` action type with LLM-based plan diff
- Track plan versions for audit trail

**Benefit**: More adaptive agent, better handles unexpected situations
**Effort**: Medium (3-4 weeks)
**Risk**: May cause mission drift, harder to debug

---

#### **Phase 3: Memory & Learning**

**Cross-Session Memory**:
- Implement Memory table with vector embeddings
- Add MemoryRetrieval tool (semantic search over past lessons)
- Inject relevant memories into system prompt dynamically

**Benefit**: Agent learns from experience, fewer repeated mistakes
**Effort**: High (4-6 weeks)
**Risk**: Incorrect lessons may propagate, privacy concerns

---

**Feedback Loop**:
- Capture user feedback on mission outcomes (thumbs up/down)
- Use feedback to refine prompts and tool selection
- Train custom model on successful mission patterns (future)

**Benefit**: Continuous improvement, higher success rate
**Effort**: High (6-8 weeks)
**Risk**: Feedback bias, requires ML expertise

---

#### **Phase 4: Collaboration**

**Multi-Agent Orchestration**:
- Implement `SubAgentTool` (convert agent to tool via `agent.to_tool()`)
- Allow orchestrator agent to delegate subtasks to specialized agents
- Add agent communication protocol

**Benefit**: Specialization (e.g., CodeAgent, ResearchAgent), better at complex tasks
**Effort**: High (6-8 weeks)
**Risk**: Coordination complexity, higher LLM costs

---

**Human-in-the-Loop**:
- Add `approval_required` flag to TodoItems
- Pause execution before dangerous operations
- Send notification (webhook, email) for user approval

**Benefit**: User control, reduced risk
**Effort**: Medium (3-4 weeks)
**Risk**: Breaks automation, notification fatigue

---

#### **Phase 5: Observability**

**Distributed Tracing**:
- Integrate OpenTelemetry for request tracing
- Trace LLM calls, tool executions, database queries
- Send traces to Jaeger or Azure Application Insights

**Benefit**: Easier debugging, performance insights
**Effort**: Medium (2-3 weeks)
**Risk**: Performance overhead, data volume

---

**Metrics Dashboard**:
- Grafana dashboard with key metrics:
  - Mission success rate
  - Average execution time
  - LLM token usage and cost
  - Tool usage patterns
  - Error rates by tool/category
- Alert on anomalies (spike in errors, high latency)

**Benefit**: Proactive issue detection, usage insights
**Effort**: Medium (3-4 weeks)
**Risk**: Dashboard maintenance overhead

---

**Session Replay**:
- Record full ReAct loop (thoughts, actions, observations)
- UI to replay session step-by-step for debugging
- Export to timeline visualization

**Benefit**: Better debugging, training data for improvements
**Effort**: Medium (3-4 weeks)
**Risk**: Storage cost for recordings

---

#### **Phase 6: Integrations**

**MCP (Model Context Protocol) Support**:
- Implement MCP client in `infrastructure/tools/mcp/`
- Allow agent to discover and use MCP servers (Playwright, Filesystem, etc.)
- Standard protocol for tool extensibility

**Benefit**: Ecosystem of tools, community contributions
**Effort**: High (4-6 weeks)
**Risk**: Protocol still evolving, breaking changes

---

**Slack/Teams Integration**:
- Chatbot interface for Slack/Microsoft Teams
- Users submit missions via chat
- Agent posts progress updates to thread
- Approve dangerous operations via button click

**Benefit**: Accessible interface, fits team workflows
**Effort**: Medium (3-4 weeks per platform)
**Risk**: Platform API rate limits, maintenance burden

---

**VS Code Extension**:
- VS Code extension to submit missions from IDE
- Inline code generation and editing
- View agent progress in sidebar

**Benefit**: Developer-friendly, tight integration
**Effort**: High (6-8 weeks)
**Risk**: Different tech stack (TypeScript), extension marketplace requirements

---

### **Technology Considerations**

#### **Alternative LLM Providers**

**Anthropic Claude**:
- Longer context windows (200K tokens)
- Better at following instructions (anecdotal)
- Already supported via LiteLLM

**Consideration**: Add Claude as model option in `llm_config.yaml`, compare performance with GPT-4.

---

**Local Models (Ollama, LM Studio)**:
- Run LLMs on-premise (no API costs)
- Data privacy (no external API calls)
- Limited by local GPU capacity

**Consideration**: Add Ollama support for air-gapped environments, document GPU requirements.

---

#### **Alternative Databases**

**Redis for State Caching**:
- Add Redis cache layer over `DbStateManager`
- Cache hot sessions (recently accessed)
- TTL-based eviction

**Benefit**: 10x faster state access for active sessions
**Effort**: Low (1-2 weeks)
**Trade-off**: Additional dependency, cache invalidation complexity

---

**DynamoDB for Serverless**:
- Replace PostgreSQL with DynamoDB for AWS Lambda deployment
- Pay-per-request pricing
- Infinite scalability

**Benefit**: True serverless, no database management
**Effort**: Medium (3-4 weeks)
**Trade-off**: Eventual consistency, limited query capabilities

---

#### **Alternative Deployment Platforms**

**AWS Lambda + API Gateway**:
- Serverless deployment
- Auto-scaling to zero
- Pay only for execution time

**Benefit**: Lower cost for low-traffic deployments
**Effort**: Medium (3-4 weeks)
**Trade-off**: Cold starts (5-10s), 15-minute execution limit

---

**Azure Container Apps**:
- Managed Kubernetes (simpler than AKS)
- Scale-to-zero capability
- Integrated Azure services

**Benefit**: Easier operations than Kubernetes
**Effort**: Low (1-2 weeks)
**Trade-off**: Azure vendor lock-in

---

### **Known Limitations (MVP)**

**1. No Parallel Tool Execution**:
- ReAct loop executes one tool at a time sequentially
- Independent operations (e.g., two API calls) can't run concurrently
- **Workaround**: None (planned for Phase 2)

**2. Limited Error Recovery**:
- Agent may get stuck if tool fails repeatedly
- No automatic fallback to alternative approaches
- **Workaround**: User must restart mission with refined prompt

**3. No Cost Guardrails**:
- Agent can consume unlimited LLM tokens
- No per-mission or per-user budget enforcement
- **Workaround**: Manual monitoring of token usage logs

**4. Single-Region Deployment**:
- No multi-region support for disaster recovery
- High latency for users far from deployment region
- **Workaround**: Deploy in user's closest region

**5. No Version Management**:
- No API versioning (/v1/ prefix exists but not enforced)
- Breaking changes will impact all clients
- **Workaround**: Careful backward compatibility, long deprecation periods

**6. Limited Observability**:
- Basic structured logging only
- No distributed tracing
- No metrics dashboard
- **Workaround**: Manual log analysis, external monitoring tools

---

### **Research Topics**

**1. Prompt Engineering Optimization**:
- **Question**: What prompt structure yields best task decomposition?
- **Approach**: A/B test different system prompts, measure success rate
- **Timeline**: Ongoing

**2. Tool Selection Strategy**:
- **Question**: Should agent decide tool before or after generating thought?
- **Current**: Tool selected based on thought content (sequential)
- **Alternative**: Parallel generation (thought + tool in single LLM call)
- **Approach**: Prototype alternative, benchmark latency and quality

**3. Context Window Management**:
- **Question**: What's the optimal message history window size?
- **Current**: Last 50 messages
- **Consideration**: Larger window = more context but higher cost and latency
- **Approach**: Experiment with 25, 50, 100 messages, measure impact

**4. State Compression**:
- **Question**: Can we use LLM to summarize old execution history?
- **Approach**: Periodically compress old observations into summary
- **Benefit**: Reduce state size while preserving essential context
- **Risk**: Information loss

---

### **Compliance & Governance**

**GDPR Compliance (if applicable)**:
- Right to erasure: Implement session deletion API
- Data portability: Export session data as JSON
- Audit logging: Track all data access
- Data retention: Auto-delete sessions after 90 days (configurable)

**SOC 2 Type II (future certification)**:
- Access controls: RBAC implementation
- Encryption: At rest and in transit
- Incident response: Document procedures
- Change management: Audit trail for code changes

**Industry-Specific**:
- **Healthcare (HIPAA)**: PHI handling, BAA requirements, audit logs
- **Finance (PCI DSS)**: No credit card data in state, secure API keys
- **Government (FedRAMP)**: Air-gapped deployment, US-based LLMs

---

### **Migration Path from Agent V2**

**For Existing Agent V2 Users**:

**Step 1: State Migration**:
```powershell
# Convert Agent V2 file states to Taskforce database
uv run python scripts/migrate_v2_states.py --source capstone/agent_v2/work_dir --target DATABASE_URL
```

**Step 2: Configuration Mapping**:
- Agent V2 `agent_factory` → Taskforce `configs/prod.yaml`
- V2 tool names preserved (no breaking changes)

**Step 3: CLI Compatibility Layer**:
- Taskforce CLI accepts same commands as Agent V2
- Alias `agent` → `taskforce` for backward compatibility

**Breaking Changes**:
- Session ID format changed (UUID4 vs custom)
- State schema: flat dict → versioned JSONB
- Tool parameter names may differ slightly

**Timeline**: Migration tool available in v1.0 beta

---

### **Success Metrics (Post-Launch)**

**Product Metrics**:
- Mission success rate: >80% (missions completed without error)
- Average execution time: <2 minutes per mission
- User retention: >60% weekly active users (WAU)

**Technical Metrics**:
- API uptime: >99.5% (staging), >99.9% (production)
- P95 latency: <10s per ReAct iteration
- Error rate: <5% of tool executions

**Business Metrics**:
- LLM cost per mission: <$0.50 (target for profitability)
- Infrastructure cost per user: <$10/month
- Support ticket volume: <10% of total missions

---
