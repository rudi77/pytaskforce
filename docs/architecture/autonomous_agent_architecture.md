# Architektur-Design: Der Autonome, Profil-basierte Agent

## 1. Das Konzept: Kernel vs. Profil

Anstatt monolithische Agenten zu bauen, verwenden wir eine Schichtenarchitektur.

  * **Layer 1: Der Autonome Kernel (The Brain)**

      * Definiert das *Verhalten*: "Ich arbeite iterativ.", "Ich korrigiere meine Fehler.", "Ich entscheide, wann ich fertig bin."
      * Ist agnostisch gegenüber der Aufgabe (egal ob Coding oder Research).
      * Zwingt den Agenten in den "Self-Correction Loop".

  * **Layer 2: Das Spezialisten-Profil (The Hat)**

      * Definiert die *Fähigkeiten*: "Ich bin ein Senior Developer.", "Ich nutze `pytest`.", "Ich lese Files bevor ich schreibe."
      * Enthält spezifische Tools und Best Practices für die Domain.

-----

## 2. Die System-Prompts

### A. Der Kernel-Prompt (Das "Betriebssystem")

Dieser Prompt wird *jedem* Agenten vorangestellt. Er überschreibt das Standardverhalten von LLMs (die gerne plaudern) mit dem Verhalten eines autonomen Workers.

```python
GENERAL_AUTONOMOUS_KERNEL_PROMPT = """
# Autonomous Agent Kernel - System Instructions

## Core Identity
You are an advanced, autonomous AI agent capable of solving complex problems by executing tasks step-by-step.
You do not rely on the user to guide your every move. You act, observe, and correct yourself.

## The Execution Protocol (CRITICAL)

You operate in a loop processing a single Task (TodoItem). Your goal is to fulfill the acceptance criteria of this *current task* completely before moving on.

1.  **Iterative Execution (The Loop)**:
    * A task is rarely solved with one single tool call.
    * You typically need to: **Gather Context** -> **Plan Action** -> **Execute** -> **Verify/Test**.
    * You must perform as many cycles as necessary within the current task.

2.  **The "Definition of Done"**:
    * The system does NOT automatically mark a task as complete just because a tool ran successfully.
    * **YOU** decide when the task is finished.
    * Use the action **`FINISH_STEP`** only when you have verified that the acceptance criteria are met.
    * If you run a tool and it works, but you haven't verified the result (e.g., via test or read), you are NOT done.

3.  **Self-Healing & Error Handling**:
    * If a tool fails or returns an error: **DO NOT STOP. DO NOT APOLOGIZE.**
    * Analyze the error message.
    * Formulate a hypothesis why it failed.
    * Try a different parameter, a different tool, or fix the underlying issue (e.g., create a missing file).
    * Only ask the user for help (`ASK_USER`) if you are truly blocked (e.g., missing credentials).

## Action Interface

You have access to a set of tools. Choose the most specific tool for the job.
* **`TOOL_CALL`**: To execute an action (read, write, search, run command, etc.).
* **`FINISH_STEP`**: To declare the current task successfully completed.
* **`ASK_USER`**: To pause and request essential missing information.
* **`REPLAN`**: If the current task is impossible or the plan needs structural changes.
"""
```

### B. Das Coding-Profil (Der "Spezialist")

Dieser Prompt wird angehängt, wenn der Agent als Coder agieren soll.

```python
CODING_SPECIALIST_PROMPT = """
## Specialization: Senior Software Engineer

You are specialized in Software Engineering. You behave like a Senior Developer working via a Command Line Interface (CLI).

### Domain Guidelines
1.  **Act, Don't Speak**: Do not dump code blocks in the chat unless explicitly asked to "explain". Use `file_write` to create actual files on the disk.
2.  **Verification First**: Never assume code works. After writing code, use `powershell` (or bash) to run linters, type checks, or test scripts.
3.  **Context Awareness**: Before editing existing files, ALWAYS use `file_read` to understand imports and class structures.
4.  **Refactoring**: If you encounter messy code while working on a task, you are expected to clean it up.

### Recommended Workflow for Coding Tasks
1.  **Explore**: `ls -R` to see the project structure.
2.  **Read**: `file_read` relevant files.
3.  **Edit**: `file_write` to apply changes (always write full file content).
4.  **Test**: `powershell` -> `pytest` or `python script.py`.
5.  **Fix**: If Test fails -> Repeat Step 2-4 immediately.
6.  **Finish**: Call `FINISH_STEP` only when tests pass.
"""
```

-----

## 3. Code-Implementierung (Infrastructure)

Damit der Agent diesen Prompts folgen kann, muss der Code die Logik unterstützen.

### Schritt 1: `events.py` (Neue Action)

```python
class ActionType(str, Enum):
    TOOL_CALL = "tool_call"
    ASK_USER = "ask_user"
    COMPLETE = "complete" # Mission complete
    REPLAN = "replan"
    FINISH_STEP = "finish_step" # <--- NEU: Step complete
```

### Schritt 2: `agent.py` (Die Logik-Änderung)

Wir ändern `_process_observation`, damit der Agent **im Loop bleibt**, bis er explizit `FINISH_STEP` sendet.

```python
    async def _process_observation(
        self,
        action: Action,
        observation: Observation,
        current_step: TodoItem,
        # ... args ...
    ) -> None:
        
        # 1. Agent meldet explizit: "Ich bin fertig mit diesem Schritt"
        if action.type == ActionType.FINISH_STEP:
            current_step.status = TaskStatus.COMPLETED
            self.logger.info("step_completed_explicitly_by_agent", step=current_step.position)
            # Optional: Ergebnis speichern
            current_step.execution_result = {"status": "completed_by_agent"}

        # 2. Tool war erfolgreich -> Agent ist NICHT fertig, sondern arbeitet weiter
        elif observation.success:
            current_step.status = TaskStatus.PENDING # Bleibt im Loop!
            
            # WICHTIG: Wir setzen den Counter zurück, damit er unendlich oft 
            # "Read -> Write -> Test" machen kann, solange die Tools funktionieren.
            current_step.attempts = 0 
            
            self.logger.info("tool_success_continuing_iteration", step=current_step.position)

        # 3. Tool ist fehlgeschlagen -> Fehler zählen
        else:
            current_step.status = TaskStatus.PENDING
            # Hier erhöhen wir attempts (passiert implizit im Caller oder hier),
            # damit wir bei endlosen Fehlern irgendwann ins Replanning gehen.
            self.logger.warning("tool_failed_retrying", step=current_step.position)

        # ... Persist logic ...
```

### Schritt 3: Die Agent Factory (Zusammenbau)

Hier bauen wir den Agenten dynamisch zusammen.

```python
class AgentFactory:
    def create_agent(self, profile: str = "generic", session_id: str) -> Agent:
        
        # 1. Basis-Prompt laden
        system_prompt = GENERAL_AUTONOMOUS_KERNEL_PROMPT
        
        # 2. Profil-spezifische Erweiterungen
        tools = []
        
        if profile == "coding":
            system_prompt += "\n\n" + CODING_SPECIALIST_PROMPT
            tools = [
                FileReadTool(), 
                FileWriteTool(), 
                PowerShellTool(), 
                AskUserTool() # Immer dabei
            ]
        elif profile == "rag":
            system_prompt += "\n\n" + RAG_SPECIALIST_PROMPT
            tools = [
                RagSemanticSearchTool(), 
                RagListDocumentsTool(), 
                RagGetDocumentTool(), 
                AskUserTool()
            ]
            
        # 3. Agent instanziieren
        return Agent(
            system_prompt=system_prompt,
            tools=tools,
            # ... dependencies ...
        )
```

-----

## 4. Beispielszenario: Wie der neue Agent arbeitet

**Mission:** "Erstelle eine `utils.py` mit einer Fibonacci-Funktion und teste sie."

**Plan (Planner):**

1.  `Create and implement utils.py` (PENDING)
2.  `Verify implementation with tests` (PENDING)

**Execution (Agent):**

  * **Iteration 1 (Step 1):**

      * *Thought:* "Ich muss `utils.py` erstellen."
      * *Action:* `file_write("utils.py", "def fib(n)...")`
      * *Observation:* Success.
      * *State:* Step 1 bleibt **PENDING**. (Früher wäre hier Step 1 fertig gewesen!)

  * **Iteration 2 (Step 1):**

      * *Thought:* "Datei ist erstellt. Ich sollte kurz prüfen, ob sie da ist."
      * *Action:* `powershell("ls utils.py")`
      * *Observation:* Success.
      * *State:* Step 1 bleibt **PENDING**.

  * **Iteration 3 (Step 1):**

      * *Thought:* "Alles sieht gut aus. Der Schritt ist erledigt."
      * *Action:* `FINISH_STEP`
      * *State:* Step 1 wird **COMPLETED**. Agent geht zu Step 2.

  * **Iteration 4 (Step 2):**

      * *Thought:* "Ich muss testen. Ich erstelle ein Testskript."
      * *Action:* `file_write("test_utils.py", "import utils...")`
      * *Observation:* Success.

  * **Iteration 5 (Step 2):**

      * *Thought:* "Jetzt führe ich den Test aus."
      * *Action:* `powershell("python test_utils.py")`
      * *Observation:* **Failed** (Syntax Error in `utils.py`).
      * *State:* Step 2 bleibt **PENDING**.

  * **Iteration 6 (Step 2 - Self Healing):**

      * *Thought:* "Verdammt, Syntaxfehler. Ich muss `utils.py` lesen und korrigieren."
      * *Action:* `file_read("utils.py")`... und danach `file_write` (Fix).

Dies ist der fundamentale Unterschied. Der Agent "lebt" in der Aufgabe, bis er zufrieden ist.

Möchtest du, dass wir den Code für die `AgentFactory` oder die Anpassung der `_process_observation` konkret umsetzen?

