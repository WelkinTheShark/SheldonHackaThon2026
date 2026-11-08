# CaveDawg Design System & Style Guide
**"The Fire in the Cave" — Primordial Brutalism & Silicon Telemetry**  
*A Zero-Dependency Frontend Specification for FastAPI (`app/static/`) and Claude Code*

---

## 1. Executive Philosophy & Thematic Tension

CaveDawg is a lightweight, local-first cost-control proxy and gateway for the Claude API and Claude Code. The aesthetic balances **primordial shelter** (African sandstone, iron-oxide haematite ochre, painted wild dogs) with **hyper-precise silicon telemetry** (tabular monospaced metrics, micro-badges, and live token diff receipts).

### Core Directives
1. **Zero Build Pipelines, Zero npm Dependencies**: Native HTML5, CSS3, and vanilla JS served directly from FastAPI in `app/static/`. Sub-10ms initial paint.
2. **Clean Minimalist Brutalism**: Every element serves an operational purpose. Clean rectangular containers with crisp 1px hairline strokes. **No jagged fissures, no faux-stone bevels, and no cartoon skeuomorphism.**
3. **100% Matte Mineral Surfaces**: Pure matte dark stone substrates (`#0c0a09` / `#14110f`). **Zero neon glows, zero cyan bloom, and zero glossy glassmorphism.**
4. **Tabular Data Fidelity**: Telemetry numbers never jitter or wobble during live streaming. Strict monospaced alignment with tabular numerals (`tnum`).

---

## 2. The Color System (Mineral & Silicon)

```
+---------------------------------------------------------------------------------------+
| TOKEN NAME             | HEX CODE | ROLE / SEMANTIC MEANING                           |
+------------------------+----------+---------------------------------------------------+
| --bg-obsidian          | #0c0a09  | Volcanic glass; root canvas background (Stone 950)|
| --bg-slate-card        | #14110f  | Chiseled basalt; primary panel / card surface     |
| --bg-slate-elevated    | #1e1916  | Raised surface; hover states & interactive cells  |
| --bg-slate-recessed    | #0e0c0a  | Recessed terminal cells, diff blocks, code pads   |
| --border-sandstone     | #261e19  | 1px hairline sandstone border stroke              |
| --border-sandstone-lit | #382e27  | Active, focused, or hovered container border      |
| --pigment-ochre        | #c2410c  | Ancestral red iron oxide; kill-switch & alerts    |
| --pigment-sandstone    | #b45309  | Limonite amber; active triage & cost warnings     |
| --pigment-circuit-gold | #f59e0b  | Golden PCB circuit traces in brand mark           |
| --pigment-malachite    | #10b981  | Silicon emerald / copper ore; verified savings    |
| --text-chalk           | #fafaf9  | High-contrast dry calcite chalk; headers & digits |
| --text-bone            | #e7e5e4  | Unbleached linen; primary readable UI text        |
| --text-granite         | #a8a29e  | Crushed granite; secondary labels & metadata      |
| --text-charcoal        | #78716c  | Charcoal smoke; timestamps & strikethrough waste  |
+---------------------------------------------------------------------------------------+
```

---

## 3. Typography Rules

### Font Families
```css
/* UI Proportional Font (Immediate load, zero layout shift) */
--font-sans: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;

/* Telemetry Monospace (Receipts, code, tokens, diffs) */
--font-mono: "JetBrains Mono", ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
```

### Tabular Number Alignment
All live metric cards, tables, and counters **must** enforce tabular figure settings to prevent layout shift during socket updates:
```css
.font-mono {
  font-family: var(--font-mono);
  font-feature-settings: "tnum" 1, "zero" 1;
  font-variant-numeric: tabular-nums lining-nums;
  letter-spacing: -0.015em;
}
```

---

## 4. Layout & Structural Principles

1. **Card Architecture**:
   * Background: `var(--bg-slate-card)` (`#14110f`).
   * Border: `1px solid var(--border-sandstone)` (`#261e19`).
   * Radius: `2px` micro-chamfer (`--radius-card: 2px`). Strictly no bubbly `rounded-lg` or `rounded-2xl`.
2. **Subtle Cave Perimeter Frame**:
   * Viewport perimeter carries a subtle multi-stop vignette simulating a natural rock shelter opening:
     ```css
     .cave-perimeter-frame {
       position: fixed; inset: 0; pointer-events: none; z-index: 998;
       box-shadow: 
         inset 0 0 50px 15px rgba(8, 7, 6, 0.95),
         inset 0 0 130px 45px rgba(6, 5, 4, 0.75),
         inset 0 0 220px 85px rgba(0, 0, 0, 0.60);
     }
     ```
3. **Surface Texture**:
   * An ultra-lightweight inline SVG noise overlay (200 bytes, `feTurbulence`, 3% opacity) applied to `body`.

---

## 5. Signature Component Specifications

### Archetype 1: The Zero-Dependency Logo
The official brand mark pairs the **African Painted Wild Dog (*Lycaon pictus*)** with **fine PCB circuit traces** and petroglyphic typography:

```html
<svg width="220" height="48" viewBox="0 0 240 52" fill="none" xmlns="http://www.w3.org/2000/svg">
  <!-- Golden Circuit Board Traces & Vias Behind Dog -->
  <path d="M70 26H110L125 14H165M110 26L120 36H170M125 14L135 6H185M90 26V44H140" stroke="#f59e0b" stroke-width="1.2" stroke-linecap="round"/>
  <circle cx="165" cy="14" r="2" fill="#f59e0b"/>
  <circle cx="170" cy="36" r="2" fill="#f59e0b"/>
  <circle cx="185" cy="6" r="2" fill="#f59e0b"/>
  <circle cx="140" cy="44" r="2" fill="#f59e0b"/>
  <circle cx="70" cy="26" r="2" fill="#f59e0b"/>

  <!-- African Wild Dog Silhouette in Red Ochre & Dark Basalt -->
  <path d="M25 32C28 28 38 27 52 27C62 27 74 30 80 26C85 23 88 18 92 14C94 11 98 8 101 6C103 8 102 12 99 14C95 17 91 21 86 24L90 42M84 24L80 40M64 23L58 41M61 23L54 39M25 32C20 27 16 22 18 16M16 16C12 21 10 28 15 33" stroke="#c2410c" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/>
  <!-- Rounded Ears of the Wild Dog -->
  <path d="M86 12C84 6 88 1 92 2C96 3 95 9 92 15" fill="#c2410c" stroke="#14110f" stroke-width="1.5"/>
  <path d="M91 12C92 5 96 0 100 1C104 2 103 8 98 13" fill="#c2410c" stroke="#14110f" stroke-width="1.5"/>
  <!-- Calico Markings -->
  <path d="M40 29C45 27 50 29 55 27C58 31 52 34 46 33Z" fill="#14110f"/>
  <path d="M68 29C72 27 76 30 80 28C81 32 76 34 71 33Z" fill="#14110f"/>

  <!-- Chiseled "CAVEDAWG" Wordmark -->
  <text x="120" y="38" font-family="'JetBrains Mono', monospace" font-size="16" font-weight="900" fill="#fafaf9" letter-spacing="1.2">CAVEDAWG</text>
</svg>
```

### Archetype 2: The Proof Matrix
Side-by-side ledger proving token downshift savings:
* Raw requested cost: `.strike-waste` (`color: #ef4444; text-decoration: line-through; font-weight: 600;`).
* Intercepted downshift cost: `.text-chalk` (`color: #fafaf9; font-weight: 700;`).
* Savings badge: `.badge-mineral.badge-malachite` (`background: #092c20; color: #34d399; border: 1px solid #10b981;`).

### Archetype 3: The 15-Second Stranger Demo Bar
Sticky top action strip positioned directly below the header:
* Amber torch indicator: 7px square dot (`background-color: var(--pigment-sandstone);`).
* 3 preset buttons: `.btn-telemetry.btn-ochre`, `.btn-amber`, `.btn-malachite`.
* Trigger handlers: Instantly pushes simulated live downshift receipts, loop breaker halts, and cache hits.

### Archetype 4: The Team Spend Podium with `may_swap`
Developer token spend allocation meter with a physical-style 1-click rocker toggle:
```html
<label class="toggle-switch">
  <input type="checkbox" checked onchange="toggleSwap('alex', this.checked)">
  <span class="toggle-slider"></span>
</label>
```

---

## 6. Rules for Claude Code Generation

When prompting or steering Claude Code to build features for CaveDawg, adhere to these strict rules:

### DO:
* Use native CSS custom properties defined in `cavedawg.css`.
* Wrap all cards in `<div class="card-telemetry">` or `<div class="card-telemetry ochre-top">`.
* Align all numbers, metrics, and timestamps using `.font-mono` and `.tabular-nums`.
* Deliver clean semantic HTML and vanilla JavaScript without external npm dependencies.

### DO NOT:
* **DO NOT** add rounded pill classes (`rounded-full`, `rounded-xl`, `rounded-2xl`). Use 2px radius.
* **DO NOT** add `box-shadow` neon glows, cyan blooms, or glassmorphic blurs (`backdrop-filter: blur(...)`).
* **DO NOT** introduce jagged or broken SVG border fissures. Use crisp 1px hairline borders.
* **DO NOT** import external libraries (e.g. Lucide, FontAwesome, Tailwind CDN, Three.js).
* **DO NOT** use pure `#000000` or `#ffffff`. Use `#0c0a09` (Obsidian) and `#fafaf9` (Calcite Chalk).
