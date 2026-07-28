# Mobile admin map — design

**Date:** 2026-07-28
**Status:** approved, ready for implementation planning

## Problem

The admin console at `/admin` is unusable on a phone for its main field task: placing
worker dots by hand.

Two concrete causes, both verified in the current code:

1. **The dot is a squashed ellipse, not a circle.** Worker nodes live inside
   `.iso-scene`, which carries `rotateX(60deg) rotateZ(-45deg)`. Unlike the name
   label (`IsometricMap.jsx:132`), the dot body does not counter-rotate, so it lies
   flat on the ground plane and is foreshortened to roughly half its height. The
   `w-5 h-5` dot renders as about 20 × 10 px, and at the phone default zoom of 0.45
   (`IsometricMap.jsx:178-180`) as about 9 × 4.5 px.

2. **Everything around the dot is `pointer-events-none`** — the ping rings, the
   heading arrows, the label. Only the dot body itself is touchable, so the
   effective touch target is that 9 × 4.5 px ellipse, far below the 44 px minimum
   for touch.

Missing the dot lands the touch on the map surface, which starts a camera rotation
(`IsometricMap.jsx:210-215`). The user sees the map spin instead of the dot move.

## Solution

A separate mobile presentation of `/admin`: the map alone, flat and face-on, with a
joystick for precise placement.

Removing camera rotation is what makes the rest fall out. At `rotateX(0)` every
element already faces the camera, so the foreshortening disappears with no
billboarding code. And with no rotation gesture, there is nothing left to trigger by
accident, so a touch on empty map is free to mean pan.

## Scope

**In scope:** a mobile-only rendering path for `/admin`.

**Out of scope:** any change to desktop behaviour. `IsometricMap.jsx` is not
modified. `CommandLayout.jsx` and `AdminPanel.jsx` each gain one guarded branch that
the desktop path never enters.

This costs roughly 100 duplicated lines of scene markup. Accepted: a flat top-down
plan view needs different scene construction from the 2.5-D isometric view anyway, so
writing it separately is less code than parameterising the existing component — and
it keeps a working safety dashboard out of the blast radius.

## Entry and layout

One URL. `/admin` stays the only address.

Mobile mode is active when the viewport is under 1024 px wide, unless the operator has
chosen the full console. That choice persists in `localStorage` under
`safework_admin_view` (`'map' | 'full'`), and is exposed as a small button in the
top-left corner so field calibration is still reachable from a phone.

In mobile mode the screen holds only:

- the map, filling the viewport
- zoom `+` / `−` and a reset-view button, top right
- the full-console button, top left
- the joystick, bottom left — **only while a worker is selected**

No header, no footer ticker, no sidebars, no legend, no scene toggle, and no vitals
alarm banner.

**Accepted consequence:** with the alarm banner gone, a phone showing this screen will
not surface `PULSE LOST` or `SIGNAL LOST`. This was raised and chosen deliberately.
The phone is a placement tool, not a monitoring station.

The PIN gate stays. Dragging a dot writes a position override to the server, so the
existing `PinGate` from `AdminPanel.jsx` is reused unchanged before the map renders.

## Camera

Flat top-down: `rotateX(0) rotateZ(0)`. No rotation gesture of any kind.

**Fit to screen.** Initial scale is `min(viewportWidth / 1000, viewportHeight / 800)`
so the whole 1000 × 800 logical scene is visible. Recomputed on resize and orientation
change — the current code computes zoom once from `window.innerWidth` and registers no
resize listener, so rotating the phone today leaves the view wrong.

**Zoom** runs from the fit scale to 3× the fit scale, driven by the `+` / `−` buttons
and by two-finger pinch. The reset button returns to fit scale with pan cleared.

**Pan.** A one-finger drag starting on empty map translates the view. It is only
meaningful past the fit scale; at fit scale the map is fully visible and pan is
clamped to zero. Pan is clamped so the scene cannot be dragged entirely off screen.

## Worker nodes

The dot grows from 20 px to 28 px and is a true circle, since nothing is foreshortened
at `rotateX(0)`.

The name label is **always visible**, sitting directly above the dot. The current
hover-reveal (`IsometricMap.jsx:131`) is dead weight on touch, where there is no hover.

The touch target is a **single hit region spanning both the dot and its label**, padded
so it is never smaller than 44 × 44 px. Both are part of one control, per the
requirement that touching either one picks up the worker.

Status colours carry over unchanged from `IsometricMap.jsx:37-86`, including the
degraded-position states, so the mobile view never implies more positional confidence
than the desktop one.

Anchors render as yellow squares with permanent labels. They are the reference frame
and must be visible, but they are **not draggable** — matching desktop, where only
`WorkerNode` receives a pointer handler.

All workers render in this view, including ones with no valid fix, mirroring the
`isAdminView` bypass at `IsometricMap.jsx:355-362`. Placing an unlocated worker by hand
is the whole point of the screen.

The scene background follows the stored `mapTheme` (`SITE` or `MINE`) from the store.
There is no toggle on this screen.

## Interaction

| Gesture | Result |
|---|---|
| Touch down on a dot or its label | Select that worker immediately (ring appears) |
| Drag from a dot or its label | Move it directly, commit on release |
| Tap empty map | Deselect |
| Drag from empty map | Pan the view (when zoomed past fit) |
| Two-finger pinch | Zoom |
| Joystick | Move the selected worker |

Selection happens on touch **down**, not release, so a drag that starts on a dot both
selects and moves it in one motion.

**Tap versus drag on empty map** is decided by a movement threshold of 8 px: a pointer
that goes down and comes up having moved less than 8 px is a tap and deselects; more
than 8 px is a pan and leaves the selection alone. Without this rule, every pan would
silently clear the selection and hide the joystick mid-task.

Direct drag and joystick are both available; they are two ways to do the same thing,
suited to coarse and fine placement respectively.

## Joystick

Hidden until a worker is selected, so an idle screen shows nothing but the map.

Analog and velocity-based: displacement from centre sets speed, and full deflection
moves the worker at **15 logical units per second** — the logical space is 0–100 on
each axis, so a full-deflection traverse of the map takes about seven seconds. Small
deflections give fine nudging. The operator's thumb sits in the bottom corner and never
covers the dot being placed, which is the advantage over direct dragging.

**Leash.** The joystick may push a worker at most **±20 logical units on each axis**
from where it sat when the placement session began. The anchor is captured on
selection and released on deselection. Placement is a correction to a position, not a
way to teleport a worker across the site; the leash also stops a held thumb from
silently walking a dot off into another zone. Direct dragging is not leashed — the
operator can see exactly where their finger is putting it.

**Cosmetic jitter.** While the stick is deflected, the worker under it wobbles by up
to **5 px**, resampled every **120 ms**. Sample-and-hold rather than smooth
interpolation, because that is how a glitching UWB fix actually behaves — a smooth
wobble reads as animation, not noise.

Three limits on this, all deliberate:

- It is **render-only**. The offset is applied as a CSS pixel translate and never
  enters the coordinate sent to `/api/admin/node`, so a placement lands exactly where
  the operator put it.
- It applies to **only the worker under the joystick**. Every other dot keeps showing
  what the server reported.
- It stops the moment the stick recentres.

**This makes a hand-placed dot read as a live sensor reading, which is exactly what it
is for and exactly why it is a hazard outside a demo.** The system otherwise works hard
to keep that distinction — `AdminPanel.jsx:288` badges manual positions `MANUAL` in
purple, and the isometric map carries six separate colours for position confidence. A
control room running this build would have no way to tell a faked wobble from a real
fix. It is scoped as tightly as possible above; it should not ship to a live site
without a visible "demo" indicator.

**Commit policy.** Joystick motion updates position locally only. A single
`POST /api/admin/node` fires **500 ms after the stick returns to centre**, so holding a
direction does not flood the API. Direct drag follows the desktop rule: one POST on
release, as in `IsometricMap.jsx:276-296`.

After either commit, the local optimistic overlay is dropped so the next socket update
renders server truth — same discipline as the current drag handler.

## Coordinate mapping

With rotation gone, the inverse projection collapses from the six trigonometric steps
at `IsometricMap.jsx:247-266` to two divisions:

```
dlx = dx / zoom / 10
dly = dy / zoom / 8
```

Results are clamped to 0–100 on both axes, as today.

## Files

New:

| File | Responsibility |
|---|---|
| `hooks/useMobileMapMode.js` | Viewport-width detection plus the persisted `safework_admin_view` preference |
| `pages/MobileAdminMap.jsx` | Screen composition: PIN gate, map, controls, joystick |
| `components/map/FlatMap.jsx` | Flat renderer — fit, zoom, pan, selection, direct drag |
| `components/map/FlatWorkerNode.jsx` | Dot, label, unified hit region, selection ring |
| `components/map/Joystick.jsx` | Analog stick, emits a velocity vector |

Modified (guarded branches only, desktop path untouched):

| File | Change |
|---|---|
| `components/layout/CommandLayout.jsx` | In mobile map mode, render `<Outlet/>` alone |
| `pages/AdminPanel.jsx` | In mobile map mode, return `<MobileAdminMap/>` early |

Unchanged: `IsometricMap.jsx`, and every other page and component.

## Error handling

- **Backend unreachable on commit.** Keep the local overlay in place and mark the dot
  as uncommitted rather than silently snapping it back, so the operator knows the
  placement did not land.
- **PIN rejected (403).** Clear the stored PIN and fall back to the gate, matching
  `runAdmin` in `AdminPanel.jsx:90-105`.
- **No workers reported.** Render the empty scene with a single short line of text;
  this is the one exception to "nothing but the map", because an empty screen with no
  explanation is indistinguishable from a broken one.

## Testing

- `useMobileMapMode` — width thresholds, preference persistence, override wins over
  width.
- Fit-scale computation across portrait and landscape aspect ratios; recompute on
  resize.
- Inverse projection: a known pixel delta at a known zoom maps to the expected logical
  delta; clamping holds at each of the four boundaries.
- Joystick: displacement maps to the expected velocity; centring triggers exactly one
  commit after the debounce; holding a direction triggers none.
- Leash: a held stick stops at 20 units from the anchor on each axis, and still
  respects the 0–100 map edges when the leash would run past them.
- Jitter: stays inside its amplitude, holds a value for one step then jumps, is
  deterministic for a given instant, and never appears in a committed coordinate.
- Hit region measures at least 44 × 44 px, and a touch on the label selects the same
  worker as a touch on the dot.
- Desktop regression: `/admin` above 1024 px renders the existing two-column console
  with the isometric map, unchanged.
