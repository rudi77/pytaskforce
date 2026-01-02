# Section 6: External APIs

Taskforce integrates with several external APIs for LLM capabilities and RAG functionality:

---

### **OpenAI API**

- **Purpose:** Primary LLM provider for thought generation, plan generation, and tool reasoning in the ReAct loop
- **Documentation:** https://platform.openai.com/docs/api-reference
- **Base URL(s):** 
  - Production: `https://api.openai.com/v1`
  - Versioned: `https://api.openai.com/v1` (versioning via model names)
- **Authentication:** Bearer token authentication via `Authorization: Bearer $OPENAI_API_KEY` header
- **Rate Limits:** 
  - GPT-4: 10,000 TPM (tokens per minute), 500 RPM (requests per minute) - varies by tier
  - GPT-4-mini: 200,000 TPM, 5,000 RPM
  - Monitor via `x-ratelimit-*` response headers

**Key Endpoints Used:**
- `POST /chat/completions` - Chat completion for ReAct thought generation and planning
- `POST /completions` (legacy) - Text completion (if needed for specific use cases)

**Integration Notes:**
- Integrated via **LiteLLM library** - not direct OpenAI SDK calls
- LiteLLM provides unified interface across providers (OpenAI, Azure, Anthropic)
- Automatic retry with exponential backoff on rate limits (429) and server errors (5xx)
- Token usage logged via structlog for cost tracking
- Parameter mapping for GPT-5 models (temperature → effort, top_p → reasoning)
- Model aliases configured in `llm_config.yaml`: main, fast, powerful, legacy
- Environment variable: `OPENAI_API_KEY` (required for OpenAI provider)

---

### **Azure OpenAI API**

- **Purpose:** Enterprise LLM provider alternative for organizations requiring Azure-hosted models (data residency, compliance, private networking)
- **Documentation:** https://learn.microsoft.com/en-us/azure/ai-services/openai/reference
- **Base URL(s):** 
  - Configured per deployment: `https://{resource-name}.openai.azure.com/`
  - API Version: `2024-02-15-preview` (configurable)
- **Authentication:** 
  - API Key: `api-key: $AZURE_OPENAI_API_KEY` header
  - Alternative: Azure AD OAuth tokens (future enhancement)
- **Rate Limits:** 
  - Configured per deployment in Azure portal
  - Typically: 240,000 TPM for GPT-4 deployments
  - Monitor via Azure metrics

**Key Endpoints Used:**
- `POST /openai/deployments/{deployment-id}/chat/completions?api-version={version}` - Chat completion

**Integration Notes:**
- Integrated via **LiteLLM library** with Azure provider configuration
- Deployment names mapped to model aliases in `llm_config.yaml`:
  ```yaml
  azure:
    enabled: true
    deployment_mapping:
      main: "gpt-4-deployment-prod"
      fast: "gpt-4-mini-deployment-prod"
  ```
- Environment variables: 
  - `AZURE_OPENAI_API_KEY` (required if Azure enabled)
  - `AZURE_OPENAI_ENDPOINT` (required if Azure enabled)
- Same parameter mapping and retry logic as OpenAI
- Optional: Private endpoint support via Azure VNet integration

---

### **Azure AI Search API**

- **Purpose:** Semantic search and document retrieval for RAG (Retrieval Augmented Generation) agent capabilities. Enables vector search over document corpus.
- **Documentation:** https://learn.microsoft.com/en-us/rest/api/searchservice/
- **Base URL(s):** 
  - Configured per search service: `https://{search-service-name}.search.windows.net/`
  - API Version: `2023-11-01` (stable)
- **Authentication:** 
  - Admin Key: `api-key: $AZURE_SEARCH_API_KEY` header (for indexing)
  - Query Key: `api-key: $AZURE_SEARCH_QUERY_KEY` header (for search only)
- **Rate Limits:** 
  - Depends on service tier (Basic, Standard, etc.)
  - Standard: 200 queries/second, 3 indexing requests/second
  - Monitor via Azure portal metrics

**Key Endpoints Used:**
- `POST /indexes/{index-name}/docs/search?api-version={version}` - Semantic vector search
- `GET /indexes/{index-name}/docs/{doc-id}?api-version={version}` - Document retrieval by ID
- `GET /indexes/{index-name}/docs?api-version={version}` - List documents with filtering

**Integration Notes:**
- Integrated via **Azure Search SDK** (`azure-search-documents` package)
- RAG tools (SemanticSearchTool, ListDocumentsTool, GetDocumentTool) in `infrastructure/tools/rag/`
- Shared Azure Search client in `azure_search_base.py`
- Security filtering support (user_id, org_id, scope fields)
- Vector search configuration:
  - Embedding model: Configurable (typically text-embedding-ada-002 or similar)
  - Vector dimensions: 1536 (for ada-002) or model-specific
  - Similarity metric: Cosine similarity
- Environment variables:
  - `AZURE_SEARCH_ENDPOINT` (required for RAG features)
  - `AZURE_SEARCH_API_KEY` (required for RAG features)
  - `AZURE_SEARCH_INDEX_NAME` (default: "documents")
- Optional feature: RAG capabilities disabled if environment variables not set

---

### **GitHub API (Optional)**

- **Purpose:** Git repository operations for GitHubTool (create repos, manage issues, PRs, etc.)
- **Documentation:** https://docs.github.com/en/rest
- **Base URL(s):** 
  - REST API: `https://api.github.com`
  - GraphQL API: `https://api.github.com/graphql` (future enhancement)
- **Authentication:** 
  - Personal Access Token: `Authorization: Bearer $GITHUB_TOKEN` header
  - OAuth tokens (future enhancement)
- **Rate Limits:** 
  - Authenticated: 5,000 requests/hour
  - Unauthenticated: 60 requests/hour
  - GraphQL: 5,000 points/hour (different counting)

**Key Endpoints Used:**
- `POST /user/repos` - Create repository
- `GET /repos/{owner}/{repo}` - Get repository details
- `POST /repos/{owner}/{repo}/issues` - Create issue
- `GET /repos/{owner}/{repo}/contents/{path}` - Read file contents

**Integration Notes:**
- Integrated via **PyGithub library** (optional dependency)
- Used by GitHubTool in `infrastructure/tools/native/git_tools.py`
- Environment variable: `GITHUB_TOKEN` (optional, tool gracefully degrades without it)
- Fallback to local git operations if GitHub API unavailable

---

### **External API Error Handling Strategy**

**Common Error Patterns:**

1. **Rate Limiting (429 responses)**
   - Strategy: Exponential backoff retry (1s, 2s, 4s, 8s)
   - Max retries: 3 attempts
   - Respect `Retry-After` header if present
   - Log rate limit events for monitoring

2. **Server Errors (5xx responses)**
   - Strategy: Retry with exponential backoff
   - Max retries: 3 attempts
   - Circuit breaker pattern after 5 consecutive failures (future enhancement)

3. **Authentication Errors (401, 403)**
   - Strategy: No retry (configuration error)
   - Log error with clear message about missing/invalid API keys
   - Graceful degradation (disable features requiring that API)

4. **Network Timeouts**
   - Default timeout: 30 seconds for LLM calls, 10 seconds for other APIs
   - Retry on connection timeout (max 2 retries)
   - Log timeout events for monitoring

5. **Invalid Requests (4xx except 429)**
   - Strategy: No retry (client error)
   - Log full request/response for debugging
   - Return actionable error message to user

**Retry Configuration:**
```python
# Example from llm_config.yaml
retry:
  max_attempts: 3
  backoff_multiplier: 2
  initial_delay_ms: 1000
  max_delay_ms: 10000
  retry_on_errors:
    - "RateLimitError"
    - "ServiceUnavailableError"
    - "InternalServerError"
```

---

### **API Cost Monitoring**

**Token Usage Tracking (LLM APIs):**
- Log every LLM call with token counts:
  ```python
  logger.info(
      "llm.completion",
      model=model_name,
      prompt_tokens=usage.prompt_tokens,
      completion_tokens=usage.completion_tokens,
      total_tokens=usage.total_tokens,
      cost_estimate_usd=calculate_cost(model, usage)
  )
  ```
- Daily/monthly cost aggregation via log analysis
- Budget alerts (future enhancement)

**Azure AI Search Usage:**
- Query count logging for capacity planning
- Index size monitoring
- Storage cost tracking (documents stored)

---

### **Rationale:**

**API Integration Decisions:**

1. **LiteLLM Abstraction**: Chose LiteLLM over direct OpenAI SDK. Rationale: Multi-provider support (OpenAI + Azure + Anthropic) through single interface. Reduces vendor lock-in. Trade-off: Additional dependency vs. flexibility.

2. **Azure AI Search SDK**: Chose official SDK over REST API calls. Rationale: Type-safe, handles authentication/retry automatically, better error messages. Trade-off: Heavier dependency vs. developer experience.

3. **Optional GitHub Integration**: Made GitHub API optional (tool degrades gracefully). Rationale: Not all deployments need GitHub access. Reduces mandatory dependencies. Trade-off: More complex conditional logic vs. deployment flexibility.

4. **Aggressive Retry Strategy**: Max 3 retries with exponential backoff. Rationale: LLM APIs occasionally unstable, retries improve reliability. Trade-off: Slower failures vs. success rate.

**Key Assumptions:**
- OpenAI API stability sufficient for production use (needs validation with historical uptime data)
- Azure AI Search latency acceptable for RAG queries (<500ms p95) (needs validation via load testing)
- Token costs within budget (needs validation with usage projections)

**Security Considerations:**
- All API keys via environment variables (never hardcoded)
- No API keys logged (filtered from structured logs)
- HTTPS enforced for all external API calls
- Timeout limits prevent hung connections

---

🏗️ **Proceeding to Core Workflows...**

---
