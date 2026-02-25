// Protocol — state machine
export { avatarReducer, parseServerMessage, initialAvatarState } from './protocol'
export type { AvatarState, AvatarAction } from './protocol'

// Client — framework-agnostic WS client
export { AvatarClient } from './client'
export type { AvatarClientOptions } from './client'

// Message builders
export {
  createChatMessage,
  createStopMessage,
  createSwitchMessage,
  createPermissionResponse,
  createResumeSessionMessage,
  createNewSessionMessage,
  createClearHistoryMessage,
  createPingMessage,
} from './protocol'

// Types
export type {
  SafetyMode,
  EngineState,
  BridgeState,
  ThinkingPhase,
  ActivityStatus,
  ChatMessage,
  CostInfo,
  ThinkingInfo,
  ToolInfo,
  ServerMessage,
  ConnectedMessage,
  TextMessage,
  ThinkingMessage,
  ToolMessage,
  StateMessage,
  EngineStateMessage,
  CostMessage,
  ErrorMessage,
  DiagnosticMessage,
  ActivityMessage,
  ChatResponseMessage,
  PongMessage,
  HistoryClearedMessage,
  InitializingMessage,
  SessionTitleUpdatedMessage,
  PermissionRequestMessage,
  ClientMessage,
  ChatRequest,
  StopRequest,
  SwitchRequest,
  PermissionResponseRequest,
  ResumeSessionRequest,
  NewSessionRequest,
  ClearHistoryRequest,
  PingRequest,
  ProviderCapabilities,
  ChatAttachment,
  UploadedFile,
  GeneratedImage,
  SessionInfo,
  WidgetMode,
  BustState,
  AvatarPoses,
  AvatarConfig,
  CompactDimensions,
  PermissionRequest,
} from './types'

// localStorage keys
export {
  LS_BUST_VISIBLE,
  LS_WIDGET_MODE,
  LS_COMPACT_HEIGHT,
  LS_COMPACT_WIDTH,
  LS_SELECTED_AVATAR,
  LS_HINTS_SHOWN,
  LS_DEFAULT_MODE,
  LS_LANGUAGE,
  LS_PROMO_DISMISSED,
} from './types'

// Config
export {
  PROVIDERS,
  createProviders,
  getProvider,
  getModelsForProvider,
  getOptionsForProvider,
  isImageModel,
  filterChoicesForModel,
  buildOptionsDict,
  getFeaturedLabel,
  getModelDisplayName,
} from './config/providers'
export type { ProviderConfig, ProviderOption } from './config/providers'

export {
  AVATARS,
  DEFAULT_AVATAR_ID,
  getAvatarById,
  getAvatarBasePath,
} from './config/avatars'

// i18n — IMPORTANT: Call initAvatarI18n() before rendering React components.
// For React apps: initAvatarI18n(reactI18nextModule)
// For non-React: initAvatarI18n()
export {
  initAvatarI18n,
  changeLanguage,
  getCurrentLanguage,
  AVAILABLE_LANGUAGES,
  i18n,
} from './i18n'

// Utils
export { nextId, summarizeParams } from './utils'
