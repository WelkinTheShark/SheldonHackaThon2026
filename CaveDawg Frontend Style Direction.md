# CaveDawg: Cave Art to Frontend Style System
## Recommended direction
**Use the reference as a brand language, not as a literal interface background.** The recommended direction, **Painted Signal**, combines warm charcoal surfaces, bone-colored text, ochre accents, an ember primary action, and restrained circuit-line decoration. The supplied image contributes the dog silhouette, mineral palette, painted marks, warm lighting, and the juxtaposition of prehistoric imagery with circuitry.[^1]

The design principle is **a modern developer dashboard with a cave-painted identity**. Most of the working interface should remain flat, legible, and familiar; concentrate the expressive treatment in the brand, header, sign-in experience, and selected illustration areas. These are proposed design decisions, not historical claims about cave art.
## Repository basis
The supplied address ends in `SheldonHackaThon202`. The public repository inspected was [SheldonHackaThon2026](https://github.com/WelkinTheShark/SheldonHackaThon2026), consistent with the earlier CaveDawg project context. The reviewed revision was `8e216869d8ac6f83fa51afcf19b185ca2b8381b4`; this is a point-in-time source review, not verification of a deployed instance.[^2]

The frontend is plain HTML, CSS, and JavaScript under `app/static`, with Barlow and Barlow Condensed already loaded. Its existing hierarchy places spend and budget first, followed by the call composer, live-call ledger, roast results, leaderboard, and user administration. [Source: HTML](https://github.com/WelkinTheShark/SheldonHackaThon2026/blob/8e216869d8ac6f83fa51afcf19b185ca2b8381b4/app/static/index.html)

The current stylesheet uses pale blue-gray surfaces, navy typography, angular controls, and rotated status stamps. Its CSS variables and component classes provide a straightforward place to introduce a theme without changing the application's architecture. [Source: stylesheet](https://github.com/WelkinTheShark/SheldonHackaThon2026/blob/8e216869d8ac6f83fa51afcf19b185ca2b8381b4/app/static/style.css)

**Scope boundary:** the accompanying stylesheet is a proposed override layer. No changes have been pushed to the repository, and no backend functionality has been altered.
## Adopt, adapt, or omit
The reference-image observations below come from the supplied CaveDawg artwork; the implementation choices are recommendations.[^1]

| Reference element | Decision | Frontend translation | Guardrail |
|---|---|---|---|
| Black and rust dog silhouette | Adopt | A compact, standalone brand mark; a larger version can appear at sign-in | Do not put the entire rectangular artwork into a tiny navbar logo |
| Ochre, charcoal, rust, and sand palette | Adopt | Charcoal canvas, bone text, warm accent hierarchy | Do not use every warm color at equal intensity |
| Gold circuit traces | Adopt selectively | Thin header decoration; optional routing illustration | Decoration must not look like live telemetry or an interactive control |
| Painted, slightly imperfect edges | Adapt | Express through the logo, a divider, or empty-state artwork | Keep table rules, field outlines, and text crisp |
| Rock-wall surface | Adapt heavily | Optional subdued brand-area texture, outside working surfaces | No texture behind tables, prompts, totals, or error messages |
| Torch-like warm lighting | Adapt | A restrained static radial glow in the application shell | No flickering, roaming lights, or continuous animation |
| Carved CaveDawg lettering | Brand-only | Keep in promotional artwork or a separately prepared wordmark | Do not use a carved or runic face for headings, fields, or numbers |
| Large animal illustration | Brand moments | Sign-in, onboarding, presentation slides, or a deliberate empty state | Do not spend the dashboard's primary screen space on a mascot |
| Cracks, shadows, and apparent depth | Mostly omit | A shallow panel elevation is enough | No stone-slab buttons or heavy embossed controls |
| Geometric linework behind the animal | Adapt | A sparse, consistent angular motif | Do not combine it with unrelated neon grids or futuristic HUD effects |

The visual tension worth preserving is **organic pigment plus precise signal paths**. Avoid turning this into either a generic orange SaaS theme or a fantasy-game interface.
## Color system
These are proposed design tokens interpreted from the artwork, **not pixel-sampled colors**. The success, error, and informational colors intentionally expand beyond the reference so operational meaning does not depend on a single orange-brown palette.

| Role | Token | Proposed value | Use |
|---|---|---|---|
| Canvas | `--cave-canvas` | `#151311` | Page background |
| Panel | `--cave-panel` | `#211D19` | Composer, ledger, dialogs |
| Raised surface | `--cave-raised` | `#2B251F` | Table headings, selected details |
| Field | `--cave-field` | `#191612` | Inputs and response area |
| Primary text | `--cave-text` | `#F2E6D2` | Body text, headings, figures |
| Secondary text | `--cave-muted` | `#C1AE95` | Hints and supporting labels |
| Placeholder | `--cave-subtle` | `#AA967E` | Nonessential prompt guidance |
| Control boundary | `--cave-border` | `#8C7965` | Field outlines and control edges |
| Primary action | `--cave-ember` | `#DF7548` | Send call and primary dialog action |
| Emphasis and focus | `--cave-gold` | `#E5B567` | Spend figure, meter, keyboard focus |
| Successful optimization | `--cave-success` | `#99B88A` | Downshifted and saved estimate |
| Intervention/error | `--cave-danger` | `#F28B78` | Budget block, stopped loop, request error |
| Information | `--cave-info` | `#8DB6C2` | Optional response/information accent |

Use **dark text on the ember button**, not white text by default. Computed contrast for the proposed dark text on ember is 5.98:1; primary text on the panel is 13.57:1, and secondary text on the panel is 7.78:1. WCAG's normal-text minimum is 4.5:1, with 3:1 allowed for qualifying large text.[^3]

These calculations cover specific solid-color pairs only. They do not establish whole-interface compliance, especially after adding opacity, imagery, new backgrounds, or additional states.
## Typography and geometry
**Keep the fonts already in the application.** Barlow for body copy and Barlow Condensed for headings provide a practical distinction without introducing another asset or typography dependency. [Source: font loading](https://github.com/WelkinTheShark/SheldonHackaThon2026/blob/8e216869d8ac6f83fa51afcf19b185ca2b8381b4/app/static/index.html)

Recommended specifications:

- Body: 16px with approximately 1.5 line height.
- Table text: approximately 14–15px; permit horizontal scrolling rather than shrinking indefinitely.
- Headings: condensed, medium-to-bold, with minimal tracking.
- Financial figures: tabular numerals so values align as they update.
- Panel corners: 10px; controls: 6px; status badges: 4px.
- Spacing: a 4/8/12/16/24/32px scale.
- Main buttons and fields: at least 44px tall; compact table actions: 36px where appropriate.

The 44px recommendation is a comfort target, not the WCAG AA minimum; WCAG 2.2 AA generally specifies 24-by-24 CSS pixels or qualifying spacing/exceptions, while the enhanced AAA criterion uses 44-by-44.[^4][^5]

Do not distress functional lettering. The brand illustration can be rough; the product's numbers and controls should not be.
## Component treatment
### Header and sign-in
Use a small standalone dog mark alongside a clean CaveDawg wordmark when a suitable transparent asset is available. Keep the large rock-wall composition for a deliberate brand panel rather than repeating it across the dashboard. The initial theme does not extract the dog or invent a vector replacement.

A faint gold circuit motif can sit on the header's right edge. It must remain decorative, noninteractive, and out of the way of session controls. The supplied stylesheet implements this as a small SVG background and hides it on narrower screens.
### Spend and budget
Keep this area as the first thing viewers read. The existing app already updates the spend figure, budget fill, savings figure, call count, and blocked count together. [Source: `renderSummary`](https://github.com/WelkinTheShark/SheldonHackaThon2026/blob/8e216869d8ac6f83fa51afcf19b185ca2b8381b4/app/static/app.js)

Use gold for the spend figure and normal meter, then coral for the existing over-budget state. Use sage for the saved amount, but preserve its estimate qualification in supporting copy: the README identifies saved amounts as estimates rather than audited outcomes. [Source: README limits](https://github.com/WelkinTheShark/SheldonHackaThon2026/blob/8e216869d8ac6f83fa51afcf19b185ca2b8381b4/README.md)

Do not show a green meter as a claim that the system is healthy; budget consumption is not a health metric.
### Composer
Place the form on an opaque warm-charcoal panel. Keep its main action ember, model recommendation understated, and override action visibly secondary. Use gold on the routing slider to connect the circuit motif with model selection without changing any labels or interaction.

The current composer includes simulation controls, recommended-model selection, a one-call override, prompt roasting, and retry-loop demonstration. Those are behaviorally distinct actions, so do not collapse them into an ambiguous themed menu. [Source: composer markup](https://github.com/WelkinTheShark/SheldonHackaThon2026/blob/8e216869d8ac6f83fa51afcf19b185ca2b8381b4/app/static/index.html)
### Live calls and statuses
Use flat table surfaces, restrained row hover, readable numeric alignment, and small rectangular status badges. Remove the current rotation and rubber-stamp animation for a more modern instrument-panel feel. [Source: existing status styles](https://github.com/WelkinTheShark/SheldonHackaThon2026/blob/8e216869d8ac6f83fa51afcf19b185ca2b8381b4/app/static/style.css)

| Existing state | Proposed treatment | Meaning |
|---|---|---|
| OK | Neutral bone/muted | A call completed without the special status |
| Overkill | Ochre | Review model fit |
| Downshifted | Sage | Optimization applied |
| Blocked by budget | Coral plus exact label | Policy intervention, not necessarily product failure |
| Loop stopped | Coral plus exact label | An agent workflow was interrupted |
| Error / dropped / failed swap | Coral plus reason | Preserve the specific diagnostic text |
| Simulated | Explicit text and persistent banner | Not a real provider-cost observation |

The JavaScript assigns status classes and explanatory text dynamically; theme these existing classes rather than substituting new status semantics. [Source: `renderCalls`](https://github.com/WelkinTheShark/SheldonHackaThon2026/blob/8e216869d8ac6f83fa51afcf19b185ca2b8381b4/app/static/app.js)
### Roast details and administration
Style roast details as expandable reports, not a glowing chat interface. Give the score emphasis, but leave the explanation, suggested fix, and receipt easy to scan.

Keep user administration visually quieter than live calls. Preserve the application's existing management visibility rules; CSS is only presentation, not an authorization mechanism. [Source: viewer handling and rendering](https://github.com/WelkinTheShark/SheldonHackaThon2026/blob/8e216869d8ac6f83fa51afcf19b185ca2b8381b4/app/static/app.js)
## Earlier references to borrow
| Earlier reference | Relevant precedent | Recommended borrowing |
|---|---|---|
| Hito Steyerl, Contemporary Cave Art | A cave environment with responsive digital imagery.[^6] | Contrast organic forms with modern technology, not literal museum reconstruction |
| Sara Mast, CAVE | Collective participation shapes an audiovisual environment. [Project](https://www.saramast.com/cave) | Make interaction reveal the identity; do not run decorative animation constantly |
| Roca dels Moros virtual tour | Guided exploration of a scanned rock-art site.[^7] | Reveal detail on demand rather than showing every explanation at once |

These are design interpretations. No claim is made that the museum projects use the proposed palette, fonts, or component system.
## Implementation plan
The hackathon-safe approach is **an additive stylesheet**, not a framework migration.

1. Copy `cavedawg-theme.css` into `app/static`.
2. Load it immediately after the existing `style.css` link.
3. Leave the existing HTML IDs, event handlers, API calls, form types, and native dialogs unchanged.
4. Review sign-in, the budget dialog, populated calls, roast details, and all access levels.
5. Run the repository's existing browser scenarios after the visual change. [Source: Wren scenarios](https://github.com/WelkinTheShark/SheldonHackaThon2026/blob/8e216869d8ac6f83fa51afcf19b185ca2b8381b4/wren/use-cases.md)

```html
/static/style.css">
/static/cavedawg-theme.css">
```

The override aliases the old palette variables to the new system and explicitly restyles controls that previously used hard-coded white backgrounds. Native dialogs, hidden content, access-related visibility classes, and the JavaScript-controlled meter width remain intact. [Source: original styling and DOM](https://github.com/WelkinTheShark/SheldonHackaThon2026/blob/8e216869d8ac6f83fa51afcf19b185ca2b8381b4/app/static/style.css)

Below 1600px, move roast results underneath live calls rather than compressing three working columns. Below 800px, stack the composer and ledger. Keep wide tables scrollable within their containers.

Use only short state transitions. Respect reduced-motion preferences and avoid continuous firelight, particle, or circuit-flow animation; the relevant CSS preference is designed to suppress nonessential motion.[^8]
## Verification and limits
Local Chromium checks of the supplied theme against the inspected, unpopulated markup found no document-wide horizontal overflow at 1440px or 390px. Hidden banners and management-only content remained hidden as expected, the native sign-in dialog rendered, and reduced-motion mode removed the meter transition. These are limited local checks, not a live-service or end-to-end test.

The kit includes an unpopulated HTML preview, desktop/mobile/sign-in screenshots, the override stylesheet, implementation notes, and computed color-pair checks. The preview deliberately omits application JavaScript and does not call APIs; it must not be presented as a working app or evidence of successful workflows.

Remaining acceptance work: populated and long-content layouts, all roles, keyboard interaction, zoom, forced colors, provider-backed calls, and the final Wren workflows. Keep simulation conspicuous and distinguish rehearsal runs from real evaluation evidence. [Source: repository test guidance](https://github.com/WelkinTheShark/SheldonHackaThon2026/blob/8e216869d8ac6f83fa51afcf19b185ca2b8381b4/wren/use-cases.md)
## Coding-agent handoff
> Implement a restrained cave-art-inspired theme called Painted Signal using the supplied override stylesheet. Preserve every existing DOM ID, API call, event handler, access rule, workflow label, native dialog, and simulation disclosure. Keep spend and budget first, the call composer and ledger next, and roast details secondary. Use warm charcoal, bone, ochre, and ember with flat readable working surfaces. Do not introduce a framework, full-screen rock wallpaper, fantasy fonts, neon HUD effects, continuous background animation, or a new navigation system. Add the dog only as a separate brand asset. Re-run the existing browser scenarios after styling.

---

## References

1. [dd33b746-f0bc-4818-a688-eae6e43e1bae.jpeg](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/images/48741198/f8953af5-604b-4518-b998-ba04eb260fd5/dd33b746-f0bc-4818-a688-eae6e43e1bae.jpeg)

2. [https://github.com/WelkinTheShark/SheldonHackaThon2026

You are an expert distributed systems engineer and API proxy architect. Conduct a comprehensive technical audit of the CaveDawg hackathon repository at https://github.com/WelkinTheShark/SheldonH...

... elements of the original vision were successfully retained (TypeSafe Jev, loop breaking, model downscaling, developer accountability).
   - Provide concrete recommendations to polish this build for the Seldon Hackathon ("Ship Happens") demo station.](https://www.perplexity.ai/search/11ced62d-cf22-4f90-9a74-903546126a2b) - CaveDawg is a substantial improvement over the original scenario simulator: it implements a real Ant...

3. [Understanding SC 1.4.3: Contrast ...](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html) - For example, for a 72ppi image, an author would need to use approximately 19pt and 24pt font sizes i...

4. [Understanding Success Criterion 2.5.8: Target Size (Minimum) | WAI](https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html) - The size of the target for pointer inputs is at least 24 by 24 CSS pixels, The requirement is for ta...

5. [Target Size (Enhanced) | WAI | W3C](https://www.w3.org/WAI/WCAG22/Understanding/target-size-enhanced.html) - While this criterion defines a minimum target size, it is recommended that larger sizes are used to ...

6. [Contemporary Cave Art | Hito Steyerl](https://www.estherschipper.com/exhibitions/1189-contemporary-cave-art-hito-steyerl/) - In this film we experience Hito Steyerl's Contemporary Cave Art, a site-specific iteration of her 20...

7. [Visita virtual a la Roca dels Moros - La Tempesta – Cultura en digital](https://latempesta.cc/projecte/roca-dels-moros/) - Visita virtual a la Roca dels Moros - La Tempesta – Cultura en digital

8. [Using the CSS prefers-reduced-motion query to prevent ...](https://www.w3.org/WAI/WCAG22/Techniques/css/C39) - The objective of this technique is to allow users to prevent animations (including motion animations...

