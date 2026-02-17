# Changelog

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
