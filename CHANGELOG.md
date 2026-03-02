# Changelog

## [1.2.0] - 2026-03-02

### Added
- **Dynamic Model Discovery** — web scraping of provider documentation pages to keep model lists up-to-date without API keys
  - Strategy pattern with `ModelParser` ABC — extensible per-provider parsers
  - `ParserRegistry` with factory + discovery pattern
  - Three parsers: `ClaudeParser`, `GeminiParser`, `CodexParser`
  - In-memory cache with configurable TTL (default 24h)
  - Concurrent fetching via `asyncio.gather()` for fast startup
  - `GET /api/avatar/models` REST endpoint with `?refresh=true` support
  - 41 unit tests + 10 live canary tests against real documentation URLs
- **Claude `additional_dirs`** — grant Claude Code access to directories beyond working_dir
  - `additional_dirs` parameter in ClaudeBridge constructor and YAML config
  - Generates `--add-dir` CLI flags and `additionalDirectories` in settings JSON
- **React hooks for dynamic models**:
  - `useDynamicModels` — three-tier fallback: static → localStorage cache → backend scraping
  - `useModelDiscoveryErrors` — listener for model discovery error events

### Changed
- Model discovery fetches run in parallel (`asyncio.gather`) to prevent browser connection stalling

## [1.1.0] - 2026-02-28

### Added
- **Context metadata** — attach key-value metadata to chat messages for domain context
- **`createProviders()` factory** — programmatic model overrides for frontend provider configs
- **`initialMode` prop** — set initial widget mode (fab / compact / fullscreen)

### Fixed
- Session manager ignoring explicit provider on switch/resume
- i18n singleton coexistence with consumer apps (namespace isolation)
- Fullscreen background transparency
- Avatar selection sync from external changes (Settings page)
- Session manager `config_path` fix

## [1.0.0] - 2026-02-15

### Added
- Three-provider AI avatar runtime (Gemini CLI, Claude Code, Codex CLI)
- Event-driven architecture with streaming support
- ACP protocol integration for Gemini and Codex bridges
- Session management (persist, resume, list)
- Web server with REST API + WebSocket
- `@avatar-engine/core` npm package:
  - Framework-agnostic WebSocket protocol and state machine
  - AvatarClient class for any UI framework
  - TypeScript types for all server/client messages
  - Provider and avatar configuration
  - i18n support (English, Czech)
- `@avatar-engine/react` npm package:
  - AvatarWidget (FAB / compact / fullscreen modes)
  - Chat UI with markdown and syntax highlighting
  - Provider/model selector with dynamic options
  - Three-mode safety (Safe / Ask / Unrestricted)
  - ACP permission dialog
  - Session management panel
  - Avatar bust with state-driven animations
  - Tailwind preset for theming
- CLI interface (`avatar` command)
- YAML configuration support
- MCP server integration
- File upload support
- CI/CD pipeline (GitHub Actions)
