# Plán: Media Input & Image Generation

> Status: IMPLEMENTOVÁNO (Fáze 1–5 hotové, Fáze 6 částečně, Fáze 7 hotová)
> Vytvořeno: 2026-02-09
> Aktualizováno: 2026-02-09
> Závisí na: PHASE7_WEB_BRIDGE_PLAN.md (web GUI), SESSION_GUI_PLAN.md (session modal)

## Kontext

Avatar Engine aktuálně podporuje pouze textový vstup/výstup.
Všechny providery (Gemini, Claude, Codex) podporují multimodální vstup —
obrázky, PDF, audio — ale naše bridges posílají jen `text_block()`.

**Kritický use case**: Analýza velkých skenovaných anglických knih (PDF, stovky stránek).
Gemini podporuje až 1000 stránek/PDF, Claude až 100 stránek — ideální pro tento účel.

### Podpora providerů

| Funkce | Gemini | Claude | Codex |
|---|---|---|---|
| Obrázky (vstup) | Ano (JPEG/PNG/WebP/HEIC) | Ano (JPEG/PNG/GIF/WebP) | Ano (PNG/JPEG/GIF/WebP) |
| PDF (vstup) | Ano (až 1000 stránek, 50 MB) | Ano (až 100 stránek, 32 MB payload) | Ne |
| Audio (vstup) | Ano (MP3/WAV/OGG/FLAC...) | Ne | Ne |
| Generování obrázků | Ano (Imagen, gemini-*-image modely) | Ne | Ano (gpt-image-1) |
| Max velikost inline | ~20 MB praktický (50 MB dokumentace) | 32 MB (celý payload) | ~20 MB |

### ACP SDK — dostupné typy

```
ContentBlock (Union)
├── TextContentBlock       — text_block(text)
├── ImageContentBlock      — image_block(data_b64, mime)      # pouze obrázky
├── AudioContentBlock      — audio_block(data_b64, mime)      # pouze audio
├── ResourceContentBlock   — resource_link_block(name, uri)   # odkaz na soubor
└── EmbeddedResourceContentBlock — resource_block(resource)   # embedded binární data
    └── resource: embedded_blob_resource(uri, blob_b64, mime) # PDF, video, cokoliv
```

**DŮLEŽITÉ**: `image_block()` je POUZE pro obrázky. Pro PDF a jiné soubory →
`embedded_blob_resource()` + `resource_block()`.

Všechna data se přenáší jako **base64** v JSON. Žádné kopírování souborů —
soubor se načte z disku, zakóduje do base64, a odešle v ACP/stream-json zprávě.

### Výkonnostní pravidlo

95% zpráv je čistý text → `[text_block(prompt)]` (stávající chování, nulová režie).
Multimodální bloky se přidávají POUZE když uživatel skutečně připojí přílohu.

---

## Fáze 1: Datový model — Attachment ✅ HOTOVO

### 1.1 `Attachment` dataclass

**Soubor:** `avatar_engine/types.py`

```python
@dataclass
class Attachment:
    """File attachment metadata."""
    path: Path          # Lokální cesta k souboru na disku
    mime_type: str       # MIME typ (image/png, application/pdf, ...)
    filename: str        # Originální název souboru
    size: int           # Velikost v bajtech
```

### 1.2 Rozšíření `Message`

**Soubor:** `avatar_engine/types.py` a `avatar_engine/bridges/base.py`

```python
@dataclass
class Message:
    role: str
    content: str
    timestamp: float = field(default_factory=time.time)
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    attachments: List[Attachment] = field(default_factory=list)  # NOVÉ
```

Zero overhead pro textové zprávy — `field(default_factory=list)` nevytvoří seznam
dokud někdo nepřistoupí k `.attachments`.

### 1.3 Rozšíření `BridgeResponse`

**Soubor:** `avatar_engine/types.py`

```python
@dataclass
class BridgeResponse:
    content: str
    # ... stávající pole ...
    generated_images: List[Path] = field(default_factory=list)  # NOVÉ — cesty k vygenerovaným obrázkům
```

---

## Fáze 2: Upload endpoint a storage ✅ HOTOVO

### 2.1 Upload storage

**Soubor:** `avatar_engine/web/uploads.py` (NOVÝ)

```python
class UploadStorage:
    """Manages uploaded file storage."""

    def __init__(self, base_dir: Optional[Path] = None):
        # Default: $TMPDIR/avatar-engine/uploads/ nebo /tmp/avatar-engine/uploads/
        # Přepsat: env AVATAR_UPLOAD_DIR nebo --upload-dir CLI flag
        self._base = base_dir or Path(tempfile.gettempdir()) / "avatar-engine" / "uploads"
        self._base.mkdir(parents=True, exist_ok=True)

    def save(self, filename: str, data: bytes, mime_type: str) -> Attachment:
        """Uloží soubor, vrátí Attachment."""
        safe_name = f"{uuid4().hex[:12]}_{sanitize_filename(filename)}"
        path = self._base / safe_name
        path.write_bytes(data)
        return Attachment(path=path, mime_type=mime_type, filename=filename, size=len(data))

    def cleanup_old(self, max_age_hours: int = 24) -> int:
        """Smaže staré soubory z tmp. Vrátí počet smazaných."""
        ...
```

Sanitizace filename: odstraní `../`, null bajty, omezí délku na 200 znaků.

### 2.2 REST upload endpoint

**Soubor:** `avatar_engine/web/server.py`

```python
@app.post("/api/avatar/upload")
async def upload_file(file: UploadFile) -> Dict:
    """Upload souboru pro připojení ke zprávě."""
    data = await file.read()
    if len(data) > MAX_UPLOAD_SIZE:  # 100 MB default
        raise HTTPException(413, "File too large")

    attachment = upload_storage.save(
        filename=file.filename or "unnamed",
        data=data,
        mime_type=file.content_type or "application/octet-stream",
    )
    return {
        "file_id": attachment.path.stem,
        "filename": attachment.filename,
        "mime_type": attachment.mime_type,
        "size": attachment.size,
        "path": str(attachment.path),
    }
```

**Konfigurace:**
- `MAX_UPLOAD_SIZE`: 100 MB (env `AVATAR_MAX_UPLOAD_MB`)
- `AVATAR_UPLOAD_DIR`: Persistentní adresář (env var)

### 2.3 Statický přístup k uploadům

```python
# Pro zobrazení vygenerovaných obrázků ve frontendu
app.mount("/api/avatar/files", StaticFiles(directory=upload_storage.base_dir))
```

---

## Fáze 3: Bridge vrstva — attachments ✅ HOTOVO

### 3.1 Rozšíření `BaseBridge.send()`

**Soubor:** `avatar_engine/bridges/base.py`

```python
async def send(self, prompt: str, attachments: Optional[List[Attachment]] = None) -> BridgeResponse:
    """Send prompt with optional file attachments."""
```

Signatura se změní, ale default `None` zajistí zpětnou kompatibilitu.
Stávající volání `bridge.send(prompt)` fungují beze změny.

### 3.2 `Engine.chat()` rozšíření

**Soubor:** `avatar_engine/engine.py`

```python
async def chat(self, message: str, attachments: Optional[List[Attachment]] = None) -> BridgeResponse:
```

Jednoduché průchozí předání do `bridge.send(message, attachments)`.

### 3.3 GeminiBridge — multimodální prompt

**Soubor:** `avatar_engine/bridges/gemini.py`

V `_send_acp()`:
```python
async def _send_acp(self, prompt: str, attachments: Optional[List[Attachment]] = None) -> BridgeResponse:
    effective_prompt = self._prepend_system_prompt(prompt)

    # Sestavit content bloky
    blocks = []

    if attachments:
        for att in attachments:
            b64 = base64.b64encode(att.path.read_bytes()).decode()
            if att.mime_type.startswith("image/"):
                blocks.append(image_block(b64, att.mime_type))
            elif att.mime_type == "application/pdf":
                blocks.append(resource_block(
                    embedded_blob_resource(f"file://{att.path}", b64, mime_type=att.mime_type)
                ))
            elif att.mime_type.startswith("audio/"):
                blocks.append(audio_block(b64, att.mime_type))
            else:
                # Ostatní binární formáty
                blocks.append(resource_block(
                    embedded_blob_resource(f"file://{att.path}", b64, mime_type=att.mime_type)
                ))

    blocks.append(text_block(effective_prompt))

    result = await asyncio.wait_for(
        self._acp_conn.prompt(
            session_id=self._acp_session_id,
            prompt=blocks,  # [image_block, ..., text_block] nebo jen [text_block]
        ),
        timeout=self.timeout,
    )
```

**Poznámka k base64 overhead**: 100 MB soubor → ~133 MB v base64.
Pro skutečně obrovské soubory (>50 MB) zvážit budoucí integraci s Gemini Files API
(přímé volání google-genai SDK, bypass ACP). Ale pro MVP stačí base64 —
většina skenovaných knih je 20-40 MB.

### 3.4 ClaudeBridge — multimodální stream-json

**Soubor:** `avatar_engine/bridges/claude.py`

V `_format_user_message()`:
```python
def _format_user_message(self, prompt: str, attachments: Optional[List[Attachment]] = None) -> str:
    content = []

    # Přílohy PŘED textem (doporučení z Claude docs)
    if attachments:
        for att in attachments:
            b64 = base64.b64encode(att.path.read_bytes()).decode()
            if att.mime_type.startswith("image/"):
                content.append({
                    "type": "image",
                    "source": {"type": "base64", "media_type": att.mime_type, "data": b64},
                })
            elif att.mime_type == "application/pdf":
                content.append({
                    "type": "document",
                    "source": {"type": "base64", "media_type": att.mime_type, "data": b64},
                    "title": att.filename,
                })

    content.append({"type": "text", "text": prompt})

    msg = {
        "type": "user",
        "message": {"role": "user", "content": content},
    }
    if self.session_id:
        msg["session_id"] = self.session_id
    return json.dumps(msg, ensure_ascii=False)
```

### 3.5 CodexBridge — multimodální ACP

**Soubor:** `avatar_engine/bridges/codex.py`

Stejný vzor jako GeminiBridge — `image_block()` pro obrázky.
Codex nepodporuje PDF vstup, tak pro PDF přidáme textovou poznámku.

---

## Fáze 4: WebSocket protokol ✅ HOTOVO

### 4.1 Chat zpráva s přílohami

**Soubor:** `avatar_engine/web/protocol.py`

Rozšířit `parse_client_message()` — typ `chat` může mít pole `attachments`:

```json
{
  "type": "chat",
  "data": {
    "message": "Analyzuj tento dokument",
    "attachments": [
      {"file_id": "a1b2c3d4e5f6_kniha.pdf", "filename": "kniha.pdf", "mime_type": "application/pdf", "path": "/tmp/avatar-engine/uploads/a1b2c3d4e5f6_kniha.pdf"}
    ]
  }
}
```

### 4.2 Server — zpracování příloh

**Soubor:** `avatar_engine/web/server.py`

V `_run_chat()`:
```python
attachments_data = msg_data.get("attachments", [])
attachments = [
    Attachment(
        path=Path(a["path"]),
        mime_type=a["mime_type"],
        filename=a["filename"],
        size=Path(a["path"]).stat().st_size,
    )
    for a in attachments_data
    if Path(a["path"]).exists()  # Bezpečnostní kontrola
]

response = await asyncio.wait_for(
    eng.chat(msg, attachments=attachments or None),
    timeout=120,
)
```

**Bezpečnost**: Validovat, že cesty příloh jsou UVNITŘ upload adresáře
(zabránit path traversal).

### 4.3 Odpověď s vygenerovanými obrázky

Rozšířit `response_to_dict()` o `generated_images`:
```python
def response_to_dict(response: BridgeResponse) -> Dict[str, Any]:
    d = { ... stávající ... }
    if response.generated_images:
        d["data"]["images"] = [
            {"url": f"/api/avatar/files/{p.name}", "filename": p.name}
            for p in response.generated_images
        ]
    return d
```

---

## Fáze 5: Frontend — Upload UI ✅ HOTOVO

**Implementační poznámky:**
- Drag & drop, paste (Ctrl+V), file picker — vše funguje
- Náhledy: obrázky max-h-32/max-h-40 s gradient overlay, PDF/audio ikona + název + velikost
- Dynamický frontend timeout: 30s + 3s/MB pro velké přílohy
- Error z `chat_response` se zobrazí v bublině pokud content je prázdný
- Velké soubory >20 MB: srozumitelná chybová hláška v GUI + ACP restart na pozadí

### 5.1 Upload hook

**Soubor:** `examples/web-demo/src/hooks/useFileUpload.ts` (NOVÝ)

```typescript
interface UploadedFile {
  fileId: string
  filename: string
  mimeType: string
  size: number
  path: string
  previewUrl?: string  // Pro obrázky: Object URL pro náhled
}

function useFileUpload() {
  const [pending, setPending] = useState<UploadedFile[]>([])
  const [uploading, setUploading] = useState(false)

  async function upload(file: File): Promise<UploadedFile> {
    // POST /api/avatar/upload (multipart/form-data)
    // Vrátí metadata, přidá do pending
  }

  function remove(fileId: string) { ... }
  function clear() { ... }

  return { pending, uploading, upload, remove, clear }
}
```

### 5.2 Drop zone + Paste handler

**Soubor:** `examples/web-demo/src/components/ChatPanel.tsx`

```typescript
// Drop zone na celý chat area
onDragOver → zvýraznění "Drop file here"
onDrop → upload(file) pro každý soubor

// Ctrl+V paste handler na input
onPaste → pokud clipboard obsahuje obrázek, upload(clipboardFile)

// File picker tlačítko vedle send buttonu
<input type="file" accept="image/*,.pdf,.md,.txt" multiple />
```

### 5.3 Attachment preview

Pod textovým inputem, nad send tlačítkem:
```
┌──────────────────────────────────────────────┐
│ [📎 kniha.pdf (23.4 MB) ✕] [🖼 photo.jpg ✕] │
│ ┌──────────────────────────────────────────┐ │
│ │ Analyzuj tuto knihu...           [📎][▶] │ │
│ └──────────────────────────────────────────┘ │
└──────────────────────────────────────────────┘
```

- PDF/dokument: ikona + název + velikost + tlačítko ✕
- Obrázek: miniatura (thumbnail) + název + tlačítko ✕
- Upload progress bar pro velké soubory

### 5.4 Odeslání zprávy s přílohami

**Soubor:** `examples/web-demo/src/hooks/useAvatarChat.ts`

Při odeslání zprávy zahrnout pending attachments:
```typescript
ws.send(JSON.stringify({
  type: "chat",
  data: {
    message: text,
    attachments: pending.map(f => ({
      file_id: f.fileId,
      filename: f.filename,
      mime_type: f.mimeType,
      path: f.path,
    })),
  },
}))
clear()  // Vyčistit pending po odeslání
```

### 5.5 MessageBubble — zobrazení příloh a obrázků

**Soubor:** `examples/web-demo/src/components/MessageBubble.tsx`

- User zprávy: zobrazit ikony příloh (PDF ikona, obrázek thumbnail)
- Assistant zprávy: pokud `images` v odpovědi → `<img>` tag s lightbox na klik
- Markdown rendering: obrázky v markdown se zobrazí inline

---

## Fáze 6: Image Generation (výstup) ⚠️ ČÁSTEČNĚ

**Implementováno:**
- Extrakce vygenerovaných obrázků z Gemini ACP response (`_extract_images_from_result()`)
- Ukládání na disk + `generated_images` v `BridgeResponse`
- Frontend zobrazení v `MessageBubble.tsx` (klikatelné obrázky)
- `response_to_dict()` mapuje `generated_images` na `/api/avatar/files/<name>` URL

**Chybí:**
- Dedikované text-to-image flow (výběr image modelu, Imagen parametry)
- Codex/OpenAI `gpt-image-1` podpora (detekce z tool_calls)
- Lightbox/galerie pro prohlížení obrázků ve větší velikosti
- Testováno pouze s Gemini modely co vrací obrázky inline

### 6.1 Detekce vygenerovaných obrázků

**Gemini**: Modely `gemini-2.0-flash-exp`, `gemini-2.0-flash-preview-image-generation`
a Imagen modely vrací obrázky v response content blocích.

V ACP streamu detekovat `ImageContentBlock` v odpovědi:
```python
# V _send_acp() po zpracování výsledku
for block in result.content:
    if hasattr(block, 'data') and hasattr(block, 'mime_type'):
        if block.mime_type.startswith('image/'):
            # Uložit na disk
            ext = block.mime_type.split('/')[-1]
            path = upload_storage.save_bytes(
                f"generated_{uuid4().hex[:8]}.{ext}",
                base64.b64decode(block.data),
                block.mime_type,
            )
            generated_images.append(path)
```

**Codex/OpenAI**: `gpt-image-1` vrací obrázky přes tool výsledky.
Detekce v tool_calls events.

**Claude**: Nepodporuje generování obrázků — přeskočit.

### 6.2 Frontend zobrazení

V `MessageBubble.tsx`:
```tsx
{message.images?.map((img, i) => (
  <div key={i} className="mt-2 rounded-lg overflow-hidden border border-slate-mid/30">
    <img
      src={img.url}
      alt={img.filename}
      className="max-w-full max-h-96 cursor-pointer"
      onClick={() => openLightbox(img.url)}
    />
  </div>
))}
```

---

## Fáze 7: Velké soubory přes ACP `resource_link_block` ✅ HOTOVO

> Status: HOTOVO (2026-02-09)
> Aktualizováno: 2026-02-09

### Kontext a motivace

Inline base64 v ACP promptech má **praktický limit ~20 MB**. Gemini API vrací
`Internal error` pro větší payloady (~40 s čekání, pak odmítnutí).

**Původní plán** počítal s Gemini Files API (upload na Google servery, `file_uri`).
Ale OAuth token z Gemini CLI je omezený — nepřijímá ho ani REST API
`generativelanguage.googleapis.com` (403 wrong scope), ani Drive API, ani Files API.
Token funguje jen uvnitř CLI procesu.

### Objev: `resource_link_block` s `file://` URI

**Ověřeno experimentem (2026-02-09)**: ACP SDK obsahuje `resource_link_block(name, uri)`
který posílá odkaz na soubor místo inline dat. Gemini CLI pak soubor přečte z disku
samo, svým vlastním auth kontextem.

**Test s 56 MB PDF** (`Zeměpis-Evropa.pdf`):
```
resource_link_block(
    name="Zeměpis-Evropa.pdf",
    uri="file:///home/box/Downloads/Zeměpis-Evropa.pdf",
    mime_type="application/pdf",
    size=58720256,
)
```
CLI úspěšně načetlo a analyzovalo celý 50stránkový PDF s Gemini 3 Pro.
Vytvořilo kompletní obsah všech kapitol (Východní Evropa, Severní, Jižní,
Jihovýchodní, Západní, Střední Evropa — 50 stran).

### Výhody oproti Gemini Files API

| Vlastnost | Files API (starý plán) | resource_link_block (nový) |
|-----------|----------------------|---------------------------|
| Auth | Vyžaduje API klíč nebo SDK | Žádné — CLI má vlastní OAuth |
| Max velikost | 2 GB | Závisí na CLI/Gemini API limitu |
| Modely | Jen Flash (free klíč) | Jakýkoliv (včetně Gemini 3 Pro) |
| Nové závislosti | `google-genai` SDK | Žádné |
| Cache/expiry | 48h retence, URI cache | Nepotřeba — soubor na disku |
| Architektura | Nový modul `avatar_engine/files/` | Změna v jedné funkci |
| Cross-session | Komplikované (URI expiry) | Triviální (soubor vždy na disku) |

### Implementace

Jediná změna: v `_build_prompt_blocks()` (gemini.py) pro velké soubory použít
`resource_link_block` místo `embedded_blob_resource`:

```python
from acp.helpers import resource_link_block

INLINE_LIMIT_BYTES = 20 * 1024 * 1024  # ~20 MB

def _build_prompt_blocks(
    prompt: str,
    attachments: list[Attachment] | None = None,
) -> list:
    """Sestaví ACP content blocks pro prompt s přílohami."""
    blocks = []

    if attachments:
        for att in attachments:
            if att.size > INLINE_LIMIT_BYTES:
                # Velký soubor → file:// odkaz, CLI čte z disku
                blocks.append(resource_link_block(
                    name=att.filename,
                    uri=att.path.as_uri(),   # file:///path/to/file.pdf
                    mime_type=att.mime_type,
                    size=att.size,
                ))
            else:
                # Malý soubor → inline base64 (stávající logika)
                blocks.append(_inline_block(att))

    blocks.append(text_block(prompt))
    return blocks
```

**Funkce zůstává synchronní** — žádné async, žádné síťové volání.
Stávající call sites (gemini.py, codex.py) se nemusí měnit.

### Změny v error handlingu

Aktuální chování pro soubory > 20 MB:
1. Base64 inline → Gemini API vrátí "Internal error" po ~40 s
2. Bridge detekuje chybu → zobrazí "File too large" → restartuje ACP

S `resource_link_block`:
1. CLI čte soubor z disku → žádné base64 omezení
2. Chybová hláška "File too large for inline upload" se zobrazí jen pokud
   `resource_link_block` selže (fallback)

### Soubory ke změně

| # | Soubor | Změna |
|---|--------|-------|
| 1 | `avatar_engine/bridges/gemini.py` | `_build_prompt_blocks()`: threshold → `resource_link_block` |
| 2 | `avatar_engine/bridges/gemini.py` | Odebrat "File too large" error (už nepotřeba) |
| 3 | `tests/test_media_bridges.py` | Test pro `resource_link_block` generování |

### Omezení a otevřené otázky

1. **Soubor musí být na lokálním disku**: `resource_link_block` používá `file://` URI.
   Pro web GUI je to OK — soubory se uploadují do `/tmp/avatar-engine/uploads/`.
   Pro vzdálený přístup (soubor na jiném stroji) by to nefungovalo.

2. **Codex/Claude**: `resource_link_block` závisí na tom, jestli daný CLI
   implementuje čtení `file://` URI. Ověřeno pro Gemini CLI, neověřeno
   pro Claude Code a Codex. Pro tyto bridgy zůstane inline base64 s limitem.

3. **Max velikost na straně Gemini API**: CLI přečte soubor z disku, ale Gemini API
   má vlastní limity (1000 stránek PDF, 100 MB na obrázek). Tyto limity platí
   i s `resource_link_block` — jde o serverový limit, ne transportní.

4. **Obrázky a audio**: Test proběhl s PDF. Ověřit, že `resource_link_block`
   funguje i pro velké obrázky (>20 MB RAW/TIFF) a audio soubory.

5. **Timeout**: CLI zpracování velkého souboru trvá déle (56 MB PDF ≈ 5+ min).
   Dynamický timeout v `_send_acp()` už existuje (+3s/MB), ale pro
   `resource_link_block` neznáme přesnou dobu — CLI může soubor uploadovat
   interně přes Files API. Timeout zvýšit na min 10 min pro soubory > 20 MB.

### Gemini Files API — archivovaný plán (záloha)

Pokud by `resource_link_block` přestal fungovat (CLI update, ACP změna), existuje
záložní plán přes Gemini Files API s free API klíčem (ai.google.dev):

- Free API klíč: 10 RPM, 250 RPD, modely Flash (ne Pro)
- Upload až 2 GB, 48h retence, `file_uri` reference
- Vyžaduje `google-genai` SDK + URI cache + credentials management
- Viz git historie tohoto souboru pro kompletní plán

---

## Limity a omezení

| Provider | Max inline | Max s Files API | Max PDF stránek | Generování obrázků |
|---|---|---|---|---|
| Gemini | ~20 MB (base64) | 2 GB (Files API, 48h) | 1000 | Ano (Imagen, gemini-image) |
| Claude | ~10 MB (32 MB payload) | N/A | 100 | Ne |
| Codex | ~20 MB | N/A | N/A | Ano (gpt-image-1) |

**Tokeny za stránku PDF:**
- Gemini: 258 tokenů/stránka (skenovaná) — 1000 stránek = 258K tokenů (~25% 1M kontextu)
- Claude: 1500-3000 tokenů/stránka — 100 stránek = 150K-300K tokenů

**Pro skenované anglické knihy (hlavní use case):**
- Gemini je optimální volba — 1000 stránek, nízká cena za stránku
- Knihu nad 1000 stránek rozdělit na díly

---

## Změny souborů

| # | Soubor | Změna |
|---|--------|-------|
| 1 | `avatar_engine/types.py` | `Attachment` dataclass, `Message.attachments`, `BridgeResponse.generated_images` |
| 2 | `avatar_engine/bridges/base.py` | `Message.attachments`, `send(prompt, attachments)` signatura |
| 3 | `avatar_engine/bridges/gemini.py` | Multimodální ACP bloky v `_send_acp()` |
| 4 | `avatar_engine/bridges/claude.py` | `document`/`image` bloky v `_format_user_message()` |
| 5 | `avatar_engine/bridges/codex.py` | `image_block()` v ACP promptu |
| 6 | `avatar_engine/engine.py` | `chat(message, attachments)` |
| 7 | `avatar_engine/web/uploads.py` | **NOVÝ** — UploadStorage |
| 8 | `avatar_engine/web/server.py` | Upload endpoint, přílohy v chatu, static files |
| 9 | `avatar_engine/web/protocol.py` | Rozšířit `parse_client_message` pro attachments |
| 10 | `examples/web-demo/src/hooks/useFileUpload.ts` | **NOVÝ** — upload hook |
| 11 | `examples/web-demo/src/components/ChatPanel.tsx` | Drop zone, paste, file picker, preview |
| 12 | `examples/web-demo/src/hooks/useAvatarChat.ts` | Předání příloh při odeslání |
| 13 | `examples/web-demo/src/components/MessageBubble.tsx` | Zobrazení příloh + generovaných obrázků |
| 14 | `examples/web-demo/src/api/types.ts` | Typy pro attachments + images |
| 15 | `tests/test_uploads.py` | **NOVÝ** — testy pro UploadStorage |
| 16 | `tests/test_media_bridges.py` | **NOVÝ** — testy pro multimodální bridge formátování |

## Pořadí implementace

1. ~~**Fáze 1**: Datový model (Attachment, Message rozšíření) + testy~~ ✅
2. ~~**Fáze 2**: UploadStorage + REST endpoint + testy~~ ✅
3. ~~**Fáze 3**: Bridge vrstva (Gemini → Claude → Codex) + testy~~ ✅
4. ~~**Fáze 4**: WebSocket protokol rozšíření~~ ✅
5. ~~**Fáze 5**: Frontend (upload hook → drop/paste → preview → odesílání)~~ ✅
6. **Fáze 6**: Image generation — částečně (extrakce + zobrazení funguje, dedikované flow chybí)
7. **Fáze 7**: Gemini Files API — naplánováno, neimplementováno

## Ověření

1. ✅ `uv run pytest` — 911 testů prochází (včetně 8 nových upload integračních testů)
2. ✅ Web UI: drag & drop obrázku → zobrazí se náhled → odeslání → Gemini analyzuje
3. ✅ Web UI: upload PDF (do ~20 MB) → Gemini analyzuje
4. ✅ Web UI: Ctrl+V screenshot → upload + analýza
5. ⬜ Web UI: přepnutí na Claude → PDF jako document block (netestováno)
6. ⬜ Web UI: image generation prompt → obrázek v chatu (netestováno end-to-end)
7. ✅ Web UI: soubor 56 MB → srozumitelná chybová hláška "File too large for inline upload"
8. ✅ Po chybě velkého souboru ACP se restartuje, další zprávy fungují normálně
9. ✅ Dynamické timeouty na všech vrstvách (bridge, server, frontend)
