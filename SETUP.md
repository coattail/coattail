# Deploy Guide (coattail Profile Refresh)

## Files to copy into the `coattail` profile repository

- `README.md`
- `dist/research-hero.svg`
- `dist/macro-lens-card.svg`
- `dist/tracker-card.svg`

## Recommended repository structure

```text
coattail/
  README.md
  dist/
    research-hero.svg
    macro-lens-card.svg
    tracker-card.svg
```

## Publishing steps

1. Create or open the public repository named exactly `coattail`.
2. Copy the files above into that repository.
3. Confirm the README loads the SVGs from `main/dist/...`.

## Customization ideas

- Replace the tagline in `README.md` with a Chinese or bilingual version.
- Swap one featured project if you want to highlight a newer tool.
- Adjust the accent colors in the SVGs if you want a warmer or lighter palette.
- If the GitHub profile repo still has an old snake workflow, remove it from `.github/workflows/` to stop failed scheduled runs.
