# Gemini CLI Headless Mode Documentation

> Source: https://geminicli.com/docs/cli/headless

## Overview

Headless mode enables programmatic execution of Gemini CLI without interactive UI. The feature supports command-line scripting, automation, CI/CD pipelines, and AI-powered tool development.

## Basic Usage

### Input Methods

**Direct prompts via flag:**
```bash
gemini --prompt "What is machine learning?"
# or short form
gemini -p "What is machine learning?"
```

**Standard input piping:**
```bash
echo "Explain this code" | gemini
```

**File combination:**
```bash
cat README.md | gemini --prompt "Summarize this documentation"
```

## Output Formats

### Text Output (Default)

Standard human-readable responses without structured metadata.

```bash
gemini -p "What is the capital of France?"
```

### JSON Output

Returns comprehensive structured data including response content, usage statistics, and error information.

```bash
gemini -p "What is the capital of France?" --output-format json
```

**Response schema includes:**
- `response`: Main AI-generated answer
- `stats.models`: Per-model API requests, token counts, and latency metrics
- `stats.tools`: Tool execution statistics with success/failure tracking
- `stats.files`: Code modification counts
- `error`: Present only when failures occur

### Stream-JSON (Streaming Output)

Emits newline-delimited JSON events in real-time. Ideal for monitoring long-running operations and building live dashboards.

```bash
gemini --output-format stream-json --prompt "Analyze this code" > events.jsonl
```

**Event types:**
1. `init` — Session initialization with session ID and model
2. `message` — User prompts and assistant responses
3. `tool_use` — Tool invocation requests
4. `tool_result` — Tool execution outcomes
5. `error` — Non-fatal warnings and errors
6. `result` — Final aggregated statistics

Each line represents a complete JSON event with timestamp.

## Command-Line Flags

| Flag | Purpose | Example |
|------|---------|---------|
| `--prompt` / `-p` | Headless mode activation | `gemini -p "query"` |
| `--output-format` | Format selection (text, json, stream-json) | `--output-format json` |
| `--model` / `-m` | Model specification | `-m gemini-3-pro-preview` |
| `--debug` / `-d` | Debug mode activation | `--debug` |
| `--yolo` / `-y` | Auto-approve actions | `-y` |
| `--approval-mode` | Approval strategy | `--approval-mode auto_edit` |
| `--include-directories` | Additional directory inclusion | `--include-directories src,docs` |

## Practical Examples

**Security review:**
```bash
cat src/auth.py | gemini -p "Review for security issues" > review.txt
```

**Batch processing:**
```bash
for file in src/*.py; do
  cat "$file" | gemini -p "Find bugs" --output-format json > "reports/$(basename "$file").json"
done
```

**Piping with JSON processing:**
```bash
result=$(gemini -p "Generate OpenAPI spec" --output-format json)
echo "$result" | jq -r '.response'
```

**Usage tracking:**
```bash
result=$(gemini -p "Explain schema" --output-format json)
tokens=$(echo "$result" | jq '.stats.models | to_entries | map(.value.tokens.total) | add')
echo "Tokens used: $tokens"
```

## File Redirection

```bash
# Redirect to file
gemini -p "Explain Docker" > output.txt

# JSON to file
gemini -p "Query" --output-format json > data.json

# Append
gemini -p "Additional info" >> output.txt

# Pipe to tools
gemini -p "List languages" | grep -i "python"
```

## ACP Mode (Agent Client Protocol)

For persistent warm sessions, use `--experimental-acp`:

```bash
gemini --experimental-acp --yolo --model gemini-3-pro-preview
```

This spawns a persistent process that accepts JSON-RPC messages for:
- `initialize` — Protocol version negotiation
- `authenticate` — OAuth or API key authentication
- `new_session` — Create session with MCP servers
- `prompt` — Send user messages and receive streaming responses

See [ACP documentation](./acp-python-sdk.md) for SDK usage.
