---
name: code-review
description: Review code for bugs, security vulnerabilities, and improvements. Use when the user asks for code review, code analysis, or wants feedback on their code quality.
---

# Code Review Skill

This skill provides structured code review capabilities with focus on:
- Bug detection and prevention
- Security vulnerability identification
- Code quality and maintainability
- Best practices compliance

## Review Process

When reviewing code, follow this structured approach:

### 1. Initial Assessment

Start by understanding the code's purpose:
- What is the code trying to accomplish?
- What are the inputs and outputs?
- What are the dependencies?

### 2. Bug Analysis

Check for common bugs:
- Off-by-one errors
- Null pointer dereferences
- Resource leaks
- Race conditions
- Unhandled exceptions
- Incorrect error handling

### 3. Security Review

Identify security vulnerabilities:
- SQL injection
- XSS (Cross-Site Scripting)
- CSRF (Cross-Site Request Forgery)
- Insecure deserialization
- Sensitive data exposure
- Improper authentication/authorization

### 4. Code Quality

Evaluate code quality:
- Readability and naming conventions
- Function and class design
- Proper separation of concerns
- DRY (Don't Repeat Yourself) violations
- Complexity analysis

### 5. Best Practices

Check for best practices:
- Proper error handling
- Logging and monitoring
- Documentation and comments
- Test coverage considerations
- Performance implications

## Output Format

Structure your review as:

```markdown
## Code Review Summary

### Overview
[Brief description of code purpose]

### Critical Issues
[List of critical bugs or security issues]

### Improvements
[Suggested improvements for code quality]

### Positive Aspects
[What the code does well]

### Recommendations
[Actionable next steps]
```

## Language-Specific Guidelines

### Python
- Check for proper type hints
- Verify async/await usage
- Look for Pythonic patterns

### JavaScript/TypeScript
- Check for proper null/undefined handling
- Verify promise handling
- Look for memory leaks in event handlers

### General
- Verify proper error boundaries
- Check for proper logging
- Look for hardcoded values
