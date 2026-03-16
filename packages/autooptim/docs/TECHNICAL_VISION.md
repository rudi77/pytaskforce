# AutoOptim: LLM-Driven Iterative Software Optimization

**Technical Vision Document**
**Version:** 1.0
**Date:** 2026-03-16

---

## 1. Executive Summary

AutoOptim is an open-source framework that applies the scientific method to software optimization — automatically. It uses Large Language Models to propose targeted, single-variable experiments on any codebase, evaluates the results against measurable metrics, and keeps only the improvements. The entire process is configured through a single YAML file, works with any programming language, and uses Git as a safety net for zero-risk experimentation.

**The core insight:** If you can measure it, an LLM can optimize it.

Where traditional optimization requires deep expertise, manual benchmarking, and hours of trial-and-error, AutoOptim transforms optimization into a continuous, automated process that runs overnight and delivers reviewed, committed improvements by morning.

---

## 2. The Problem

### 2.1 Manual Optimization Doesn't Scale

Every development team faces optimization tasks: reducing memory consumption, speeding up hot paths, simplifying complex code, tuning configuration parameters, improving AI agent prompts. The current approach is almost always the same:

1. Developer identifies a bottleneck
2. Developer hypothesizes a fix
3. Developer implements the change
4. Developer runs benchmarks
5. Developer compares results
6. If worse → revert. If better → commit.
7. Repeat from step 2.

This process is **slow** (hours per cycle), **expensive** (senior developer time), and **inconsistent** (depends on who's doing it). A single optimization session might explore 3-5 hypotheses. A systematic exploration of the search space would require hundreds.

### 2.2 The Search Space Explodes

Modern software systems have thousands of tunable parameters:

- A Kubernetes deployment has CPU limits, memory limits, replica counts, health check intervals, connection pool sizes, timeout values, cache TTLs
- An AI agent has model selection, temperature, max tokens, system prompts, tool configurations, context window policies, planning strategies
- A web application has database query patterns, caching strategies, bundle sizes, lazy loading thresholds, compression settings

Each parameter interacts with others. The combinatorial search space is vast. Manual exploration covers a negligible fraction.

### 2.3 Optimization Knowledge Lives in Heads

When a senior engineer optimizes a critical service, the knowledge of *what was tried*, *what worked*, and *why* is rarely captured systematically. The next time a similar optimization is needed, someone starts from scratch. There is no institutional memory of optimization experiments.

### 2.4 No Unified Framework

The tooling landscape is fragmented:

- Python has `cProfile`, `tracemalloc`, `radon`
- JavaScript has Lighthouse, webpack-bundle-analyzer
- Go has `pprof`, `benchstat`
- Java has JMH, VisualVM
- AI/ML has Optuna, Ray Tune, Weights & Biases

Each tool is language-specific and measures a narrow slice. None of them *proposes* improvements. None of them *applies* changes automatically. None of them runs a *closed-loop* optimization cycle.

### 2.5 AI Code Assistants Are Reactive, Not Proactive

GitHub Copilot, Claude, and ChatGPT can suggest optimizations when asked. But they operate in a **single-shot** mode: one suggestion at a time, with no measurement feedback loop. They don't know if their suggestion actually improved performance, and they can't build on previous results.

---

## 3. The Solution: LLM-Driven Iterative Optimization

AutoOptim closes the loop. It combines the code understanding capabilities of LLMs with automated measurement and the scientific rigor of controlled experiments.

### 3.1 The Optimization Loop

```
                    ┌─────────────────────────────────┐
                    │         EXPERIMENT LOG           │
                    │  (what worked, what didn't)      │
                    └──────────────┬──────────────────┘
                                   │ learns from history
                                   ▼
┌──────────────────────────────────────────────────────────┐
│  1. PROPOSE                                              │
│     LLM analyzes history + current files → hypothesis    │
│     "Reducing context_policy.max_items from 10 to 6      │
│      will cut token usage 40% with minimal quality loss" │
└────────────────────────────┬─────────────────────────────┘
                             │
                             ▼
┌──────────────────────────────────────────────────────────┐
│  2. MUTATE                                               │
│     Apply file changes (config, code, prompts)           │
│     Validate: syntax check → preflight → tests pass      │
└────────────────────────────┬─────────────────────────────┘
                             │
                             ▼
┌──────────────────────────────────────────────────────────┐
│  3. EVALUATE                                             │
│     Run benchmarks / test suite / eval framework         │
│     Collect scores: accuracy, latency, memory, cost      │
└────────────────────────────┬─────────────────────────────┘
                             │
                             ▼
┌──────────────────────────────────────────────────────────┐
│  4. DECIDE                                               │
│     composite_score >= baseline - tolerance?              │
│     YES → git commit (KEEP)                              │
│     NO  → git reset --hard (DISCARD)                     │
└────────────────────────────┬─────────────────────────────┘
                             │
                             ▼
                      next iteration
```

Each iteration takes minutes, not hours. AutoOptim can run 20-50 experiments overnight while the team sleeps.

### 3.2 Why LLMs Are Uniquely Suited

Traditional optimization tools find bottlenecks. They don't fix them. An LLM can:

- **Read code** and understand what it does at a semantic level
- **Read experiment history** and learn what worked (and what didn't) in previous iterations
- **Generate targeted hypotheses** based on understanding, not random search
- **Write actual code changes** — not just numeric parameter adjustments
- **Reason about trade-offs** between quality, performance, and cost

This is fundamentally different from hyperparameter tuning (Optuna, Ray Tune), which operates on numeric search spaces. AutoOptim operates on the *code itself* — the actual source files, configuration files, and prompt templates.

### 3.3 The Scientific Method, Applied to Code

Each experiment follows strict scientific methodology:

1. **Hypothesis**: "Changing X will improve Y because Z"
2. **Single variable**: Only one thing changes per experiment
3. **Measurement**: Quantitative scores from automated evaluation
4. **Reproducibility**: Git commits capture exact state; experiment log captures all results
5. **Iteration**: Each experiment builds on the accumulated knowledge of previous ones

### 3.4 Safety by Design

AutoOptim is designed to be safe enough to run unattended:

| Safety Mechanism | How It Works |
|-----------------|-------------|
| **Preflight checks** | Compilation, linting, import checks run *before* expensive evaluation |
| **Allowed/blocked paths** | LLM can only modify whitelisted files and directories |
| **Safe key whitelists** | For config files, only specified keys can be changed |
| **Syntax validation** | Code changes are syntax-checked before being written |
| **Test suites as invariants** | Tests must pass as a preflight condition |
| **Git-based rollback** | Failed experiments are `git reset --hard` — zero permanent damage |
| **Cost budgets** | `max_cost_usd` and `max_iterations` prevent runaway spending |
| **Human review** | All kept changes are regular git commits, reviewable via PR |

---

## 4. Architecture

### 4.1 Protocol-Based Extension Points

AutoOptim is built on six Python Protocols (PEP 544) that define clean extension points:

```
┌─────────────────────────────────────────────────────────────┐
│                      RUNNER (Orchestrator)                    │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌─────────────┐ │
│  │ Proposer │→ │ Mutator  │→ │Evaluator │→ │   Metric    │ │
│  │ Protocol │  │ Protocol │  │ Protocol │  │  Protocol   │ │
│  └──────────┘  └────┬─────┘  └────┬─────┘  └─────────────┘ │
│                     │             │                          │
│              ┌──────┴──────┐ ┌────┴─────┐                   │
│              │  Preflight  │ │  Score   │                   │
│              │  Protocol   │ │  Parser  │                   │
│              └─────────────┘ │ Protocol │                   │
│                              └──────────┘                   │
└─────────────────────────────────────────────────────────────┘
```

| Protocol | Responsibility | Built-in Implementations |
|----------|---------------|-------------------------|
| `MutatorProtocol` | Apply file changes safely | YamlMutator, CodeMutator, TextMutator |
| `EvaluatorProtocol` | Run evaluation, return scores | CommandEvaluator, ScriptEvaluator |
| `MetricProtocol` | Compute composite scalar | ConfigurableMetric (weighted formula from YAML) |
| `ProposerProtocol` | Generate experiment proposals via LLM | ExperimentProposer (litellm-based) |
| `ScoreParserProtocol` | Parse raw eval output into Scores | JsonScoreParser |
| `PreflightProtocol` | Validate mutations before evaluation | Configurable shell commands |

Any protocol can be replaced with a custom implementation by specifying a `class: "module:ClassName"` in the YAML config.

### 4.2 Config-Driven Design

The entire optimization target is defined in a single YAML file. No code changes needed for new domains:

```yaml
name: "my-optimization"
project_root: "."

categories:
  <name>:
    weight: <float>           # how often to propose in this category
    mutator:
      type: yaml | code | text | custom
      allowed_paths: [...]    # what the LLM may touch
      blocked_paths: [...]    # what it must never touch
      safe_keys: { ... }      # for YAML: which keys are modifiable
      preflight: ["cmd"]      # validation commands after mutation
    context_files: [...]      # files shown to the LLM for context

evaluator:
  type: command | script | custom
  command: "..."              # shell command that produces scores
  quick_task: "..."           # fast eval for most iterations
  full_task: "..."            # thorough eval for periodic validation

metric:
  scores: [...]               # named metrics from the evaluator
  composite:                  # how to combine into a single number
    quality: { weight: 0.9, components: { ... } }
    efficiency: { weight: 0.1, type: ratio_to_baseline, components: [...] }

proposer:
  model: "claude-sonnet-4-20250514"
  system_prompt_file: "prompts/system.md"  # domain-specific instructions

runner:
  max_iterations: 30
  max_cost_usd: 20.0
  tolerance: 0.02             # keep if composite >= baseline - tolerance
```

### 4.3 Git as the Experiment Journal

Git provides the persistence and safety layer:

- **Each kept experiment** = one git commit with a descriptive message
- **Each discarded experiment** = `git reset --hard HEAD~1` (as if it never happened)
- **Each run** = a dedicated branch (`autooptim/run-20260316-143022`)
- **Experiment log** = TSV file outside git, never affected by resets
- **Crash recovery** = state file enables `--resume` after interruption

The result: a clean, linear git history where every commit is a verified improvement.

---

## 5. Use Cases

### 5.1 Performance Optimization

**Problem:** A Python service has grown to consume 2GB RSS in production. The team needs to reduce memory usage without breaking functionality.

```yaml
name: memory-optimization
categories:
  code:
    mutator:
      type: code
      allowed_paths: ["src/myservice/"]
      blocked_paths: ["tests/", "src/myservice/migrations/"]
      preflight:
        - "python -c 'import myservice'"
        - "pytest tests/ -x -q --timeout=120"
    context_files:
      - "src/myservice/data_store.py"
      - "src/myservice/cache.py"

evaluator:
  type: script
  script: |
    import subprocess, json, tracemalloc
    tracemalloc.start()
    from myservice.benchmark import run_standard_workload
    run_standard_workload()
    current, peak = tracemalloc.get_traced_memory()
    result = subprocess.run(["pytest", "tests/", "-q", "--tb=no"],
                           capture_output=True, text=True)
    print(json.dumps({
        "peak_mb": peak / 1024 / 1024,
        "current_mb": current / 1024 / 1024,
        "test_pass": 1.0 if result.returncode == 0 else 0.0,
    }))

metric:
  scores:
    - { name: test_pass, range: [0, 1] }
    - { name: peak_mb, type: lower_is_better }
    - { name: current_mb, type: lower_is_better }
  composite:
    quality:
      weight: 0.4
      components: { test_pass: 1.0 }
    efficiency:
      weight: 0.6
      type: ratio_to_baseline
      components: [peak_mb, current_mb]
```

**What the LLM might propose:**
- Replace `dict` accumulations with generators
- Use `__slots__` on frequently instantiated classes
- Switch from eager loading to lazy initialization
- Replace large in-memory caches with bounded LRU caches
- Reduce string copies in hot parsing loops

**This works for any language:**

| Language | Evaluator Command | What It Measures |
|----------|-------------------|-----------------|
| **Go** | `go test -bench=. -benchmem -json ./...` | allocs/op, bytes/op |
| **Rust** | `cargo bench --bench memory -- --output-format json` | Peak RSS via `/proc/self/status` |
| **Java** | `mvn test -pl benchmark && parse_jmh_results.py` | Heap usage, GC pauses |
| **C#** | `dotnet run --project Benchmark -- --json` | BenchmarkDotNet memory stats |
| **Node.js** | `node --expose-gc benchmark.js` | `process.memoryUsage()` |

### 5.2 Code Quality Improvement

**Problem:** A codebase has accumulated complexity over two years. Average cyclomatic complexity is 12, and new developers struggle to onboard.

```yaml
name: code-simplification
categories:
  refactor:
    weight: 1.0
    mutator:
      type: code
      allowed_paths: ["src/"]
      blocked_paths: ["tests/", "src/generated/"]
      preflight:
        - "pytest tests/ -x -q --timeout=60"
    context_files:
      - "src/core/engine.py"
      - "src/core/processor.py"

evaluator:
  type: script
  script: |
    import subprocess, json
    cc = subprocess.run(["radon", "cc", "src/", "-j", "-a"],
                       capture_output=True, text=True)
    data = json.loads(cc.stdout)
    loc = subprocess.run(["cloc", "src/", "--json", "--quiet"],
                        capture_output=True, text=True)
    loc_data = json.loads(loc.stdout)
    tests = subprocess.run(["pytest", "tests/", "-q", "--tb=no"],
                          capture_output=True, text=True)
    print(json.dumps({
        "test_pass": 1.0 if tests.returncode == 0 else 0.0,
        "avg_complexity": float(data.get("average", 10)),
        "total_loc": float(loc_data.get("Python", {}).get("code", 1000)),
    }))

metric:
  scores:
    - { name: test_pass, range: [0, 1] }
    - { name: avg_complexity, type: lower_is_better }
    - { name: total_loc, type: lower_is_better }
  composite:
    quality:
      weight: 0.5
      components: { test_pass: 1.0 }
    efficiency:
      weight: 0.5
      type: ratio_to_baseline
      components: [avg_complexity, total_loc]

proposer:
  system_prompt: |
    You are a code simplification expert. Your goal: reduce cyclomatic
    complexity and lines of code while keeping ALL tests green.
    Focus on: extracting functions, removing dead code, simplifying
    conditionals, replacing complex patterns with stdlib.
    NEVER change public APIs or remove tests.
```

### 5.3 AI Agent Optimization

**Problem:** An AI coding agent scores 65% on task completion benchmarks. The team wants to push it above 80% without increasing token cost.

```yaml
name: agent-optimization
categories:
  config:
    weight: 0.50
    mutator:
      type: yaml
      allowed_paths: ["configs/agent.yaml"]
      safe_keys:
        agent: [planning_strategy, max_steps, planning_strategy_params]
        context_policy: [max_items, max_chars_per_item, max_total_chars]
        tools: null
    context_files: ["configs/agent.yaml"]

  prompt:
    weight: 0.35
    mutator:
      type: text
      allowed_paths: ["prompts/"]
    context_files: ["prompts/system_prompt.py"]

  code:
    weight: 0.15
    mutator:
      type: code
      allowed_paths: ["src/agent/strategies/", "src/agent/context/"]
      blocked_paths: ["src/agent/api/", "tests/"]
      preflight: ["python -c 'import agent'"]
    context_files: ["src/agent/strategies/react.py"]

evaluator:
  type: command
  command: "python evals/run_eval.py {task_name}"
  quick_task: "coding_generation"
  full_task: "coding_full"

metric:
  scores:
    - { name: task_completion, range: [0, 1] }
    - { name: output_accuracy, range: [0, 1] }
    - { name: efficiency_tokens, type: lower_is_better }
  composite:
    quality:
      weight: 0.90
      components: { task_completion: 0.6, output_accuracy: 0.4 }
    efficiency:
      weight: 0.10
      type: ratio_to_baseline
      components: [efficiency_tokens]
```

**What the LLM might discover:**
- Switching planning strategy from `native_react` to `plan_and_execute` improves task completion by 8%
- Adding "always read the full file before editing" to the system prompt reduces errors by 15%
- Reducing `context_policy.max_items` from 10 to 6 saves 40% tokens with only 2% quality loss
- Adding a `grep` tool to the tool list improves code search tasks significantly

### 5.4 Infrastructure Configuration Tuning

**Problem:** A Go microservice's Kubernetes deployment is over-provisioned. The team wants to reduce costs while maintaining p99 latency SLA.

```yaml
name: k8s-resource-optimization
categories:
  resources:
    weight: 1.0
    mutator:
      type: yaml
      allowed_paths: ["k8s/deployment.yaml"]
      safe_keys:
        spec:
          - replicas
        resources:
          - limits
          - requests
    context_files: ["k8s/deployment.yaml"]

evaluator:
  type: command
  command: >
    kubectl apply -f k8s/deployment.yaml &&
    sleep 30 &&
    hey -n 10000 -c 100 http://myservice:8080/api/health |
    python3 parse_hey_output.py
  timeout: 120
  quick_task: "quick"
  full_task: "full"

metric:
  scores:
    - { name: p99_latency_ms, type: lower_is_better }
    - { name: error_rate, type: lower_is_better }
    - { name: cpu_millicores, type: lower_is_better }
    - { name: memory_mb, type: lower_is_better }
  composite:
    quality:
      weight: 0.6
      components:
        p99_latency_ms: 0.5  # treated as lower_is_better
        error_rate: 0.5
    efficiency:
      weight: 0.4
      type: ratio_to_baseline
      components: [cpu_millicores, memory_mb]
```

### 5.5 LLM Cost Optimization

**Problem:** An AI-powered application spends $15k/month on API calls. The team wants to reduce costs while maintaining output quality.

```yaml
name: llm-cost-optimization
categories:
  prompts:
    weight: 0.6
    mutator:
      type: text
      allowed_paths: ["prompts/"]
    context_files: ["prompts/summarize.md", "prompts/extract.md"]

  config:
    weight: 0.4
    mutator:
      type: yaml
      allowed_paths: ["config/llm.yaml"]
      safe_keys:
        model: null
        temperature: null
        max_tokens: null
    context_files: ["config/llm.yaml"]

evaluator:
  type: command
  command: "python evals/quality_and_cost.py"

metric:
  scores:
    - { name: quality_score, range: [0, 1] }
    - { name: cost_per_request, type: lower_is_better }
    - { name: tokens_per_request, type: lower_is_better }
  composite:
    quality:
      weight: 0.5
      components: { quality_score: 1.0 }
    efficiency:
      weight: 0.5
      type: ratio_to_baseline
      components: [cost_per_request, tokens_per_request]
```

**What the LLM might discover:**
- Shorter, more direct prompts that reduce token usage by 30% with no quality loss
- Switching certain calls from GPT-4 to GPT-4-mini where quality is sufficient
- Removing redundant instructions from system prompts
- Restructuring few-shot examples to be more token-efficient

---

## 6. Multi-Language Support

AutoOptim is **language-agnostic by design**. It operates on text files and shell commands. Any language with a build tool and a test runner works:

| Language | Mutator | Preflight Check | Benchmark Tool | Example Eval Command |
|----------|---------|-----------------|---------------|---------------------|
| **Python** | `code` | `python -c "import myapp"` | pytest-benchmark, tracemalloc | `pytest --benchmark-json=out.json` |
| **TypeScript** | `code` | `npx tsc --noEmit` | Jest, Vitest, Lighthouse | `npm run bench -- --json` |
| **Go** | `code` | `go build ./...` | built-in `testing.B` | `go test -bench=. -benchmem -json` |
| **Rust** | `code` | `cargo check` | Criterion, built-in bench | `cargo bench -- --output-format json` |
| **Java** | `code` | `./gradlew compileJava` | JMH | `./gradlew jmh -PjmhOutputFormat=json` |
| **Kotlin** | `code` | `./gradlew compileKotlin` | JMH, kotlinx-benchmark | Same as Java |
| **C#/.NET** | `code` | `dotnet build` | BenchmarkDotNet | `dotnet run -c Release -- --json` |
| **C/C++** | `code` | `make` or `cmake --build .` | Google Benchmark, perf | `./benchmark --benchmark_format=json` |
| **Ruby** | `code` | `ruby -c myapp.rb` | benchmark-ips | `ruby bench.rb` |
| **SQL** | `text` | SQL syntax check | pgbench, EXPLAIN | `pgbench -t 1000 -j 4 && parse.py` |
| **Terraform** | `text` | `terraform validate` | Infracost | `infracost breakdown --format json` |
| **Docker** | `text` | `hadolint Dockerfile` | `docker build` | `docker inspect --format json` |
| **YAML/JSON** | `yaml` | Schema validation | Domain-specific | Application benchmark |

**Key insight:** The language's own toolchain provides the preflight checks and benchmarks. AutoOptim simply orchestrates the loop.

---

## 7. Team Integration Patterns

### 7.1 Nightly Optimization Runs

Run AutoOptim as a nightly CI/CD job. Results are committed to a branch for morning review.

```yaml
# .github/workflows/autooptim-nightly.yml
name: Nightly Optimization
on:
  schedule:
    - cron: '0 2 * * *'  # 2 AM daily

jobs:
  optimize:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pip install autooptim
      - run: |
          autooptim run \
            --config .autooptim/performance.yaml \
            --max-iterations 15 \
            --max-cost-usd 5.00
      - run: |
          git push origin autooptim/run-$(date +%Y%m%d)
```

**Morning ritual:** Team reviews the optimization branch. Cherry-pick the improvements worth keeping. Discard the rest.

### 7.2 Pre-Release Performance Gate

Before each release, squeeze out performance improvements within a cost budget:

```bash
# In the release pipeline
autooptim run \
  --config .autooptim/pre-release.yaml \
  --max-iterations 10 \
  --max-cost-usd 3.00 \
  --eval-mode full
```

### 7.3 Continuous Agent Improvement

For AI/ML teams, run AutoOptim against eval suites after each model or prompt change:

```bash
# After updating the base model
autooptim run \
  --config .autooptim/agent-tuning.yaml \
  --max-iterations 20 \
  --eval-mode quick
```

This creates an **automated prompt engineering pipeline** — the LLM optimizes its own prompts based on eval results.

### 7.4 Tech Debt Reduction Sprints

Configure for complexity reduction, run for N iterations, review the simplifications:

```bash
# During a dedicated tech debt sprint
autooptim run \
  --config .autooptim/simplify.yaml \
  --max-iterations 30 \
  --max-cost-usd 10.00

# Review all kept experiments
git log --oneline autooptim/run-latest..HEAD
```

### 7.5 Onboarding New Team Members

A junior developer can run AutoOptim to explore optimization opportunities and learn from the LLM's hypotheses and explanations — even if they don't keep the changes.

---

## 8. Safety & Guardrails

AutoOptim is designed to be **safe enough to run unattended** while being **transparent enough for human review**.

### 8.1 Defense in Depth

```
Layer 1: PATH RESTRICTIONS
  ├── allowed_paths: only these files can be modified
  ├── blocked_paths: these files are never touched
  └── safe_keys: for YAML, only these keys are changeable

Layer 2: PREFLIGHT VALIDATION
  ├── Syntax check (compile, tsc, go vet, cargo check)
  ├── Import/build check (does the project still compile?)
  ├── Lint check (ruff, eslint, clippy)
  └── Test suite (pytest, jest, go test — must pass)

Layer 3: GIT SAFETY NET
  ├── Every change is a commit (inspectable, revertable)
  ├── Failed experiments are git reset --hard (zero trace)
  ├── Experiment log persists outside git (never lost)
  └── Crash recovery via state file + --resume

Layer 4: BUDGET CONTROLS
  ├── max_iterations: hard cap on experiments
  ├── max_cost_usd: budget cap on LLM/eval spending
  └── tolerance: threshold for keeping marginal changes

Layer 5: HUMAN REVIEW
  ├── All kept changes are standard git commits
  ├── Reviewable via normal PR workflow
  └── Cherry-pick or squash at team's discretion
```

### 8.2 What AutoOptim Cannot Break

- **Tests**: if tests don't pass as preflight, the mutation is discarded before evaluation
- **Interfaces**: blocked paths and allowed paths prevent changes to API surfaces
- **Production**: AutoOptim operates on a branch, never on main/production
- **Budget**: hard cost limits prevent runaway API spend

---

## 9. Comparison with Existing Approaches

| Approach | Scope | Automation | Feedback Loop | Code Changes |
|----------|-------|-----------|---------------|-------------|
| **Manual optimization** | Unlimited | None | Manual benchmarking | Manual |
| **Profiler-guided** (cProfile, pprof) | Performance | Measurement only | Dev interprets results | Manual |
| **Hyperparameter tuning** (Optuna, Ray Tune) | Numeric params | Full | Automated | No — only numbers |
| **AI Code Assistants** (Copilot, Claude) | Code | Suggestion only | None — single-shot | Suggested, not measured |
| **AutoOptim** | **Code + Config + Prompts** | **Full** | **Closed-loop, iterative** | **Automatic, measured, safe** |

### Why AutoOptim Is Fundamentally Different

1. **Closed loop**: The LLM sees whether its previous suggestions worked. It learns within the session.
2. **Measurement-driven**: Every change is evaluated against quantitative metrics. No guessing.
3. **Code-level, not parameter-level**: Optuna tunes numbers. AutoOptim rewrites functions, restructures configs, edits prompts.
4. **Multi-domain**: The same framework handles performance, quality, cost, and AI optimization.
5. **Safe by default**: Git rollback, preflight checks, and path restrictions make it safe to run unattended.

---

## 10. Roadmap

### Near-term

- **Parallel experiment execution**: Run multiple experiments on separate git worktrees simultaneously
- **Rich experiment viewer**: HTML report with score trends, diffs, and hypothesis analysis
- **More built-in evaluators**: Direct integration with pytest-benchmark, Go benchmark, JMH

### Medium-term

- **Multi-objective Pareto optimization**: Instead of a single composite, explore the Pareto frontier between competing objectives (speed vs. memory, quality vs. cost)
- **Cross-project learning**: Share experiment histories across projects to warm-start the proposer
- **CI/CD plugins**: First-class integrations for GitHub Actions, GitLab CI, Jenkins

### Long-term

- **Community recipe marketplace**: Share and discover optimization configs for common frameworks (Django, FastAPI, Next.js, Spring Boot)
- **Autonomous continuous optimization**: Run as a daemon that monitors production metrics and proposes improvements when regressions are detected
- **Multi-agent proposer**: Specialized LLM agents for different categories (performance expert, code quality expert, cost expert) that collaborate on proposals

---

## 11. Getting Started

### Installation

```bash
pip install autooptim
```

### Your First Optimization

1. **Create a config file** (`optimize.yaml`):

```yaml
name: my-first-optimization
project_root: "."

categories:
  code:
    mutator:
      type: code
      allowed_paths: ["src/"]
      preflight: ["pytest tests/ -x -q"]
    context_files: ["src/main.py"]

evaluator:
  type: command
  command: "pytest tests/ --benchmark-json=/dev/stdout -q"
  quick_task: "quick"
  full_task: "full"

metric:
  scores:
    - { name: mean_time, type: lower_is_better }
    - { name: test_pass, range: [0, 1] }
  composite:
    quality:
      weight: 0.5
      components: { test_pass: 1.0 }
    efficiency:
      weight: 0.5
      type: ratio_to_baseline
      components: [mean_time]

runner:
  max_iterations: 10
  max_cost_usd: 5.0
```

2. **Run it:**

```bash
autooptim run --config optimize.yaml
```

3. **Review the results:**

```bash
git log --oneline  # see kept experiments
cat .autooptim/logs/run-*.tsv  # full experiment history
```

---

## 12. Conclusion

Software optimization has been a manual, artisanal craft. AutoOptim transforms it into an **automated, scientific, continuous process**. By combining LLM reasoning with automated measurement and safe experimentation, it enables development teams to:

- **Optimize faster** — 50 experiments overnight vs. 5 in a day manually
- **Optimize broader** — cover performance, quality, cost, and AI behavior with one tool
- **Optimize safer** — git rollback and preflight checks make every experiment risk-free
- **Optimize across languages** — one framework for Python, Go, Rust, TypeScript, Java, and beyond

The question is no longer "should we optimize?" but "what should we measure?" Once you have a metric, AutoOptim handles the rest.

---

*AutoOptim is open source. Contributions welcome.*
