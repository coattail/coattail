# Deploy Guide (coattail Profile Refresh)

## Files to copy into the `coattail` profile repository

- `README.md`
- `dist/research-hero.svg`
- `dist/macro-lens-card.svg`
- `dist/tracker-card.svg`
- `.github/workflows/snake.yml`

## Recommended repository structure

```text
coattail/
  README.md
  dist/
    research-hero.svg
    macro-lens-card.svg
    tracker-card.svg
  .github/
    workflows/
      snake.yml
```

## Publishing steps

1. Create or open the public repository named exactly `coattail`.
2. Copy the files above into that repository.
3. In GitHub Settings -> Actions -> General, enable `Read and write permissions`.
4. Run the `Generate Snake Animation` workflow once.
5. Confirm the README loads the SVGs from `main/dist/...` and the snake from the `output` branch.

## Customization ideas

- Replace the tagline in `README.md` with a Chinese or bilingual version.
- Swap one featured project if you want to highlight a newer tool.
- Adjust the accent colors in the SVGs if you want a warmer or lighter palette.
