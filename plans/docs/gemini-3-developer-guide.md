# Gemini 3 Developer Guide

> Source: https://ai.google.dev/gemini-api/docs/gemini-3

## Model Overview

Gemini 3 is Google's latest AI model family for advanced reasoning, autonomous coding, and complex multimodal tasks.

## Models

| Model | Context Window | Knowledge Cutoff | Pricing (per 1M tokens) |
|-------|----------------|------------------|-------------------------|
| Gemini 3 Pro | 1M input / 64k output | Jan 2025 | $2 input / $12 output |
| Gemini 3 Flash | 1M input / 64k output | Jan 2025 | $0.50 input / $3 output |

## Key API Parameters

### Thinking Level

**Replaces `thinking_budget` from Gemini 2.5.** Controls maximum reasoning depth:

| Level | Description |
|-------|-------------|
| `minimal` | Closest to disabled (Flash only can fully disable) |
| `low` | Minimizes latency for simple tasks |
| `medium` | Balanced (Flash only) |
| `high` | **Default** — Maximizes reasoning for complex problems |

**Important:** You cannot disable thinking for Gemini 3 Pro. Use `minimal` or `low` for faster responses.

### Configuration Example

```python
from google.generativeai import types

config = types.GenerateContentConfig(
    thinking_config=types.ThinkingConfig(
        thinking_level="low",  # or "high", "minimal", "medium"
        include_thoughts=False  # Don't show thinking in output
    ),
    temperature=1.0,  # Keep default for best results
    max_output_tokens=8192
)
```

### Temperature

**Recommendation:** Keep default value of 1.0. Lower settings may cause unexpected behavior or performance degradation on complex reasoning tasks.

### Media Resolution

Controls vision processing via `media_resolution` parameter:

| Content Type | Recommended Setting |
|--------------|---------------------|
| Images | `high` |
| PDFs | `medium` |
| Video | `low` |

### Thought Signatures

Encrypted representations maintaining reasoning context across API calls:
- **Required** for function calling and image generation/editing
- **Recommended** for text/chat workflows

## Gemini CLI Settings

Configure in `.gemini/settings.json`:

```json
{
  "model": {
    "name": "gemini-3-pro-preview"
  },
  "modelConfigs": {
    "customAliases": {
      "gemini-3-pro-preview": {
        "modelConfig": {
          "generateContentConfig": {
            "temperature": 1.0,
            "thinkingConfig": {
              "thinkingLevel": "HIGH",
              "includeThoughts": false
            }
          }
        }
      }
    }
  }
}
```

## Core Capabilities

- **Text generation** with advanced reasoning
- **Image generation and editing** with grounding via Google Search
- **Video and audio understanding**
- **Code execution** with visual inspection
- **Multimodal function responses** combining text and media
- **Structured outputs** with built-in tools

## Built-in Tools

- Google Search
- URL Context
- Code Execution
- File Search

## Migration from Gemini 2.5

Key changes:
1. Use `thinking_level` instead of `thinking_budget`
2. Remove explicit temperature adjustments (keep default 1.0)
3. Test new PDF resolution defaults
4. Monitor token consumption changes

**Not yet supported:**
- Image segmentation
- Maps grounding

## Prompting Best Practices

- Use precise, concise instructions
- Gemini 3 prefers direct requests over verbose prompt engineering
- Place specific questions after data context for better grounding

## Regional Requirements

Gemini 3 Pro is only available in the **global** location.

For Vertex AI users:
```bash
export GOOGLE_CLOUD_LOCATION="global"
```

## Rate Limits

- Ultra subscribers: 2,000 requests per day
- API key users: Standard quotas apply

## Availability

**Immediate access:**
- Google AI Ultra subscribers (non-business)
- Users with paid Gemini API keys

**Coming soon:**
- Gemini Code Assist Enterprise users

**Waitlist:**
- Google AI Pro, Gemini Code Assist Standard, individual plans
