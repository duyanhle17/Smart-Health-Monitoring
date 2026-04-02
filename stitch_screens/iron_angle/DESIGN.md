# Design System Specification: Industrial Utilitarianism

## 1. Overview & Creative North Star
### Creative North Star: "The Kinetic Blueprint"
This design system rejects the "softness" of modern SaaS in favor of a high-contrast, structural aesthetic inspired by the Bauhaus movement and industrial safety signage. It is built for high-stakes environments where clarity is a safety requirement, not just a preference. 

We break the "standard template" look through **Calculated Brutalism**. By utilizing zero-radius geometry, heavy stroke weights, and asymmetric grid placements, we create a UI that feels like a physical instrument—rigid, reliable, and authoritative. This isn't a "website"; it is a digital control room.

---

## 2. Colors & Surface Logic
The palette is restricted to a high-signal industrial array. Every color must serve a functional purpose: information, warning, or emergency.

### The Palette (Material Design Mapping)
- **Primary (#000000):** Structural foundation. Used for all borders, primary text, and heavy UI anchors.
- **Secondary (#C00015):** The "Alarm" state. High-chroma red for critical failures and immediate hazards.
- **Tertiary (#4A3900):** The "Warning" state. Used with `on_tertiary` (#FFE08B) for cautionary data.
- **Surface (#F9F9F9):** The "Off-white" substrate. Provides maximum contrast against black structural elements.

### The "Heavy Border" Rule
In a departure from traditional soft-UI, this system **mandates** 2px or 3px solid borders (`outline`) for all module containment. 
- **Prohibited:** Soft shadows, 1px borders, and rounded corners.
- **Required:** Every module must feel "framed." Use `primary` (#000000) for standard modules and `secondary` (#C00015) for critical modules.

### Surface Hierarchy
Nesting is achieved through "Inverted Contrast" rather than elevation:
- **Level 1 (Base):** `surface` (#f9f9f9)
- **Level 2 (In-set Module):** `surface_container` (#eeeeee) with a 2px `primary` border.
- **Level 3 (Active State):** `primary` (#000000) background with `on_primary` (#e2e2e2) text.

---

## 3. Typography: The Geometric Voice
The typography is the core of the system’s "Bauhaus" soul. We use **Space Grotesk** for display and **Work Sans** for data, creating a tension between architectural geometry and industrial legibility.

- **Display-LG (Space Grotesk, 3.5rem):** Reserved for singular, high-impact safety metrics (e.g., Gas Levels).
- **Headline-MD (Space Grotesk, 1.75rem):** Used for section headers. Always uppercase to emphasize the utilitarian "signage" feel.
- **Body-LG (Work Sans, 1rem):** High-readability sans-serif for status reports and logs.
- **Label-SM (Space Grotesk, 0.6875rem):** Used for technical metadata. Tight tracking, bold weight.

**The "Digital Vital" Rule:** For real-time sensor data, use tabular lining figures (monospaced) to ensure numbers don't jump when values change.

---

## 4. Elevation & Depth: Structural Layering
We reject "Ambient Shadows." Depth in this system is interpreted as **Physical Stacking**.

- **Tonal Layering:** Hierarchy is communicated by the weight of the border and the density of the background. A "Critical Alert" card does not float; it occupies the space with a `secondary_container` background and a 4px `secondary` border.
- **The Offset Shadow:** If visual "lift" is required for a modal, use a hard-edged, 100% opaque offset. (e.g., a black rectangle offset 4px down and 4px right from the module, with no blur).
- **Zero-Radius Execution:** All `roundedness` tokens are set to `0px`. Sharp corners communicate precision and industrial rigor.

---

## 5. Components

### Buttons: The "Actuator" Style
- **Primary:** `primary` background, `on_primary` text. No border-radius. 2px `primary` border.
- **Emergency (Secondary):** `secondary` background, `on_error` text. Used only for "Stop" or "Evacuate."
- **States:** Hover states should invert colors (e.g., Background becomes `surface`, text becomes `primary`).

### Input Fields: The "Form-Field"
- Text inputs are rectangular blocks with 2px `outline` borders. 
- **Focus State:** Border weight increases to 4px. No "glow" or "halo."

### Vital Sign Modules (Cards)
- Use a grid-based layout. 
- Large `Display-SM` numbers for the value.
- Small `Label-MD` text in the top-left corner for the metric name (e.g., "O2 LEVELS").
- If the value exceeds thresholds, the entire card background switches to `secondary_container` or `tertiary_container`.

### Progress Bars: "The Gauge"
- No rounded ends. 
- Background: `surface_container_high`. 
- Fill: `primary` (Normal), `tertiary` (Warning), or `secondary` (Danger).

---

## 6. Do’s and Don’ts

### Do:
- **Embrace Asymmetry:** Use the 24-unit spacing scale to create intentional gaps in the grid, mimicking 20th-century editorial design.
- **Use Heavy Strokes:** When in doubt, make the border thicker.
- **Respect the Grid:** Every element must align to a hard pixel-perfect vertical and horizontal axis.

### Don't:
- **No Gradients:** Color must be flat and "honest."
- **No Icons without Labels:** In a safety environment, icons are secondary to text. Never use a "hamburger" menu; use a button labeled "MENU."
- **No "Soft" Interactions:** Avoid spring-based animations. Use linear or high-speed "Ease-In" transitions (150ms-200ms) to maintain the "mechanical" feel.
- **No Divider Lines:** Use background color shifts (`surface_container_low` vs `surface`) or 2px borders to define boundaries. Never use thin, grey 1px dividers.