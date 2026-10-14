# Ideas to take the project further

Done in 0.2.0: Home Assistant integration, HTTP API, mDNS discovery, shuffle bag
(no repeats), video/trashed assets skipped, EXIF rotation respected, preview
renditions instead of originals, persisted settings, 15-minute default interval
(e-ink shouldn't be redrawn every 30 s), rotating logs, no more full-size
downloads piling up in `images/`.

Next candidates:

1. **Smart crop** – centre-crop cuts off faces. Immich knows face boxes
   (`/api/people`, asset `people[].faces[]`); crop around them. Or offer a "fit" mode
   with a blurred/white border instead of cropping.
2. **Colour tuning** – 7-colour panels look washed out; add per-panel saturation/contrast
   (`set_image(img, saturation=…)` on supported models) and optional dithering preview.
3. **Weather/clock overlay** – a small date or "taken in Passau, Aug 2024" caption from the
   metadata that is already fetched.
4. **Quiet hours on the device** – skip refreshes at night even without HA.
5. **Physical buttons** – the Impression has four buttons (GPIO 5/6/16/24): next / previous /
   pause / display off, in addition to HA.
6. **Smarter selection** – favourites only, "on this day" photos, weighted by recency.
7. **Pull-through cache** – keep the next photo pre-downloaded so a button press is instant.
8. **Tests & CI** – the pure parts (`render`, `immich`, controller with a fake display)
   are easy to test; add a GitHub Action with `ruff` + `pytest`.
9. **Lockfile** – `poetry.lock` is out of sync with the slimmed-down `pyproject.toml`
   (run `poetry lock`); the installer uses `requirements.txt`.
