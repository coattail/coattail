# Deploy Guide (Sunny-1991 Profile)

## 1) Create profile repository

Create a public repository named exactly:

`Sunny-1991`

## 2) Add files

Copy files from this template into the profile repository root:

- `README.md`
- `.github/workflows/snake.yml`

## 3) Enable workflow permissions

In repository settings:

`Settings -> Actions -> General -> Workflow permissions -> Read and write permissions`

## 4) Trigger once

Go to Actions, run `Generate Snake Animation` manually once.

After it succeeds, the snake animation will be published to `output` branch and shown in README.

## 5) Optional customizations

- Replace email in README (`your_email_here@example.com`)
- Change theme (`tokyonight`) to your preferred theme
- Add/remove pinned project cards
