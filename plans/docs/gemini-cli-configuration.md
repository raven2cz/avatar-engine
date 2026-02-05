# Gemini CLI Configuration Documentation

> Source: https://github.com/google-gemini/gemini-cli/blob/main/docs/get-started/configuration.md

## Configuration Hierarchy

Settings apply in this order (highest precedence last):
1. Default hardcoded values
2. System defaults file
3. User settings file
4. Project settings file
5. System settings file
6. Environment variables
7. Command-line arguments

## Settings File Locations

- **User**: `~/.gemini/settings.json`
- **Project**: `.gemini/settings.json`
- **System defaults**: `/etc/gemini-cli/system-defaults.json` (Linux), `C:\ProgramData\gemini-cli\system-defaults.json` (Windows), `/Library/Application Support/GeminiCli/system-defaults.json` (macOS)
- **System overrides**: Same paths with `settings.json` instead

Environment variables in settings use `$VAR_NAME` or `${VAR_NAME}` syntax for automatic resolution.

## Major Configuration Categories

### General
- `previewFeatures`: Enable preview features (default: false)
- `preferredEditor`: Specify editor for opening files
- `vimMode`: Enable Vim keybindings (default: false)
- `enableAutoUpdate`: Allow automatic updates (default: true)
- `enablePromptCompletion`: AI-powered prompt suggestions (default: false)
- `checkpointing.enabled`: Session recovery (default: false, requires restart)
- `sessionRetention`: Configure automatic cleanup with `maxAge` (e.g., "30d", "7d"), `maxCount`, or `minRetention`

### UI
- `theme`: Color theme selection
- `autoThemeSwitching`: Switch light/dark based on terminal (default: true)
- `terminalBackgroundPollingInterval`: Check frequency in seconds (default: 60)
- `customThemes`: Define custom color schemes
- `hideWindowTitle`, `hideBanner`, `hideFooter`, `hideContextSummary`: Toggle UI elements
- `showStatusInTitle`: Display model thoughts in window title (default: false)
- `dynamicWindowTitle`: Show status icons (default: true)
- `useAlternateBuffer`: Preserve shell history (default: false, requires restart)
- `incrementalRendering`: Reduce flickering (default: true, requires restart)
- `accessibility.screenReader`: Plain-text output for accessibility (default: false, requires restart)

### Output
- `format`: Choose "text" or "json" (default: "text")

### IDE
- `enabled`: Enable IDE integration mode (default: false, requires restart)
- `hasSeenNudge`: Track nudge display status

### Privacy
- `usageStatisticsEnabled`: Collect usage data (default: true, requires restart)

## Model Configuration

### Core Model Settings

**`model.name`**: Specify Gemini model for conversations

**`model.maxSessionTurns`**: Maximum turns to retain (-1 = unlimited, default: -1)

**`model.summarizeToolOutput`**: Enable tool output summarization with per-tool token budgets

**`model.compressionThreshold`**: Trigger context compression at fraction usage (e.g., 0.2, 0.3; default: 0.5)

**`model.disableLoopDetection`**: Disable infinite loop prevention (default: false)

### Model Aliases

**`modelConfigs.aliases`**: Named presets supporting inheritance via "extends" property

Example alias structure:
```json
{
  "base": {
    "modelConfig": {
      "generateContentConfig": {
        "temperature": 0,
        "topP": 1
      }
    }
  },
  "gemini-2.5-pro": {
    "extends": "chat-base-2.5",
    "modelConfig": { "model": "gemini-2.5-pro" }
  }
}
```

**`modelConfigs.customAliases`**: User-defined presets merged with built-ins

**`modelConfigs.overrides`**: Apply configurations based on model matches

### Generation Configuration

**`generateContentConfig`** includes:
- `temperature`: Randomness control (0 = deterministic, 1.0 = default)
- `topP`, `topK`: Sampling parameters
- `maxOutputTokens`: Response length limit
- `thinkingConfig`: Extended thinking options
  - `includeThoughts`: Show reasoning (boolean)
  - `thinkingBudget`: Token allocation for thinking (Gemini 2.5)
  - `thinkingLevel`: Set to "HIGH", "LOW", "MINIMAL", "MEDIUM" (Gemini 3)

### Built-in Model Aliases

- `gemini-3-pro-preview`
- `gemini-3-flash-preview`
- `gemini-2.5-pro`
- `gemini-2.5-flash`
- `gemini-2.5-flash-lite`
- `classifier`
- `prompt-completion`
- `summarizer-default`
- `web-search`
- `web-fetch`

## Example: Full settings.json

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
            "temperature": 0.7,
            "topP": 0.95,
            "topK": 64,
            "maxOutputTokens": 8192,
            "thinkingConfig": {
              "includeThoughts": false,
              "thinkingLevel": "HIGH"
            }
          }
        }
      }
    }
  },
  "mcpServers": {
    "my-server": {
      "command": "python",
      "args": ["mcp_server.py"]
    }
  }
}
```

## Tools & Context

- `tools`: Configure available tools and capabilities
- `mcp`: Model Context Protocol settings
- `mcpServers`: MCP server configurations
- `context`: Context file settings

## Advanced Features

- `security`: Security-related configurations
- `experimental`: Beta features
- `skills`: Custom skill definitions
- `hooksConfig`, `hooks`: Lifecycle hook definitions
- `admin`: Administrative settings
- `telemetry`: Data collection preferences
