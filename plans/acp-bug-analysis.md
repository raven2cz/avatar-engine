## Root Cause Analysis

After investigating the gemini-cli source code, the root cause appears to be in how ACP mode handles model configuration resolution.

### The Problem

In **`packages/cli/src/zed-integration/zedIntegration.ts`** (line 489), the ACP `Session.prompt()` method passes a minimal `{ model }` object to `chat.sendMessageStream()`:

```typescript
// zedIntegration.ts, Session.prompt(), line 485-494
const model = resolveModel(
  this.config.getModel(),
  this.config.getPreviewFeatures(),
);
const responseStream = await chat.sendMessageStream(
  { model },          // <-- only { model }, no customAliases context
  nextMessage?.parts ?? [],
  promptId,
  pendingSend.signal,
);
```

Then in **`packages/core/src/core/geminiChat.ts`** (line 305-306), `sendMessageStream()` resolves the `ModelConfigKey` through `ModelConfigService` but **only extracts the `model` field**, discarding the resolved `generateContentConfig`:

```typescript
// geminiChat.ts, sendMessageStream(), line 305-306
const { model } =
  this.config.modelConfigService.getResolvedConfig(modelConfigKey);
// ^^^^ generateContentConfig is resolved but discarded!
```

### Why Normal (Non-ACP) Mode Works

The normal CLI path goes through `GeminiClient.generateContent()` (`packages/core/src/core/client.ts`, line 906) which properly calls:

```typescript
const desiredModelConfig =
  this.config.modelConfigService.getResolvedConfig(modelConfigKey);
let {
  model: currentAttemptModel,
  generateContentConfig: currentAttemptGenerateContentConfig,
} = desiredModelConfig;
```

Here, **both** `model` and `generateContentConfig` are extracted and used, so `customAliases` configuration (system instructions, temperature, safety settings, etc.) is properly applied.

### ModelConfigService Resolution Chain

`ModelConfigService.getResolvedConfig()` (`packages/core/src/services/modelConfigService.ts`, line 285) correctly resolves `customAliases` through `resolveAliasChain()` (line 159), which walks the alias `extends` hierarchy and merges `modelConfig` from root to leaf. The resolution itself works correctly — the problem is that ACP's code path discards the resolved configuration.

### Comparison

| Aspect | ACP Path | Normal Path |
|--------|----------|-------------|
| Entry Point | `Session.prompt()` line 489 | `GeminiClient.generateContent()` line 906 |
| Config Extraction | `{ model }` only | `{ model, generateContentConfig }` |
| Result | `customAliases` config lost | `customAliases` fully applied |

### Suggested Fix

In `geminiChat.ts` `sendMessageStream()`, the resolved `generateContentConfig` should be preserved and passed through to the API call, similar to how `GeminiClient.generateContent()` handles it. Alternatively, the ACP path in `zedIntegration.ts` could be routed through `GeminiClient` to reuse the existing proper resolution logic.
