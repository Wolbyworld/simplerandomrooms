# V2 user acceptance test plan

Run these cases against a disposable local database. Use a current Chromium,
Firefox, or WebKit browser for desktop checks and at least one 390 px-wide
mobile viewport. Never point the test session at production.

Record the browser, viewport, locale, reduced-motion setting, room code, and
pass/fail result for each run. A failed case should include a screenshot and the
relevant server/browser log excerpt without participant tokens.

## Test setup

1. Start the application with a new temporary SQLite database.
2. Open `/health` and verify a healthy response.
3. Keep a private/incognito window available as a second participant.
4. Keep the browser accessibility tree and network inspector available.
5. For reconnection cases, use the browser's offline network toggle rather than
   stopping the server.

## Desktop: solo flow

- [ ] On the home page, Numbers, Names/List, Coin, and Dice are immediately
  discoverable without creating a multiplayer session first.
- [ ] Configure Numbers as 1–3, without replacement, then choose **Draw now**.
  The room opens with a prominent result, a persistent draw action, remaining
  count, compact sharing controls, and collapsed settings.
- [ ] Draw until exhausted. Every result is unique, the completed state is
  explicit, and another draw produces a useful non-destructive error.
- [ ] Reset the round. The eligible pool is restored and history records the
  reset instead of disappearing.
- [ ] Invalidate the latest result. The result becomes eligible again and a
  separate audit entry identifies the invalidation; earlier history is intact.
- [ ] Copy and download/export history. The exported rows match the on-screen
  result order, actors, timestamps, modes, validity, and receipt details.
- [ ] Open receipt details. They include draw index, timestamp, mode, actor,
  result, and eligible-pool commitment, and use precise audit language without
  claiming that the server's randomness can be independently proven.

## Desktop: modes and presets

- [ ] Numbers accepts negative and positive inclusive integer bounds, rejects a
  reversed or unreasonably large range inline, and supports multiple winners.
- [ ] Paste names separated by lines, commas, tabs, and spreadsheet cells. Blank
  values disappear, whitespace is normalized, duplicates are reported, and
  first-seen spelling/order is retained.
- [ ] When weight syntax is offered, valid positive weights are explained and
  reflected in configuration; zero, negative, malformed, or excessive weights
  are rejected without losing the draft.
- [ ] **Pick a winner**, **Split teams**, **Choose an order**, **Yes / no**, and
  **Standard dice** populate understandable settings and produce an appropriate
  result.
- [ ] Coin only returns Heads/Tails and dice results remain inside the configured
  dice/count bounds.
- [ ] Multiple-winner list/number draws are atomic, contain no duplicate winner
  without replacement, and reduce the remaining count by the winner count.
- [ ] Long list items and large numeric results wrap or scale without covering
  controls or leaving the result stage.

## Multiplayer, sharing, and recovery

- [ ] The top bar shows a short, human-friendly room code. The copy-link action
  produces a joinable URL without exposing host credentials.
- [ ] Native share (where supported), QR, and WhatsApp actions contain the same
  join URL. Dismissing the native share sheet is not presented as an error.
- [ ] Open the share URL in a private window. A guest-name step appears before
  the room, trims whitespace, safely renders markup-like input as text, and
  rejects blank or overlong names.
- [ ] Both windows show participant presence and host identity. The host's name
  and role agree in both clients.
- [ ] With host-only drawing enabled, a guest draw is rejected without changing
  history or the pool. Host settings, reset, and end controls remain unavailable
  to the guest.
- [ ] Switch to anyone-can-draw. A guest draw appears once in both windows with
  the guest as actor and identical result, remaining count, receipt, and index.
- [ ] Refresh both clients. Configuration, participants, complete result history,
  invalidations, and remaining pool recover from the server; no repeated item
  becomes eligible accidentally.
- [ ] Toggle one client offline and back online. Status changes through
  disconnected/reconnecting/connected states, then the client receives one
  canonical current state without duplicating history.
- [ ] Visit a room through its short-code URL with mixed case and surrounding
  whitespace removed. It resolves to the same room; an unknown or malformed
  code gives a privacy-safe not-found response.
- [ ] End the room as host. Both clients see an ended state, drawing/configuration
  is disabled, and revisiting the link never silently creates a new room.
- [ ] If expiry is configured, verify an expired room shows a clear expired state
  and no participant details leak to unrelated visitors.

## Mobile and touch

- [ ] At 390 × 844 and 320 × 568, the result and primary draw button are visible
  without horizontal scrolling; all controls have at least a 44 × 44 px target.
- [ ] Opening settings uses a usable bottom sheet: focus moves inside, background
  content does not scroll, Escape/back/close works, and focus returns to the
  opener.
- [ ] The primary action stays thumb-reachable above browser safe-area insets and
  does not overlap recent-result chips or completion/error messages.
- [ ] The on-screen keyboard does not hide name entry, pasted-list feedback, or
  the submit action.
- [ ] QR and share controls fit the viewport and remain dismissible in portrait
  and landscape.
- [ ] A supported device produces optional, restrained haptic feedback after a
  reveal; disabling haptics and sound is remembered.

## Keyboard, screen reader, and reduced motion

- [ ] Complete every home and room action using only Tab, Shift+Tab, Enter,
  Space, arrow keys where conventional, and Escape. Focus is always visible.
- [ ] Space/Enter draws when focus is outside an editable control, but never while
  typing in an input, textarea, select, dialog, or contenteditable region.
- [ ] After drawing, a polite live region announces the final result once. It does
  not read intermediate animation frames or reannounce old history on reconnect.
- [ ] Form controls have programmatic names, errors are associated with their
  fields, status is not communicated by color alone, and icon-only buttons have
  screen-reader labels.
- [ ] At 200% zoom and with increased text size, content remains operable and no
  essential result, error, or permission explanation is clipped.
- [ ] Enable `prefers-reduced-motion: reduce` before loading. Reveal movement and
  smooth scrolling are removed or reduced to a brief crossfade, while the result
  and live announcement still work.
- [ ] Contrast meets WCAG AA for text, focus indicators, controls, errors, and
  disabled states on the paper/ink/signal palette.

## Localization

- [ ] Switch between English and Spanish from both home and room pages. Navigation,
  modes, settings, validation, errors, sharing text, permissions, completion,
  history, receipt labels, and reconnect/ended states all change language.
- [ ] The chosen locale survives navigation, refresh, and a newly created room.
- [ ] User-provided names/results are never translated. Number/date formatting is
  understandable in the chosen locale, and long Spanish labels do not overflow.
- [ ] A missing translation falls back to a readable English string rather than
  displaying a key or blank control.

## Trust and adverse input

- [ ] Submit malformed JSON, an unknown action, missing fields, wrong field types,
  oversized names/lists, impossible winner counts, and out-of-range dice via the
  API and WebSocket. Each receives a structured safe error and leaves room state
  unchanged.
- [ ] Attempt host-only actions with a guest token, no token, and a token from a
  different room. All fail without revealing whether unrelated credentials or
  internal room identifiers exist.
- [ ] Use participant/list values containing `<script>`, HTML entities, quotes,
  bidirectional characters, and very long text. The UI renders text safely and
  exported history does not execute spreadsheet formulas.
- [ ] Send two draw actions as concurrently as practical. Draw indices are unique
  and sequential, no-replacement results are unique, and both clients converge on
  the same state.
- [ ] Reload after every draw and compare the displayed remaining count/history
  with the API state. The server is always authoritative.

## Smoke and regression closeout

- [ ] Run `pytest -q` successfully on the same revision.
- [ ] Run `python scripts/random_draw_smoke.py --base-url
  http://127.0.0.1:8000 smoke` successfully against the disposable local server.
- [ ] Capture final desktop home, desktop room, mobile home, mobile result,
  settings sheet, completed state, and two-participant screenshots.
- [ ] Confirm the feature branch was not pushed and no deployment, DNS, or
  production mutation occurred during verification.
