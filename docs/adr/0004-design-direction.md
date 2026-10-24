# 0004. Design direction: instrument panel, surgical steel

- Status: proposed
- Date: 2026-10-24
- Deciders: Jay
- Ticket: SG-10

The ticket asks for this as `0002-design-direction.md`. ADR numbers 0002 and 0003 were
already taken (session limits, simulator), so it is 0004.

## Context and problem statement

The users are sterile processing supervisors and technicians, on desktops and on tablets on
the work floor, often in gloves and sometimes in bright light. They read numbers (hours,
counts, probabilities) and act on them the evening before a shift. The interface must feel
calm and trustworthy. It must not look like a generic AI template: no Inter, no purple
gradients, no glassmorphism, no emoji as icons.

## Considered options

1. **Instrument panel, surgical steel** (chosen). Cool steel neutrals and one teal accent
   used like an indicator lamp. Hairline rules, small engraved uppercase labels, and large
   tabular monospace numbers as the hero. A subtle "gauge rail" tick texture marks scales
   and headers.
2. **Clinical white with a blue system palette.** Familiar from EHRs, but it reads as
   generic, and blue clashes with the info status color.
3. **Dark-first control room.** Dramatic and good for wall displays. It is tiring under
   bright floor lighting, and printing and screenshots suffer.
4. **Warm editorial (serif headings, paper tones).** Distinctive, but it suggests reports
   rather than a live tool, and it gets less dense.

## Decision outcome

Chosen option: 1. It matches the domain (stainless steel, sterilizer gauges, cycle
printouts), puts numbers first, and works in light and dark at the same density.

- Type: IBM Plex Sans 400/500/600 for UI and IBM Plex Mono with tabular, slashed-zero
  numerals for every metric (`.tabular`). Scale 12, 13, 14, 16, 20, 24, 32, 40.
- Color: `steel` 50 to 950 and `teal` 50 to 950. Primary is teal-700 in light and
  teal-400 in dark. Each status set (good, warning, critical, info) has bg, fg and border
  colors and always comes with an icon or a text label.
- Shape: 8px grid with a 4px half step, radius 6/8/12, one popover elevation, and a 2px
  focus ring with a 2px offset. Motion is 150 to 200 ms ease-out, off under
  `prefers-reduced-motion`.
- Signature details: engraved section labels (`.engraved`), the gauge rail under page
  headers and range bars, an active-nav "lamp" bar, and 44px touch targets everywhere.
- Contrast: every text/background pair is at least 4.5:1, and control borders and the focus
  ring are at least 3:1 in both themes. This is checked by `sg test a11y --tokens`.

### Consequences

- Good: one accent keeps attention on status and numbers. The tokens are hex, so the
  contrast check is exact.
- Bad: a single accent leaves little room for chart series. Charts use steel shades plus
  teal and a warm fifth color. Revisit in SG-15 if forecasts need more series.

## Links

- Plan section: §2.4, §6.1, §6.2, §6.5
- `apps/web/src/styles/tokens.css`, `apps/web/src/app/globals.css`, `/app/style`
