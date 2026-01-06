# Examples & Tutorials

Taskforce includes several example agents to help you get started with different use cases.

## 📂 Example Agents

You can find complete, runnable examples in the `examples/` directory:

- **[Accounting Agent](https://github.com/rudi77/pytaskforce/tree/main/examples/accounting_agent)**: German accounting agent with invoice validation, compliance checking (§14 UStG), and booking proposals.
- **[Customer Support Agent](https://github.com/rudi77/pytaskforce/tree/main/examples/customer_support_agent)**: An example of an interactive support bot.

### Loading Example Plugins

Example agents can be loaded directly as plugins:

```powershell
# Load the accounting agent as a plugin
taskforce chat --plugin examples/accounting_agent
```

This dynamically loads all tools from the plugin and makes them available to the agent. See the **[Plugin Development Guide](plugins.md)** for creating your own plugins.

## 🎓 Tutorials

- **[Custom Tool Tutorial](https://github.com/rudi77/pytaskforce/blob/main/examples/custom-tool-and-profile-tutorial.ipynb)**: A Jupyter notebook walking through how to create your own tools and configuration profiles.

## 💡 Common Use Cases

### 1. File Analysis
Run the agent to analyze local source code or data files using the `file_read` and `python` tools.

### 2. RAG (Retrieval Augmented Generation)
Configure a profile with the `rag_agent` type to enable semantic search across your document library.

---
*See [examples/README.md](../examples/README.md) for a full catalog of built-in demos.*

