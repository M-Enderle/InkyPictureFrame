# Home Assistant integration

The `inky_frame` custom integration talks to a small HTTP API that the frame
service exposes on the Pi (port `8765`). No MQTT broker is needed.

## Install

**HACS:** HACS → ⋮ → *Custom repositories* → add `https://github.com/M-Enderle/InkyPictureFrame`
(type *Integration*) → download *Inky Picture Frame* → restart Home Assistant.

**Manual:** copy `custom_components/inky_frame` into your HA `config/custom_components/`.

## Connect

1. Update the Pi (`git pull`, `sudo bash install.sh`, `sudo systemctl restart inky-frame`).
2. Get the API token on the Pi: `cd InkyPictureFrame && /home/pi/.virtualenvs/pimoroni/bin/python -m frame token`.
3. Home Assistant discovers the frame via mDNS (*Settings → Devices → Discovered*).
   Otherwise: *Add integration → Inky Picture Frame* and enter host, port and token.

## Entities

| Entity | Purpose |
|---|---|
| `image.inky_frame_photo` | Live preview of what is on the display |
| `button.inky_frame_next_photo` / `…_previous_photo` | Skip forward / back |
| `button.inky_frame_reload_album` | Re-read the Immich album |
| `switch.inky_frame_display` | Off = panel is wiped white and the slideshow pauses |
| `switch.inky_frame_automatic_change` | Pause / resume the timer, keeping the current photo |
| `number.inky_frame_change_interval` | Minutes between photos (3–1440) |
| `select.inky_frame_orientation` | Landscape / portrait |
| `select.inky_frame_album` | Choose any Immich album |
| `light.inky_frame_led` | Dimmable LED (only if `LED_GPIO` is set, see [led.md](led.md)) |
| `sensor.inky_frame_current_photo` | Filename; attributes: album, taken, location, `immich_url` |
| `sensor.inky_frame_status` | idle / updating / off / error (`last_error` attribute) |
| `sensor.inky_frame_last_change`, `…_next_change` | Timestamps |
| `sensor.inky_frame_photos_in_album` | Album size |

Entity IDs follow the English names above (HA derives them from the system
language at first setup, so yours may differ — and an area can add a prefix, e.g.
`light.schlafzimmer_inky_frame_led` — check *Settings → Entities*).

A note on "off": e-ink keeps its image without power. *Display off* therefore
redraws the panel white (one ~30 s refresh) and stops the slideshow.

## Dashboard card

```yaml
type: vertical-stack
cards:
  - type: picture-entity
    entity: image.inky_frame_photo
    show_state: false
    show_name: false
  - type: entities
    entities:
      - sensor.inky_frame_current_photo
      - entity: sensor.inky_frame_next_change
        name: Next change
      - switch.inky_frame_display
      - switch.inky_frame_automatic_change
      - number.inky_frame_change_interval
      - select.inky_frame_album
      - select.inky_frame_orientation
      - light.inky_frame_led
  - type: horizontal-stack
    cards:
      - type: button
        entity: button.inky_frame_previous_photo
        icon: mdi:skip-previous
        show_name: false
      - type: button
        entity: button.inky_frame_next_photo
        icon: mdi:skip-next
        show_name: false
```

## Automation ideas

```yaml
# Wipe the frame at night, bring it back in the morning
- alias: Inky frame night mode
  triggers:
    - trigger: time
      at: "23:00:00"
  actions:
    - action: switch.turn_off
      target: { entity_id: switch.inky_frame_display }
- alias: Inky frame morning
  triggers:
    - trigger: time
      at: "07:00:00"
  actions:
    - action: switch.turn_on
      target: { entity_id: switch.inky_frame_display }

# New photo when the first person arrives home
- alias: Inky frame welcome
  triggers:
    - trigger: state
      entity_id: zone.home
      from: "0"
  conditions:
    - condition: numeric_state
      entity_id: zone.home
      above: 0
  actions:
    - action: button.press
      target: { entity_id: button.inky_frame_next_photo }
```

## API (for debugging)

`GET /api/v1/health` is open; everything else needs `Authorization: Bearer <token>`.
Interactive docs: `http://<pi>:8765/docs`.

| Method | Path | |
|---|---|---|
| GET | `/api/v1/status` | full state as JSON |
| GET | `/api/v1/image` | preview JPEG |
| POST | `/api/v1/command/{next\|previous\|reload\|clear}` | |
| POST | `/api/v1/settings` | `interval_min`, `orientation`, `album_id`, `display_on`, `slideshow` |
| POST | `/api/v1/led` | `on`, `brightness` (1–255) |
