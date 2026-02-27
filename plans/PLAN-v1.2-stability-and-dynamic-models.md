# Plan: v1.2 — Claude working dirs, dynamické modely (web scraping)

**Status:** Approved
**Datum:** 2026-02-26
**Branch:** `feature/v1.2-stability`

---

## Motivace

Po release v1.1.0 a integraci do Synapse máme dva problémy:

1. **Claude Code working dirs** — V Synapse projektu Claude nemůže přistupovat k `~/.synapse`, protože working_dir je jinde. CLI flag `--add-dir` existuje, ale bridge ho nepoužívá.
2. **Zastaralé seznamy modelů** — Statický `PROVIDERS` v providers.ts zastarává během dnů (Gemini je už na 3.1!). CLI nástroje nemají `models list` příkaz a většina uživatelů nemá API klíče (používají měsíční plány + OAuth). Řešení: **scraping dokumentačních stránek providerů**.

> **Část A (Gemini fallback/default) ZRUŠENA** — Modely se mění příliš rychle, hardcoded
> default zastarává. Fallback_model je nebezpečný (zapomene se tam starý model).
> Řeší to Část C — dynamické modely automaticky nabídnou nejnovější.

---

## Část B: Claude Code — additional directories

### B1: Přidat `additional_dirs` do ClaudeBridge

**Soubor:** `avatar_engine/bridges/claude.py`

Nový konstruktor parametr:

```python
def __init__(self, ..., additional_dirs: list[str] | None = None):
    self._additional_dirs = additional_dirs or []
```

V `_build_persistent_command()` přidat `--add-dir` flagy:

```python
for d in self._additional_dirs:
    expanded = os.path.expanduser(d)
    if os.path.isdir(expanded):
        cmd.extend(["--add-dir", expanded])
```

### B2: Propagovat z engine a config

**Soubor:** `avatar_engine/engine.py` — v `_create_bridge()`:

```python
return ClaudeBridge(
    ...
    additional_dirs=pcfg.get("additional_dirs", []),
    ...
)
```

### B3: Propagovat z EngineSessionManager a web API

`additional_dirs` se předá přes `**kwargs` automaticky.

```yaml
# avatar.yaml
claude:
  additional_dirs:
    - ~/.synapse
    - ~/projects/shared-data
```

### B4: Přidat do settings JSON (--settings flag)

V `_prepare_config()` přidat `additionalDirectories` do settings JSON — dvojitá ochrana
(`--add-dir` CLI flag + settings JSON).

### Soubory k úpravě (Část B)

| Soubor | Změna |
|--------|-------|
| `avatar_engine/bridges/claude.py` | `additional_dirs` param, `--add-dir` flags, settings JSON |
| `avatar_engine/engine.py` | Předat `additional_dirs` do ClaudeBridge |

---

## Část C: Dynamické seznamy modelů (web scraping)

### Proč scraping?

- **CLI nástroje nemají `models list`** — ověřeno: Gemini CLI, Claude Code ani Codex CLI nemají příkaz pro výpis modelů
- **Většina uživatelů nemá API klíče** — Avatar Engine je postavený na měsíčních plánech (Google OAuth, Anthropic subscription, OpenAI plan)
- **Dokumentační stránky jsou aktuální** — provideři docs aktualizují při každém releasu modelu

### Zdrojové stránky

| Provider | URL | Formát |
|----------|-----|--------|
| **Claude** | `https://platform.claude.com/docs/en/about-claude/models/overview` | HTML tabulka — "Claude API alias" |
| **Gemini** | `https://ai.google.dev/gemini-api/docs/models` | Seznam modelů s ID |
| **Codex** | `https://developers.openai.com/codex/models/` | Přehledný seznam s ID |

### Architektura — Strategy pattern + Registry

Parsery zrcadlí vzor `bridges/` — každý provider má vlastní parser třídu:

```
avatar_engine/web/model_discovery/
  __init__.py          # Veřejné API: fetch_models(), invalidate_cache(), get_parser()
  base.py              # ModelParser ABC — rozhraní pro všechny parsery
  registry.py          # ParserRegistry — registr + factory
  cache.py             # ModelCache — in-memory + TTL logika
  claude_parser.py     # ClaudeModelParser
  gemini_parser.py     # GeminiModelParser
  codex_parser.py      # CodexModelParser
```

### C1: `base.py` — ModelParser ABC

```python
"""Abstract base class for model parsers.

Each parser is responsible for:
1. Fetching its provider's documentation page
2. Extracting model identifiers from HTML
3. Determining which model is the default (most capable)
4. Filtering out non-chat models (embeddings, TTS, image gen, etc.)

To add a new provider parser:
1. Create a new file (e.g., mistral_parser.py)
2. Subclass ModelParser
3. Register in registry.py
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class ParseResult:
    """Result of parsing a provider's model documentation."""
    provider: str
    models: list[str]                 # Sorted: best first
    default_model: str | None         # Recommended default (first in list)
    source_url: str                   # URL that was scraped
    legacy_models: list[str] = field(default_factory=list)  # Older but still available


class ModelParser(ABC):
    """Abstract parser for provider documentation pages."""

    @property
    @abstractmethod
    def provider_id(self) -> str:
        """Provider identifier matching PROVIDERS config (e.g., 'gemini')."""
        ...

    @property
    @abstractmethod
    def source_url(self) -> str:
        """Documentation URL to scrape."""
        ...

    @abstractmethod
    def parse(self, html: str) -> ParseResult:
        """Parse HTML content and extract model identifiers.

        Must return non-empty models list or raise ValueError.
        Raises ValueError if page structure changed and parsing failed.
        """
        ...

    async def fetch_and_parse(self, client: httpx.AsyncClient) -> ParseResult:
        """Fetch page and parse. Subclasses can override for multi-page scraping."""
        resp = await client.get(self.source_url, headers=self._headers())
        resp.raise_for_status()
        result = self.parse(resp.text)
        if not result.models:
            raise ValueError(
                f"No models parsed from {self.source_url} — "
                f"page structure may have changed, parser needs update"
            )
        return result

    def _headers(self) -> dict[str, str]:
        return {
            "User-Agent": "AvatarEngine/1.2 ModelDiscovery",
            "Accept": "text/html,application/xhtml+xml,*/*",
        }
```

### C2: Provider parsery

Každý parser v samostatném souboru. Příklad `claude_parser.py`:

```python
"""Claude model parser — scrapes platform.claude.com docs.

Expected page structure:
  - HTML table with columns including "Claude API alias" and "Claude API ID"
  - Model IDs match pattern: claude-{tier}-{version}[-datestring]
  - Current models in "Latest models comparison" section
  - Legacy models in "Legacy models" section
"""

import re
from .base import ModelParser, ParseResult

# Pattern matches: claude-opus-4-6, claude-sonnet-4-5-20250929, etc.
_MODEL_PATTERN = re.compile(r"claude-(?:opus|sonnet|haiku)-[\w.-]+")
_DATE_SUFFIX = re.compile(r"-\d{8}$")


class ClaudeModelParser(ModelParser):
    provider_id = "claude"
    source_url = "https://platform.claude.com/docs/en/about-claude/models/overview"

    def parse(self, html: str) -> ParseResult:
        raw = set(_MODEL_PATTERN.findall(html))
        aliases = sorted(
            [m for m in raw if not _DATE_SUFFIX.search(m)],
            key=self._sort_key,
        )
        legacy = sorted(
            [m for m in aliases if self._is_legacy(m, aliases)],
            key=self._sort_key,
        )
        current = [m for m in aliases if m not in legacy]
        return ParseResult(
            provider="claude",
            models=current,
            default_model=current[0] if current else None,
            source_url=self.source_url,
            legacy_models=legacy,
        )
```

Stejný pattern pro `gemini_parser.py` (s blacklist filtrem pro non-chat modely)
a `codex_parser.py`.

### C3: `registry.py` — ParserRegistry

```python
"""Parser registry — factory + discovery.

Usage:
    registry = ParserRegistry()
    registry.register(ClaudeModelParser())
    registry.register(GeminiModelParser())
    registry.register(CodexModelParser())

    parser = registry.get("gemini")
    result = await parser.fetch_and_parse(client)

    # Or fetch all at once:
    results = await registry.fetch_all(client)
"""

class ParserRegistry:
    def __init__(self):
        self._parsers: dict[str, ModelParser] = {}

    def register(self, parser: ModelParser) -> None:
        self._parsers[parser.provider_id] = parser

    def get(self, provider_id: str) -> ModelParser | None:
        return self._parsers.get(provider_id)

    @property
    def providers(self) -> list[str]:
        return list(self._parsers.keys())

    async def fetch_all(self, client) -> tuple[dict[str, ParseResult], dict[str, str]]:
        """Returns (results, errors) tuple."""
        results, errors = {}, {}
        for pid, parser in self._parsers.items():
            try:
                results[pid] = await parser.fetch_and_parse(client)
            except Exception as e:
                errors[pid] = str(e)
        return results, errors


# Default registry with all built-in parsers
def create_default_registry() -> ParserRegistry:
    from .claude_parser import ClaudeModelParser
    from .gemini_parser import GeminiModelParser
    from .codex_parser import CodexModelParser

    registry = ParserRegistry()
    registry.register(ClaudeModelParser())
    registry.register(GeminiModelParser())
    registry.register(CodexModelParser())
    return registry
```

### C4: `cache.py` — ModelCache

```python
"""In-memory cache with TTL for parsed model results."""

import time
from dataclasses import dataclass
from .base import ParseResult

@dataclass
class CacheEntry:
    results: dict[str, ParseResult]
    errors: dict[str, str]
    timestamp: float

class ModelCache:
    def __init__(self, ttl: int = 86400):  # 24h default
        self._ttl = ttl
        self._entry: CacheEntry | None = None

    def get(self) -> CacheEntry | None:
        if self._entry and (time.time() - self._entry.timestamp) < self._ttl:
            return self._entry
        return None

    def set(self, results: dict[str, ParseResult], errors: dict[str, str]) -> None:
        self._entry = CacheEntry(results=results, errors=errors, timestamp=time.time())

    def invalidate(self) -> None:
        self._entry = None
```

### C5: `__init__.py` — veřejné API

```python
"""Dynamic model discovery via web scraping.

Public API:
    fetch_models(providers=None) → dict    # Main entry point
    invalidate_cache() → None              # Force refresh
    get_registry() → ParserRegistry        # Access parsers
"""

from .registry import create_default_registry, ParserRegistry
from .cache import ModelCache
from .base import ModelParser, ParseResult

_registry = create_default_registry()
_cache = ModelCache(ttl=86400)

async def fetch_models(providers: list[str] | None = None) -> dict:
    """Fetch models from documentation pages. Returns JSON-serializable dict."""
    cached = _cache.get()
    if cached:
        return _serialize(cached.results, cached.errors)

    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
        results, errors = await _registry.fetch_all(client)

    _cache.set(results, errors)
    return _serialize(results, errors)


def _serialize(results, errors) -> dict:
    """Convert ParseResults to JSON-serializable dict for API response."""
    data = {}
    for pid, result in results.items():
        data[pid] = {
            "models": result.models,
            "defaultModel": result.default_model,
            "source": result.source_url,
            "legacyModels": result.legacy_models,
        }
    if errors:
        data["errors"] = errors
    data["fetched_at"] = ...
    return data
```

### C6: Server endpoint

**Soubor:** `avatar_engine/web/server.py`

```python
from avatar_engine.web.model_discovery import fetch_models, invalidate_cache

@app.get("/api/avatar/models")
async def get_models(refresh: bool = False) -> JSONResponse:
    if refresh:
        invalidate_cache()
    result = await fetch_models()
    return JSONResponse(result)
```

Query param `?refresh=true` vynutí nový scrape (pro manuální debug).

### C7: React hook `useDynamicModels`

**Soubor:** `packages/react/src/hooks/useDynamicModels.ts` (nový)

Třívrstvý fallback: static → localStorage → backend fetch.
Při chybě emituje `CustomEvent('avatar-engine:model-error')`.

### C8: React hook `useModelDiscoveryErrors`

**Soubor:** `packages/react/src/hooks/useModelDiscoveryErrors.ts` (nový)

Listener hook — host app (Synapse) ho použije pro zobrazení warning toastu/banneru.

### C9: Export

**Soubor:** `packages/react/src/index.ts`

```typescript
export { useDynamicModels } from './hooks/useDynamicModels'
export { useModelDiscoveryErrors } from './hooks/useModelDiscoveryErrors'
export type { ModelDiscoveryError } from './hooks/useModelDiscoveryErrors'
```

### Soubory k úpravě (Část C)

| Soubor | Typ | Popis |
|--------|-----|-------|
| `avatar_engine/web/model_discovery/__init__.py` | **Nový** | Veřejné API: `fetch_models()`, `invalidate_cache()` |
| `avatar_engine/web/model_discovery/base.py` | **Nový** | `ModelParser` ABC + `ParseResult` dataclass |
| `avatar_engine/web/model_discovery/registry.py` | **Nový** | `ParserRegistry` + `create_default_registry()` |
| `avatar_engine/web/model_discovery/cache.py` | **Nový** | `ModelCache` s TTL |
| `avatar_engine/web/model_discovery/claude_parser.py` | **Nový** | `ClaudeModelParser` |
| `avatar_engine/web/model_discovery/gemini_parser.py` | **Nový** | `GeminiModelParser` |
| `avatar_engine/web/model_discovery/codex_parser.py` | **Nový** | `CodexModelParser` |
| `avatar_engine/web/server.py` | Upravit | `GET /api/avatar/models` endpoint |
| `packages/react/src/hooks/useDynamicModels.ts` | **Nový** | React hook, třívrstvý fallback |
| `packages/react/src/hooks/useModelDiscoveryErrors.ts` | **Nový** | Error listener hook |
| `packages/react/src/index.ts` | Upravit | Export nových hooků |

---

## Testy

### Unit testy — `tests/test_model_discovery.py`

Testují parsing logiku s **fixture HTML** (uložené snapshoty stránek):

```python
# Fixture HTML uložené v tests/fixtures/
# tests/fixtures/claude_models.html
# tests/fixtures/gemini_models.html
# tests/fixtures/codex_models.html

class TestClaudeParser:
    def test_parse_current_models(self, claude_html):
        parser = ClaudeModelParser()
        result = parser.parse(claude_html)
        assert "claude-opus-4-6" in result.models
        assert result.default_model == "claude-opus-4-6"

    def test_parse_separates_legacy(self, claude_html):
        result = ClaudeModelParser().parse(claude_html)
        assert "claude-opus-4-0" in result.legacy_models
        assert "claude-opus-4-0" not in result.models

    def test_parse_empty_html_raises(self):
        with pytest.raises(ValueError, match="No models parsed"):
            ClaudeModelParser().parse("<html></html>")

class TestGeminiParser:
    def test_excludes_non_chat_models(self, gemini_html):
        result = GeminiModelParser().parse(gemini_html)
        assert not any("tts" in m for m in result.models)
        assert not any("embedding" in m for m in result.models)
        assert not any("image" in m.split("-")[-1] for m in result.models)

    def test_sorts_by_version(self, gemini_html):
        result = GeminiModelParser().parse(gemini_html)
        # 3.1 before 3.0 before 2.5
        assert result.models.index("gemini-3.1-pro-preview") < \
               result.models.index("gemini-2.5-flash")

class TestCodexParser:
    def test_parse_models(self, codex_html):
        result = CodexModelParser().parse(codex_html)
        assert "gpt-5.3-codex" in result.models

class TestParserRegistry:
    def test_register_and_get(self):
        registry = ParserRegistry()
        registry.register(ClaudeModelParser())
        assert registry.get("claude") is not None
        assert registry.get("unknown") is None

    def test_default_registry_has_all_providers(self):
        registry = create_default_registry()
        assert set(registry.providers) == {"claude", "gemini", "codex"}

class TestModelCache:
    def test_ttl_expiry(self):
        cache = ModelCache(ttl=1)
        cache.set({"claude": ...}, {})
        time.sleep(1.1)
        assert cache.get() is None

    def test_invalidate(self):
        cache = ModelCache()
        cache.set({"claude": ...}, {})
        cache.invalidate()
        assert cache.get() is None
```

### Live/canary testy — `tests/test_model_discovery_live.py`

Označené `@pytest.mark.live` — spouštějí se separátně, testují **reálný scraping**:

```python
"""Live tests — fetch real documentation pages and verify parsing.

Run with: uv run pytest tests/test_model_discovery_live.py -v
These tests hit real URLs. When they fail, it means the documentation
page structure changed and the parser needs updating.

NOT included in default test run (requires @pytest.mark.live).
"""

@pytest.mark.live
@pytest.mark.asyncio
class TestClaudeParserLive:
    async def test_fetch_and_parse_real_page(self):
        parser = ClaudeModelParser()
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            result = await parser.fetch_and_parse(client)
        assert len(result.models) >= 2, f"Expected ≥2 models, got: {result.models}"
        assert result.default_model is not None
        # Every model ID must start with 'claude-'
        assert all(m.startswith("claude-") for m in result.models)

@pytest.mark.live
@pytest.mark.asyncio
class TestGeminiParserLive:
    async def test_fetch_and_parse_real_page(self):
        parser = GeminiModelParser()
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            result = await parser.fetch_and_parse(client)
        assert len(result.models) >= 3, f"Expected ≥3 models, got: {result.models}"
        assert all(m.startswith("gemini-") for m in result.models)
        # Must not contain non-chat models
        for m in result.models:
            assert "embedding" not in m
            assert "tts" not in m

@pytest.mark.live
@pytest.mark.asyncio
class TestCodexParserLive:
    async def test_fetch_and_parse_real_page(self):
        parser = CodexModelParser()
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            result = await parser.fetch_and_parse(client)
        assert len(result.models) >= 2, f"Expected ≥2 models, got: {result.models}"
        assert all(m.startswith("gpt-") for m in result.models)

@pytest.mark.live
@pytest.mark.asyncio
class TestFullDiscoveryLive:
    async def test_fetch_all_providers(self):
        """End-to-end: all three providers return valid models."""
        result = await fetch_models()
        for provider in ["claude", "gemini", "codex"]:
            assert provider in result, f"Missing provider: {provider}"
            assert len(result[provider]["models"]) >= 2
        # No errors expected when all pages are up
        assert "errors" not in result or len(result["errors"]) == 0
```

### Konfigurace pytest

**Soubor:** `pyproject.toml` — přidat marker:

```toml
markers = [
    "integration: integration tests requiring real CLI tools",
    "live: live scraping tests hitting real documentation URLs",
    ...
]
```

**Default test run** (`uv run pytest`) přeskočí live testy.
**CI canary job** může spouštět live testy jako scheduled check.

---

## Pořadí implementace

```
1. model_discovery/ package  — base.py, registry.py, cache.py
2. Tři parsery               — claude, gemini, codex (+ fixture HTML)
3. Unit testy                 — test_model_discovery.py
4. Live testy                 — test_model_discovery_live.py (ověří parsing)
5. Server endpoint            — GET /api/avatar/models
6. React hooks                — useDynamicModels, useModelDiscoveryErrors
7. Claude add-dir (Část B)    — bridges/claude.py, engine.py
```

---

## Ověření

```bash
# Build
npm run build -w packages/core -w packages/react

# Unit testy (rychlé, offline)
uv run pytest tests/test_model_discovery.py -v

# Live testy (canary — ověří, že parsery fungují na reálných stránkách)
uv run pytest tests/test_model_discovery_live.py -v

# Všechny testy
npm test -w packages/core && uv run pytest tests/ -x --timeout=30

# Manuální test
# GET /api/avatar/models → vrátí modely ze všech providerů
# GET /api/avatar/models?refresh=true → vynutí nový scrape
```

---

## Dopad na Synapse

Po release v1.2.0:

```bash
npm install @avatar-engine/core@^1.2.0 @avatar-engine/react@^1.2.0
pip install avatar-engine==1.2.0
```

```yaml
# avatar.yaml
claude:
  additional_dirs:
    - ~/.synapse
```

```tsx
import { useDynamicModels, useModelDiscoveryErrors } from '@avatar-engine/react'

const dynamicProviders = useDynamicModels('/api/avatar')
const modelErrors = useModelDiscoveryErrors()

<AvatarWidget customProviders={dynamicProviders} ... />
{modelErrors.length > 0 && <WarningBanner errors={modelErrors} />}
```
