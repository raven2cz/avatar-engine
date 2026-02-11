# Avatar GUI: Compact Companion Drawer + Animated Bust

**Status:** SCHVÁLENO — Varianta A zvolena
**Branch:** `feature/avatar-gui-compact-mode`
**Datum:** 2026-02-11
**Referenční mockup:** `plans/mockups/variant-a-polished.html`

---

## Rozhodnutí

**Zvolena Varianta A: "Companion Drawer"** — drawer zdola s avatarem vlevo, chat vpravo.
Varianty B a C zamítnuty. Polished HTML mockup slouží jako pixel-perfect reference
pro barvy, rozměry, animace a UX chování.

---

## Architektonický princip: ADITIVNÍ INTEGRACE

```
NESMÍ se měnit (existující jádro):
  ├── useAvatarChat.ts         ← message state machine
  ├── useAvatarWebSocket.ts    ← WS reducer + reconnect
  ├── useFileUpload.ts         ← upload flow
  ├── ChatPanel.tsx            ← message list + input (fullscreen)
  ├── MessageBubble.tsx        ← message rendering
  ├── MarkdownContent.tsx      ← markdown parser
  ├── BreathingOrb.tsx         ← galaxie animace (ZACHOVAT!)
  ├── ThinkingIndicator.tsx    ← thinking fáze display
  ├── ToolActivity.tsx         ← tool execution tracker
  ├── StatusBar.tsx            ← header s provider/model/session
  ├── SessionPanel.tsx         ← session management modal
  ├── ProviderModelSelector.tsx← provider/model dropdown
  ├── CostTracker.tsx          ← cost footer
  └── tailwind.config.js       ← theme barvy + animace (pouze přidat, ne měnit)

PŘIDÁVÁME (nová vrstva):
  ├── AvatarWidget.tsx         ← master container (fab/compact/fullscreen)
  ├── AvatarFab.tsx            ← FAB tlačítko (subtilní, tmavé)
  ├── AvatarBust.tsx           ← bust + sprite sheet engine + animace
  ├── CompactChat.tsx          ← kompaktní chat (menší fonty, zjednodušený)
  ├── AvatarPicker.tsx         ← popup pro výběr postavy
  ├── useWidgetMode.ts         ← state machine: fab ↔ compact ↔ fullscreen
  ├── useAvatarBust.ts         ← mapování engineState → bust stav
  └── avatars.ts               ← konfigurace předdefinovaných avatarů
```

### Klíčové pravidlo

**Fullscreen režim = současná aplikace beze změn.** `AvatarWidget` pouze
obaluje stávající `<App>` obsah. Galaxie animace (`BreathingOrb`), message flow,
thinking indicator, tool activity — vše zůstává.

**Compact režim = NOVÝ zjednodušený pohled** na stejná data (`messages[]`,
`engineState`, `cost` atd.) z `useAvatarChat`. Sdílí data, NE komponenty —
compact má vlastní, menší UI.

---

## Tři režimy zobrazení

```
   ┌──────── FAB click ────────┐
   ↓                            │ křížek / Esc
 [FAB]                      [COMPACT]
   60% opacity, tmavý           │ drawer zdola, max-width ~1030px
   hover → 100%                 │ resizable výška + šířka
                                │
                            expand tlačítko / Ctrl+Shift+F
                                ↓
                          [FULLSCREEN]
                             současná App beze změn
                             Compact tlačítko / Esc → zpět
```

---

## Compact mode — designové zásady

Compact mode je ODLIŠNÝ od fullscreenu. Menší, skromnější, nebere pozornost:

| Vlastnost | Fullscreen | Compact |
|-----------|-----------|---------|
| Fonty zpráv | 0.82rem | 0.75rem |
| Message avatary | 26px | 20px |
| Padding zpráv | 10px 14px | 6px 10px |
| BreathingOrb | ANO (galaxie) | NE (jen bust animace) |
| ThinkingIndicator | Plný s fází | Zjednodušený (3 tečky) |
| ToolActivity | Plný seznam | Počet + ikona |
| StatusBar | Plný header | Minimální (provider badge + controls) |
| Code bloky | Plné + syntax hl. | Menší font, zachovat hl. |
| CostTracker | Footer | Skrytý (viditelný ve fullscreenu) |
| Markdown | Plný render | Plný render (menší fonty) |
| Session panel | Modal | Přístupný přes fullscreen |
| File upload | Preview + progress | Malá ikona + jméno |
| Scrollbar | 6px nativní | 8px nativní, inset thumb |
| Max šířka chatu | 800px (fs-messages) | var(--compact-width, 1030px) |
| Výchozí výška | - | Zarovnáno s horní hranou bustu |

### Compact layout (z mockupu)

```
┌────────────────────────────────────────────────────────────────────┐
│                     HOST APLIKACE                                  │
│                 (zbytek webu / IDE / cokoliv)                      │
├──────┬────────────── vroubkování ──────────────────────┬───────────┤
│      │ [●Gemini] gemini-3-pro  [Přemýšlím...]   [□][×]│           │
│ ╔══╗ │ ┌──────────────────────────────────────────┐ ▐ │ ║vroubk.║ │
│ ║  ║ │ │ AI: Ahoj! Jak ti mohu pomoci?            │ ▐ │ ║       ║ │
│ ║B ║ │ │ User: Napiš mi sort                      │ ▐ │ ║       ║ │
│ ║U ║ │ │ AI: Tady je implementace...               │ ▐ │ ║       ║ │
│ ║S ║ │ │                                          │ ▐ │ ║       ║ │
│ ║T ║ │ ├──────────────────────────────────────────┤   │           │
│ ║  ║ │ │ [📎] Napiš zprávu...              [➤]   │   │           │
│ ╚══╝ │ └──────────────────────────────────────────┘   │           │
│▓▓▓▓▓▓│  pill                                         │           │
└──────┴────────────────────────────────────────────────┴───────────┘
```

- **Horní resize** — vroubkování, `cursor: ns-resize`, libovolná výška
- **Pravý resize** — vertikální vroubkování, `cursor: ew-resize`, min 530px
- **Pill toggle** — 20×40px vroubkový grip na levé hraně chatu, hover opacity
- **Bust area** — 230px fixní šířka, bust `left:14px, translateY:2.8%`
- **Char picker** — 32px kruhové tlačítko, click/drag pattern, portrait thumbnaily 48×72

---

## Avatar Bust System

### Stavový automat

```
engineState (z WebSocket)     →    bustState (vizuální)
─────────────────────────────────────────────────────────
'idle'                        →    idle (breathe animace)
'thinking'                    →    thinking (pohupování + synapse glow)
'responding'                  →    speaking (sprite sheet ping-pong + pulse glow)
'tool_executing'              →    thinking (pohupování + neural glow)
'waiting_approval'            →    idle (breathe + amber glow)
'error'                       →    error (shake + rose glow)
```

### Sprite sheet engine

```
Horizontální strip: [Frame0][Frame1][Frame2][Frame3]
                     Idle    Mírně   Otevř.  Široce
                     ústa    otevř.  ústa    otevř.

Extrakce: canvas per frame, frameW = img.width / frameCount
Ping-pong: 0→1→2→3→2→1→0... @ 120ms/frame (8fps)
Speaking frames: [1,2,3] (frame 0 = idle)
```

### CSS animace bustu

Všechny keyframes používají `translateY(${bustTranslateY}%)` a přepisují se
dynamicky při drag-posun bustu (viz mockup, `updateBustAnimationKeyframes()`).

```
bust-breathe    3.5s ease-in-out infinite   scale(1→1.006), translateY(-4px)
bust-thinking   3.0s ease-in-out infinite   rotate(±1.2°), translateY(-7px)
bust-speaking   2.0s ease-in-out infinite   scale(1→1.015)
bust-shake      0.6s ease-in-out once       translateX(±8px)
bust-glow       pod bustem, radial-gradient, blur(10px)
```

### Předdefinovaní avataři (z kokoro-dubber)

| ID | Jméno | Sprite sheet | Rozměry framu |
|----|-------|-------------|---------------|
| `bella` | Bella | `af_bella.webp` | 200×359 |
| `heart` | Heart | `af_heart.webp` | 200×331 |
| `adam`  | Adam  | `am_adam.webp`  | 200×311 |

Soubory v `plans/mockups/busts/` (800px wide resized), base64 data v `bust-data.js`.
Pro produkci: přesunout do `public/avatars/` jako WebP soubory.

---

## FAB tlačítko

Z mockupu — subtilní, tmavé, neruší:

```css
background: var(--slate-dark);
border: 1px solid var(--glass-border);
opacity: 0.6;                           /* default */
opacity: 1;                             /* hover */
width: 80px; height: 80px;
border-radius: 50%;
```

Canvas uvnitř — čtvercový crop obličeje z frame 0, circle clip, 72×72px.

---

## Klávesové zkratky

| Zkratka | Akce | Kontext |
|---------|------|---------|
| `Escape` | Compact → FAB / Fullscreen → Compact | Globální |
| `Ctrl+Shift+A` | Toggle compact (FAB ↔ Compact) | Globální |
| `Ctrl+Shift+F` | Toggle fullscreen | Compact/Fullscreen |
| `Ctrl+Shift+H` | Toggle viditelnost bustu | Compact |
| `Enter` | Odeslat zprávu | Chat input (existující) |
| `Shift+Enter` | Nový řádek | Chat input (existující) |

---

## Persistence (localStorage)

| Klíč | Hodnota | Default |
|------|---------|---------|
| `avatar-engine-bust-visible` | `'0'` / `'1'` | `'1'` |
| `avatar-engine-widget-mode` | `'fab'`/`'compact'`/`'fullscreen'` | `'fab'` |
| `avatar-engine-compact-height` | px číslo | auto (výška bustu) |
| `avatar-engine-compact-width` | px číslo | `1030` |
| `avatar-engine-selected-avatar` | avatar ID | `'bella'` |

---

## Nové soubory

```
examples/web-demo/src/
  ├── components/
  │   ├── AvatarWidget.tsx          ← Master container, mode state machine
  │   ├── AvatarFab.tsx             ← FAB button (80px, dark, opacity 0.6)
  │   ├── AvatarBust.tsx            ← Bust render + sprite sheet + animace
  │   ├── AvatarPicker.tsx          ← Character picker popup (portrait thumbs)
  │   ├── CompactChat.tsx           ← Compact chat (menší fonty, zjednodušený)
  │   ├── CompactHeader.tsx         ← Minimální header (provider badge + controls)
  │   ├── CompactMessages.tsx       ← Message list (compact styling)
  │   └── CompactInput.tsx          ← Input area (compact)
  ├── hooks/
  │   ├── useWidgetMode.ts          ← fab↔compact↔fullscreen + localStorage
  │   └── useAvatarBust.ts          ← engineState→bustState + sprite sheet engine
  ├── config/
  │   └── avatars.ts                ← Avatar definice (bella, heart, adam)
  └── types/
      └── avatar.ts                 ← AvatarConfig, BustState, WidgetMode

examples/web-demo/public/avatars/
  ├── bella/
  │   └── speaking.webp             ← 4-frame sprite sheet
  ├── heart/
  │   └── speaking.webp
  └── adam/
      └── speaking.webp
```

### Modifikované soubory (minimální zásahy)

```
src/App.tsx
  ← Obalit celý obsah do <AvatarWidget>
  ← Předat useAvatarChat() výstupy jako props widgetu
  ← Fullscreen obsah zůstává BEZE ZMĚN

src/index.css
  ← Přidat compact-mode utility třídy (compact font sizes, padding)

tailwind.config.js
  ← Přidat bust animace (bust-breathe, bust-thinking, bust-speaking, bust-shake)
  ← NEMĚNIT stávající galaxie animace!
```

---

## Implementační fáze

### Fáze 1: Widget Container + Mode Switching
1. Vytvořit `useWidgetMode.ts` — state machine fab↔compact↔fullscreen
2. Vytvořit `AvatarWidget.tsx` — `position:fixed` container
3. Upravit `App.tsx` — obalit do widgetu, předat chat props
4. Implementovat FAB (`AvatarFab.tsx`) — tmavý kruhový button
5. Implementovat přechody (CSS transitions, drawer slide-up)
6. Klávesové zkratky (Escape, Ctrl+Shift+A, Ctrl+Shift+F)
7. Persistence režimu do localStorage

### Fáze 2: Avatar Bust System
1. Vytvořit `useAvatarBust.ts` — mapování engineState→bustState
2. Vytvořit `AvatarBust.tsx` — canvas rendering, sprite sheet extrakce
3. Implementovat ping-pong speaking animaci (120ms/frame)
4. CSS keyframes animace (breathe, thinking, speaking, shake)
5. Glow efekt pod bustem (radial-gradient, blur)
6. Přidat bust animace do `tailwind.config.js`

### Fáze 3: Compact Chat
1. Vytvořit `CompactHeader.tsx` — provider badge, state badge, fullscreen/close
2. Vytvořit `CompactMessages.tsx` — message list s menšími fonty
3. Vytvořit `CompactInput.tsx` — textarea + send/attach
4. Vytvořit `CompactChat.tsx` — container s header/messages/input
5. Napojit na `useAvatarChat` data (messages, sendMessage, atd.)
6. Nativní CSS scrollbar (8px, inset thumb, hover highlight)

### Fáze 4: Resize + Bust Area
1. Resize handle horní (vroubkování, ns-resize)
2. Resize handle pravý (vertikální vroubkování, ew-resize)
3. Drawer max-width s CSS variable `--compact-width`
4. Bust area (230px, overflow visible pro bust nad drawer)
5. Pill toggle (20×40px grip, avatar hide/show, localStorage persist)
6. Výchozí výška zarovnaná s horní hranou bustu

### Fáze 5: Avatar Picker + Config
1. Vytvořit `AvatarPicker.tsx` — portrait thumbnaily (48×72px)
2. Character switching (re-render bust + FAB thumb)
3. Click-vs-drag pattern na picker buttonu
4. Avatar volba persist do localStorage
5. Přesunout sprite sheet assety do `public/avatars/`

### Fáze 6: Polish
1. Responsive breakpoints (< 768px: bust hidden, FAB menší)
2. Accessibility (aria labels, focus trap v compact)
3. Performance (lazy load sprite sheets, will-change hints)
4. Testování na 4K (max-width constraint)
5. Edge cases (příliš malé okno, přechod compact↔fullscreen se ztrátou stavu)

---

## Závislosti

- **Žádné nové** — vše řešeno nativním CSS + React
  - Animace: CSS keyframes (ne Framer Motion — zbytečná závislost)
  - Sprite sheet: HTML5 Canvas
  - Resize: mousedown/mousemove/mouseup
  - Persistence: localStorage

---

## Mockupy

| Soubor | Popis | Status |
|--------|-------|--------|
| `plans/mockups/variant-a-polished.html` | **REFERENČNÍ** — pixel-perfect demo | HOTOVO |
| `plans/mockups/bust-data.js` | Base64 sprite sheet data (3 avatary) | HOTOVO |
| `plans/mockups/busts/` | Resized WebP sprite sheets | HOTOVO |
| `plans/mockups/variant-a-companion-drawer.html` | Původní návrh A | ARCHIV |
| `plans/mockups/variant-b-floating-island.html` | Zamítnutá varianta B | ARCHIV |
| `plans/mockups/variant-c-stage-mode.html` | Zamítnutá varianta C | ARCHIV |
