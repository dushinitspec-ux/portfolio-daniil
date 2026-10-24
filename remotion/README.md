# Promo videos (Remotion)

React compositions that render a 42-second 1080p promo video and a cover image for each
portfolio project. The output goes straight into the website.

| Composition | Output |
|---|---|
| `promo-fridge-alert-bot`, `promo-hotel-ai-concierge`, `promo-uptime-monitor` | `../site/public/videos/<id>.mp4` |
| `cover-<id>` (still, 1920 × 1200) | `../site/public/projects/<id>/cover.png` |
| frame 840 of `promo-hotel-ai-concierge` | `../site/public/projects/hotel-ai-concierge/conversation.png` |

## Usage

```bash
npm install
npm run studio            # preview and edit in the browser
npm run render            # render all videos and covers (a few minutes)
npm run render -- covers  # only the still images (seconds)
```

## Structure of every video

5 s title → 8 s the problem → 16 s how it works (real screenshots and messages) →
8 s result → 5 s name and role. Same palette and fonts as the website (`src/theme.ts`).

## Honesty rule

Everything shown on screen is real: the chart and the status page are screenshots from the
demo runs, and every chat message is copied from real output of the projects (demo runs or
tests). Numbers are real test counts and measurements. The cover motifs are illustrations
and are described as such in the image `alt` text.

These promo videos do not replace a screen recording of the working app; record those
separately (see the checklist in the main README).
