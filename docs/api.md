# REST API Guide

Taskforce includes a production-ready REST API built with **FastAPI**.

## 🚀 Starting the Server

Run the server using `uvicorn`:
```powershell
uvicorn taskforce.api.server:app --reload
```

## 📖 API Documentation

Once the server is running, you can access the interactive documentation at:

- **Swagger UI**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc**: [http://localhost:8000/redoc](http://localhost:8000/redoc)

## 🛣 Key Endpoints

### Execution
- `POST /api/v1/execution/execute`: Run a mission synchronously.
- `POST /api/v1/execution/execute/stream`: Run a mission with real-time SSE progress updates.

### Sessions
- `GET /api/v1/sessions`: List all active sessions.
- `GET /api/v1/sessions/{session_id}`: Retrieve full state for a specific session.

### System
- `GET /health`: Basic liveness check.

## 🔧 Integration Example

```python
import requests

response = requests.post(
    "http://localhost:8000/api/v1/execution/execute",
    json={
        "mission": "Write a hello world in Rust",
        "profile": "dev"
    }
)
print(response.json()["result"])
```

