/**
 * TypeScript types mirroring avatar_engine/events.py + web/protocol.py
 */

/** Current state of the AI engine's processing pipeline. */
export type EngineState = 'idle' | 'thinking' | 'responding' | 'tool_executing' | 'waiting_approval' | 'error'

/** Categorizes what the AI model is currently reasoning about. */
export type ThinkingPhase = 'general' | 'analyzing' | 'planning' | 'coding' | 'reviewing' | 'tool_planning'

/** Lifecycle status of a tracked activity (tool call, sub-task, etc.). */
export type ActivityStatus = 'pending' | 'running' | 'completed' | 'failed' | 'cancelled'

/** WebSocket bridge connection state as seen by the client. */
export type BridgeState = 'disconnected' | 'warming_up' | 'ready' | 'busy' | 'error'

/**
 * Provider feature support flags, received on WebSocket connection.
 * @property can_list_sessions - Whether the provider supports listing saved sessions.
 * @property can_load_session - Whether the provider supports loading a specific session by ID.
 * @property can_continue_last - Whether the provider can resume the most recent session.
 * @property thinking_supported - Whether the provider emits thinking/reasoning tokens.
 * @property thinking_structured - Whether thinking tokens include structured phase metadata.
 * @property cost_tracking - Whether the provider reports per-request cost data.
 * @property budget_enforcement - Whether the provider can enforce spending limits.
 * @property system_prompt_method - How the provider injects system prompts (e.g. "system", "developer").
 * @property streaming - Whether the provider supports streaming responses.
 * @property parallel_tools - Whether the provider can execute multiple tool calls concurrently.
 * @property cancellable - Whether in-flight requests can be cancelled.
 * @property mcp_supported - Whether the provider supports MCP (Model Context Protocol) tools.
 */
export interface ProviderCapabilities {
  can_list_sessions: boolean
  can_load_session: boolean
  can_continue_last: boolean
  thinking_supported: boolean
  thinking_structured: boolean
  cost_tracking: boolean
  budget_enforcement: boolean
  system_prompt_method: string
  streaming: boolean
  parallel_tools: boolean
  cancellable: boolean
  mcp_supported: boolean
}

/** Three-tier safety mode controlling tool execution permissions. */
export type SafetyMode = 'safe' | 'ask' | 'unrestricted'

// === Server → Client messages ===

/** Sent once after WebSocket handshake; carries session metadata and provider capabilities. */
export interface ConnectedMessage {
  type: 'connected'
  data: {
    session_id: string | null
    provider: string
    model: string | null
    version: string
    capabilities: ProviderCapabilities
    engine_state: EngineState
    cwd?: string
    session_title?: string
    safety_mode?: SafetyMode
  }
}

/** Streamed text chunk from the AI model's response. */
export interface TextMessage {
  type: 'text'
  data: {
    text: string
    is_complete: boolean
    timestamp: number
    provider: string
  }
}

/** Streamed thinking/reasoning token from the AI model. */
export interface ThinkingMessage {
  type: 'thinking'
  data: {
    thought: string
    phase: ThinkingPhase
    subject: string
    is_start: boolean
    is_complete: boolean
    block_id: string
    token_count: number
    category: string
    timestamp: number
    provider: string
  }
}

/** Emitted when a tool call starts, completes, or fails. */
export interface ToolMessage {
  type: 'tool'
  data: {
    tool_name: string
    tool_id: string
    parameters: Record<string, unknown>
    status: 'started' | 'completed' | 'failed'
    result: string | null
    error: string | null
    timestamp: number
    provider: string
  }
}

/** Emitted when the WebSocket bridge transitions between connection states. */
export interface StateMessage {
  type: 'state'
  data: {
    old_state: BridgeState | null
    new_state: BridgeState | null
    detail?: string
    timestamp: number
    provider: string
  }
}

/** Lightweight notification that the engine's processing state has changed. */
export interface EngineStateMessage {
  type: 'engine_state'
  data: {
    state: EngineState
  }
}

/** Per-request cost and token usage report. */
export interface CostMessage {
  type: 'cost'
  data: {
    cost_usd: number
    input_tokens: number
    output_tokens: number
    timestamp: number
    provider: string
  }
}

/** Sent when the server encounters an error during processing. */
export interface ErrorMessage {
  type: 'error'
  data: {
    error: string
    recoverable?: boolean
    timestamp?: number
    provider?: string
  }
}

/** Internal diagnostic/log message forwarded from the engine for debugging. */
export interface DiagnosticMessage {
  type: 'diagnostic'
  data: {
    message: string
    level: string
    source: string
    timestamp: number
    provider: string
  }
}

/** Progress update for a tracked activity (tool execution, sub-task, etc.). */
export interface ActivityMessage {
  type: 'activity'
  data: {
    activity_id: string
    parent_activity_id: string
    activity_type: string
    name: string
    status: ActivityStatus
    progress: number
    detail: string
    concurrent_group: string
    is_cancellable: boolean
    started_at: number
    completed_at: number
    timestamp: number
    provider: string
  }
}

/** An image generated during the AI response. */
export interface GeneratedImage {
  url: string
  filename: string
}

/** Final summary sent after the AI finishes responding to a chat request. */
export interface ChatResponseMessage {
  type: 'chat_response'
  data: {
    content: string
    success: boolean
    error: string | null
    duration_ms: number
    session_id: string | null
    cost_usd: number | null
    tool_calls: unknown[]
    images?: GeneratedImage[]
  }
}

/** Response to a client ping; used for latency measurement and keep-alive. */
export interface PongMessage {
  type: 'pong'
  data: { ts: number }
}

/** Confirms that conversation history has been cleared. */
export interface HistoryClearedMessage {
  type: 'history_cleared'
  data: Record<string, never>
}

/** Sent while the engine/provider is still initializing (e.g. loading models). */
export interface InitializingMessage {
  type: 'initializing'
  data: {
    provider: string
    detail: string
  }
}

/** Notifies the client that a session's title was auto-generated or updated. */
export interface SessionTitleUpdatedMessage {
  type: 'session_title_updated'
  data: {
    session_id: string
    title: string | null
    is_current_session?: boolean
  }
}

/** Sent when the engine requires user approval before executing a tool (ask/safe mode). */
export interface PermissionRequestMessage {
  type: 'permission_request'
  data: {
    request_id: string
    tool_name: string
    tool_input: string
    options: Array<{ option_id: string; kind: string }>
    timestamp: number
    provider: string
  }
}

/** Discriminated union of all messages the server can send to the client. */
export type ServerMessage =
  | ConnectedMessage
  | TextMessage
  | ThinkingMessage
  | ToolMessage
  | StateMessage
  | EngineStateMessage
  | CostMessage
  | ErrorMessage
  | DiagnosticMessage
  | ActivityMessage
  | ChatResponseMessage
  | PongMessage
  | HistoryClearedMessage
  | InitializingMessage
  | SessionTitleUpdatedMessage
  | PermissionRequestMessage

// === Client → Server messages ===

/**
 * Metadata for a file uploaded by the user, used on the client side.
 * @property fileId - Unique identifier assigned after upload.
 * @property filename - Original file name.
 * @property mimeType - MIME type of the uploaded file.
 * @property size - File size in bytes.
 * @property path - Server-side path where the file is stored.
 * @property previewUrl - Optional data URL or blob URL for client-side preview.
 */
export interface UploadedFile {
  fileId: string
  filename: string
  mimeType: string
  size: number
  path: string
  previewUrl?: string
}

/** Wire format for a file attachment sent with a chat request. */
export interface ChatAttachment {
  file_id: string
  filename: string
  mime_type: string
  path: string
}

/** Sends a user message (with optional attachments and context metadata) to the AI engine. */
export interface ChatRequest {
  type: 'chat'
  data: { message: string; attachments?: ChatAttachment[]; context?: Record<string, unknown> }
}

/** Requests cancellation of the current AI response. */
export interface StopRequest {
  type: 'stop'
  data: Record<string, never>
}

/** Keep-alive ping; the server replies with a PongMessage. */
export interface PingRequest {
  type: 'ping'
  data: Record<string, never>
}

/** Requests the server to clear conversation history for the current session. */
export interface ClearHistoryRequest {
  type: 'clear_history'
  data: Record<string, never>
}

/** Requests switching to a different AI provider or model. */
export interface SwitchRequest {
  type: 'switch'
  data: { provider: string; model?: string; options?: Record<string, unknown> }
}

/** Requests resuming an existing session by its ID. */
export interface ResumeSessionRequest {
  type: 'resume_session'
  data: { session_id: string }
}

/** Requests the server to create a fresh session. */
export interface NewSessionRequest {
  type: 'new_session'
  data: Record<string, never>
}

/** Sends the user's response to a permission prompt (approve/deny). */
export interface PermissionResponseRequest {
  type: 'permission_response'
  data: {
    request_id: string
    option_id: string
    cancelled: boolean
  }
}

/** Discriminated union of all messages the client can send to the server. */
export type ClientMessage = ChatRequest | StopRequest | PingRequest | ClearHistoryRequest | SwitchRequest | ResumeSessionRequest | NewSessionRequest | PermissionResponseRequest

// === Session info (from GET /api/avatar/sessions) ===

/**
 * Summary of a saved session returned by the sessions REST endpoint.
 * @property session_id - Unique session identifier.
 * @property provider - AI provider that owns this session.
 * @property cwd - Working directory the session was started in.
 * @property title - Human-readable session title (auto-generated or user-set).
 * @property updated_at - ISO 8601 timestamp of last activity, or null if unknown.
 * @property is_current - Whether this is the currently active session.
 */
export interface SessionInfo {
  session_id: string
  provider: string
  cwd: string
  title: string
  updated_at: string | null
  is_current: boolean
}

// === UI State ===

/**
 * A single message in the chat UI, combining text content with associated metadata.
 * @property id - Unique message identifier.
 * @property role - Whether this message is from the user or the assistant.
 * @property content - Markdown text content of the message.
 * @property timestamp - Unix timestamp (ms) when the message was created.
 * @property tools - Tool calls associated with this assistant message.
 * @property thinking - Thinking/reasoning metadata, if the model emitted it.
 * @property isStreaming - True while the message is still being streamed.
 * @property durationMs - Total response time in milliseconds.
 * @property costUsd - Cost of this response in USD.
 * @property attachments - Files the user attached to this message.
 * @property images - Images generated during the AI response.
 * @property context - Optional opaque metadata (e.g. page context) sent to the AI but not displayed in the chat bubble.
 */
export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  timestamp: number
  tools: ToolInfo[]
  thinking?: ThinkingInfo
  isStreaming: boolean
  durationMs?: number
  costUsd?: number
  attachments?: UploadedFile[]
  images?: GeneratedImage[]
  context?: Record<string, unknown>
}

/**
 * Tracks the state of a single tool call within a chat message.
 * @property toolId - Server-assigned tool call identifier.
 * @property name - Tool name (e.g. "Read", "Bash", "Edit").
 * @property status - Current execution status.
 * @property params - JSON-serialized tool parameters.
 * @property error - Error message if the tool call failed.
 * @property startedAt - Unix timestamp (ms) when execution started.
 * @property completedAt - Unix timestamp (ms) when execution finished.
 */
export interface ToolInfo {
  toolId: string
  name: string
  status: 'started' | 'completed' | 'failed'
  params: string
  error?: string
  startedAt: number
  completedAt?: number
}

/**
 * Snapshot of the AI model's current thinking/reasoning block.
 * @property phase - What category of reasoning is active.
 * @property subject - Brief label for what the model is thinking about.
 * @property startedAt - Unix timestamp (ms) when thinking began.
 * @property isComplete - Whether this thinking block has finished.
 */
export interface ThinkingInfo {
  phase: ThinkingPhase
  subject: string
  startedAt: number
  isComplete: boolean
}

/**
 * Accumulated cost and token usage across the session.
 * @property totalCostUsd - Running total cost in USD.
 * @property totalInputTokens - Running total of input tokens consumed.
 * @property totalOutputTokens - Running total of output tokens generated.
 */
export interface CostInfo {
  totalCostUsd: number
  totalInputTokens: number
  totalOutputTokens: number
}

// === Widget / Avatar types ===

/** Display mode of the avatar widget overlay. */
export type WidgetMode = 'fab' | 'compact' | 'fullscreen'

/** Visual state of the avatar bust animation. */
export type BustState = 'idle' | 'thinking' | 'speaking' | 'error'

/**
 * Maps engine states to avatar pose asset identifiers.
 * @property idle - Pose shown when the engine is idle; "auto" selects one automatically.
 * @property thinking - Optional pose shown during thinking/reasoning.
 * @property error - Optional pose shown on error.
 * @property speaking - Optional pose shown while the assistant is responding.
 */
export interface AvatarPoses {
  idle: string | 'auto'
  thinking?: string
  error?: string
  speaking?: string
}

/**
 * Configuration for a single avatar character.
 * @property id - Unique avatar identifier.
 * @property name - Human-readable avatar name.
 * @property poses - Pose asset mapping for different engine states.
 * @property speakingFrames - Number of animation frames in the speaking sequence.
 * @property speakingFps - Frames per second for speaking animation playback.
 */
export interface AvatarConfig {
  id: string
  name: string
  poses: AvatarPoses
  speakingFrames: number
  speakingFps: number
}

/** Dimensions (px) of the compact widget mode. */
export interface CompactDimensions {
  width: number
  height: number
}

/** Client-side representation of a pending permission request shown in the PermissionDialog. */
export interface PermissionRequest {
  requestId: string
  toolName: string
  toolInput: string
  options: Array<{ option_id: string; kind: string }>
}

// localStorage keys
export const LS_BUST_VISIBLE = 'avatar-engine-bust-visible'
export const LS_WIDGET_MODE = 'avatar-engine-widget-mode'
export const LS_COMPACT_HEIGHT = 'avatar-engine-compact-height'
export const LS_COMPACT_WIDTH = 'avatar-engine-compact-width'
export const LS_SELECTED_AVATAR = 'avatar-engine-selected-avatar'
export const LS_HINTS_SHOWN = 'avatar-engine-hints-shown'
export const LS_DEFAULT_MODE = 'avatar-engine-default-mode'
export const LS_LANGUAGE = 'avatar-engine-language'
export const LS_PROMO_DISMISSED = 'avatar-engine-promo-dismissed'
