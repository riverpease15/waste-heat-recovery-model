/**
 * scheduler_inputs_frontend/theme.js
 *
 * Single source of truth for all custom input styling.
 * Edit this file to update Start Time, Duration, and GPU Power Level at once.
 * Changes take effect on next Streamlit rerun — no rebuild needed.
 */

window.THEME = {
  // ── Colors ─────────────────────────────────────────────────────────────
  surface:        '#1a1d27',
  border:         '#2e3347',
  borderFocus:    '#4a90d9',
  glow:           'rgba(74, 144, 217, 0.18)',
  digit:          '#ffffff',
  digitDim:       '#3a3f58',
  accent:         '#4a90d9',
  labelColor:     '#ffffff',
  hintColor:      '#8b92b0',
  optionHover:    'rgba(74, 144, 217, 0.12)',
  optionSelected: 'rgba(74, 144, 217, 0.22)',

  // ── Typography ──────────────────────────────────────────────────────────
  fontClock: "'Share Tech Mono', 'Courier New', monospace",
  fontUi:    "'DM Sans', -apple-system, BlinkMacSystemFont, sans-serif",
  digitSize:      '32px',
  labelSize:      '12px',
  hintSize:       '11px',
  valueSize:      '32px',   /* clock/duration digit size — restored to original */
  valueSizeSmall: '18px',   /* gpu/rack text size — smaller without affecting height */

  // ── Shape ───────────────────────────────────────────────────────────────
  borderRadius: '10px',
  borderWidth:  '1.5px',

  // ── Spacing ─────────────────────────────────────────────────────────────
  paddingV:    '10px',
  paddingH:    '18px',
  inputHeight: '55px',   /* clock/duration: 32px digit + 10+10 padding + 3px borders */
  inputHeightSmall: '44px',  /* gpu/rack: 20px font + 10+10 padding + 4px borders */
};

(function applyTheme() {
  const r = document.documentElement;
  const t = window.THEME;
  r.style.setProperty('--surface',         t.surface);
  r.style.setProperty('--border',          t.border);
  r.style.setProperty('--border-focus',    t.borderFocus);
  r.style.setProperty('--glow',            t.glow);
  r.style.setProperty('--digit',           t.digit);
  r.style.setProperty('--digit-dim',       t.digitDim);
  r.style.setProperty('--accent',          t.accent);
  r.style.setProperty('--label-color',     t.labelColor);
  r.style.setProperty('--hint-color',      t.hintColor);
  r.style.setProperty('--option-hover',    t.optionHover);
  r.style.setProperty('--option-selected', t.optionSelected);
  r.style.setProperty('--font-clock',      t.fontClock);
  r.style.setProperty('--font-ui',         t.fontUi);
  r.style.setProperty('--digit-size',      t.digitSize);
  r.style.setProperty('--label-size',      t.labelSize);
  r.style.setProperty('--hint-size',       t.hintSize);
  r.style.setProperty('--value-size',       t.valueSize);
  r.style.setProperty('--value-size-small', t.valueSizeSmall);
  r.style.setProperty('--border-radius',   t.borderRadius);
  r.style.setProperty('--border-width',    t.borderWidth);
  r.style.setProperty('--padding-v',       t.paddingV);
  r.style.setProperty('--padding-h',       t.paddingH);
  r.style.setProperty('--input-height',       t.inputHeight);
  r.style.setProperty('--input-height-small', t.inputHeightSmall);
})();