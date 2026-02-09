# Plán: Media Input & Image Generation

> Status: IMPLEMENTOVÁNO (Fáze 1–5 hotové, Fáze 6 částečně, Fáze 7 naplánovaná)
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

## Fáze 7 (budoucí): Gemini Files API pro velké soubory

> Status: NAPLÁNOVÁNO — implementace odložena
> Aktualizováno: 2026-02-09

### Kontext a motivace

Inline base64 v ACP promptech má **praktický limit ~20 MB** (ne 50 MB jak uvádí
dokumentace). Gemini API vrací `Internal error` pro inline base64 payloady překračující
tento limit — chyba přijde po ~40 s a není to timeout, ale odmítnutí na straně API.

Aktuální stav (implementováno ve Fázi 6):
- Soubory ≤ ~20 MB: fungují přes inline base64 v ACP promptu
- Soubory > ~20 MB: srozumitelná chybová zpráva uživateli s vysvětlením limitu
- Session zůstane v READY stavu (obnovitelná chyba)

**Gemini Files API** umožňuje upload až **2 GB** na servery Google s 48h retencí.
Soubor dostane URI (`files/abc123`), které lze použít v libovolném promptu místo base64.

### Klíčové vlastnosti Gemini Files API

| Vlastnost | Hodnota |
|-----------|---------|
| Max velikost | 2 GB |
| Retence | 48 hodin od uploadu |
| URI formát | `files/<id>` (např. `files/abc123xyz`) |
| Scope | **Session-independent** — URI lze použít v jakémkoliv promptu, jakékoliv session |
| Autentizace | Google OAuth token (stejný jako Gemini CLI) |
| SDK | `google-genai` Python package |

### Architektura

```
avatar_engine/files/
    __init__.py          # Public API: get_or_upload(path, provider) → file_uri | None
    _cache.py            # FileURICache — disk-persisted cache s TTL
    _gemini_upload.py    # GeminiFilesUploader — upload + polling stavu
```

### Automatický threshold

```python
INLINE_LIMIT_MB = 20  # Praktický limit pro base64 inline

def should_use_files_api(attachment: UploadedFile) -> bool:
    """Soubory > 20 MB automaticky přes Files API, menší inline."""
    return attachment.size > INLINE_LIMIT_MB * 1024 * 1024
```

V `_build_prompt_blocks()` (gemini.py):
- Pokud `should_use_files_api(att)` → použít `file_uri` z cache/uploadu
- Jinak → stávající inline base64 (`embedded_blob_resource`)

### URI Cache — sdílená napříč sessions

Cache mapuje lokální soubor na vzdálené URI:

```python
@dataclass
class CachedFileURI:
    file_uri: str           # "files/abc123xyz"
    local_path: str         # "/home/user/docs/huge.pdf"
    sha256: str             # Hash obsahu souboru
    size_bytes: int         # Velikost souboru
    uploaded_at: float      # Unix timestamp uploadu
    expires_at: float       # uploaded_at + 48h (172800s)
    mime_type: str          # "application/pdf"

class FileURICache:
    """Disk-persisted cache: (local_path, sha256) → CachedFileURI"""

    def __init__(self, cache_dir: Path = Path("~/.avatar-engine/file-cache")):
        self._cache_dir = cache_dir.expanduser()
        self._cache_file = self._cache_dir / "uri_cache.json"

    def get(self, path: str, sha256: str) -> str | None:
        """Vrátí URI pokud existuje a nevypršelo, jinak None."""

    def put(self, entry: CachedFileURI) -> None:
        """Uloží URI do cache na disk."""

    def evict_expired(self) -> int:
        """Smaže všechny expired záznamy, vrátí počet smazaných."""
```

**Klíčový princip**: Cache klíčem je `(local_path, sha256)` — pokud se soubor změní
(jiný hash), stará URI se nepoužije a provede se nový upload.

**Persistence na disku**: `~/.avatar-engine/file-cache/uri_cache.json` — přežije
restart serveru, restart CLI. Cache se načte při prvním volání.

**TTL**: 48h od uploadu. Při `get()` se kontroluje `expires_at` — pokud < now,
záznam se automaticky smaže a vrátí None (trigger re-upload).

**Safety margin**: Nastavit expiry na 47h místo 48h — bezpečnostní marže, aby URI
nevypršelo uprostřed dlouhého promptu.

### Upload flow

```python
class GeminiFilesUploader:
    """Upload souborů přes Gemini Files API."""

    def __init__(self, cache: FileURICache):
        self._cache = cache
        self._client: genai.Client | None = None

    async def get_or_upload(self, attachment: UploadedFile) -> str:
        """Vrátí file_uri — z cache nebo po uploadu."""
        sha256 = compute_sha256(attachment.path)

        # 1. Zkusit cache
        cached = self._cache.get(str(attachment.path), sha256)
        if cached:
            return cached

        # 2. Upload
        client = self._get_client()
        uploaded = client.files.upload(
            file=str(attachment.path),
            config={"mime_type": attachment.mime_type},
        )

        # 3. Polling — čekat na ACTIVE stav (velké soubory se procesují)
        while uploaded.state == "PROCESSING":
            await asyncio.sleep(2)
            uploaded = client.files.get(name=uploaded.name)

        if uploaded.state != "ACTIVE":
            raise RuntimeError(f"File upload failed: {uploaded.state}")

        # 4. Uložit do cache
        self._cache.put(CachedFileURI(
            file_uri=uploaded.uri,
            local_path=str(attachment.path),
            sha256=sha256,
            size_bytes=attachment.size,
            uploaded_at=time.time(),
            expires_at=time.time() + 47 * 3600,  # 47h safety margin
            mime_type=attachment.mime_type,
        ))

        return uploaded.uri
```

### Autentizace — reuse OAuth tokenu z Gemini CLI

Gemini CLI ukládá OAuth credentials v `~/.gemini/google_accounts.json`:

```json
{
  "accounts": [{
    "auth_credential": {
      "oauth2": {
        "client_id": "...",
        "client_secret": "...",
        "refresh_token": "..."
      }
    }
  }]
}
```

`GeminiFilesUploader._get_client()` načte tyto credentials a vytvoří `genai.Client`
bez potřeby samostatného API klíče. Pokud soubor neexistuje, Files API není dostupné
(graceful degradation — zůstane inline limit 20 MB).

### Cross-session přenos souborů

**URI je session-independent** — soubor uploadovaný v session A je dostupný v session B,
C, i v CLI režimu. URI žije na serverech Google 48h od uploadu, nezávisle na session.

**Use-cases:**

1. **Stejná session, opakované dotazy**: Upload jednou, URI z cache se použije
   pro všechny následující prompty ve stejné session.

2. **Jiná session, stejný soubor**: Uživatel otevře novou session a přetáhne
   stejný PDF → cache hit (path + sha256 se shodují) → žádný re-upload.

3. **Jiná session, jiný stroj**: Cache je lokální na disk. Na jiném stroji
   se provede nový upload (cache miss).

4. **Po 48h**: Cache entry expired → automatický re-upload při dalším použití.

5. **Session resume s referencí na soubor**: Při resume se historie načte
   z filesystému (Fáze 15). Pokud historie obsahuje file_uri reference,
   tyto URI mohou být expired. Řešení:
   - Při resume detekovat `files/` URI v historii
   - Zkontrolovat cache — pokud expired, zobrazit upozornění uživateli
   - NEPOKOUŠET SE automaticky re-uploadovat (soubor mohl být smazán/změněn)

### Integrace do `_build_prompt_blocks()`

```python
async def _build_prompt_blocks(
    prompt: str,
    attachments: list[UploadedFile] | None = None,
    uploader: GeminiFilesUploader | None = None,  # NOVÝ parametr
) -> list:
    """Sestaví ACP content blocks — s automatickým Files API pro velké soubory."""
    blocks = [text_block(prompt)]
    if not attachments:
        return blocks

    for att in attachments:
        if uploader and should_use_files_api(att):
            # Velký soubor → Files API
            file_uri = await uploader.get_or_upload(att)
            # ACP resource_block s URI (TBD: závisí na ACP SDK podpoře file_uri)
            blocks.append(resource_block(uri=file_uri, mime_type=att.mime_type))
        else:
            # Malý soubor → inline base64 (stávající logika)
            blocks.append(_inline_block(att))

    return blocks
```

**Poznámka**: `_build_prompt_blocks` se změní na `async` — nutné aktualizovat
všechny call sites (gemini.py, codex.py).

### Závislosti

```toml
[project.optional-dependencies]
gemini-files = ["google-genai>=1.0"]
```

Volitelná závislost — pokud `google-genai` není nainstalované, Files API
není dostupné a platí inline limit 20 MB.

### Otevřené otázky k dořešení

1. **ACP SDK podpora file_uri**: Má ACP `resource_block()` parametr pro file URI,
   nebo je potřeba bypass ACP a volat Gemini API přímo?

2. **Codex/Claude**: Files API je specifické pro Gemini. Pro Claude existuje
   podobný limit (~32 MB) ale bez Files API alternativy. Pro Codex nemá inline
   base64 praktický problém (OpenAI API akceptuje větší payloady).

3. **Progress indikátor**: Upload 2 GB souboru trvá minuty. Frontend by měl
   zobrazovat progress bar s procentuální indikací.

4. **Concurrent uploads**: Pokud uživatel přetáhne 5 velkých souborů najednou,
   měly by se uploadovat paralelně (asyncio.gather) s limitem concurrency.

5. **Čištění cache**: Automatické `evict_expired()` při startu serveru +
   periodicky (např. co hodinu). Nebo lazy při každém `get()` volání.

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
