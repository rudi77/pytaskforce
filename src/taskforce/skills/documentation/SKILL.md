---
name: documentation
description: Create and improve technical documentation including API docs, README files, user guides, and code comments. Use when the user needs help writing or improving documentation.
---

# Documentation Skill

This skill helps create clear, comprehensive technical documentation including:
- README files
- API documentation
- User guides
- Code comments and docstrings
- Architecture documentation

## Documentation Types

### 1. README Files

A good README should include:

```markdown
# Project Name

Brief description of what the project does.

## Features

- Feature 1
- Feature 2
- Feature 3

## Installation

```bash
pip install project-name
```

## Quick Start

```python
from project import main
main.run()
```

## Documentation

Link to detailed documentation.

## Contributing

How to contribute to the project.

## License

Project license information.
```

### 2. API Documentation

For API endpoints, document:

```markdown
## Endpoint Name

**URL:** `/api/v1/resource`

**Method:** `POST`

**Description:** What this endpoint does.

### Request

**Headers:**
| Header | Required | Description |
|--------|----------|-------------|
| Authorization | Yes | Bearer token |
| Content-Type | Yes | application/json |

**Body:**
```json
{
  "field1": "string",
  "field2": 123
}
```

### Response

**Success (200):**
```json
{
  "id": "abc123",
  "status": "success"
}
```

**Error (400):**
```json
{
  "error": "Invalid request",
  "details": "field1 is required"
}
```
```

### 3. Code Documentation

For Python docstrings (Google style):

```python
def process_data(input_data: dict, validate: bool = True) -> dict:
    """Process input data and return results.

    This function takes raw input data, validates it (optionally),
    and returns processed results.

    Args:
        input_data: Dictionary containing raw data to process.
            Expected keys: 'name', 'value', 'timestamp'.
        validate: Whether to validate input before processing.
            Defaults to True.

    Returns:
        Dictionary with processed results containing:
        - 'processed_name': Cleaned name string
        - 'computed_value': Calculated value
        - 'processing_time': Time taken in ms

    Raises:
        ValueError: If input_data is missing required keys.
        ProcessingError: If processing fails.

    Example:
        >>> data = {'name': 'test', 'value': 42, 'timestamp': '2024-01-01'}
        >>> result = process_data(data)
        >>> print(result['computed_value'])
        84
    """
    pass
```

### 4. Architecture Documentation

Document system architecture with:

```markdown
# Architecture Overview

## System Components

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Client    │────▶│   API       │────▶│  Database   │
└─────────────┘     └─────────────┘     └─────────────┘
                          │
                          ▼
                    ┌─────────────┐
                    │   Cache     │
                    └─────────────┘
```

## Data Flow

1. Client sends request to API
2. API validates request
3. API checks cache
4. If not cached, query database
5. Return response

## Key Design Decisions

### Decision 1: Caching Strategy
**Context:** [Why this decision was needed]
**Decision:** [What was decided]
**Consequences:** [Impact of the decision]
```

## Best Practices

### Writing Style
- Use clear, concise language
- Avoid jargon unless necessary
- Define technical terms on first use
- Use active voice

### Structure
- Use consistent formatting
- Include a table of contents for long documents
- Group related information together
- Use code examples liberally

### Maintenance
- Keep documentation close to code
- Update docs with code changes
- Review documentation regularly
- Gather user feedback

## Templates

See the `templates/` directory for:
- `README_TEMPLATE.md` - Project README template
- `API_TEMPLATE.md` - API endpoint documentation
- `ARCHITECTURE.md` - Architecture decision record
