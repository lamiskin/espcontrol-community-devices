# Seeed reTerminal D1001 8" ESP32-P4

- **Chip:** ESP32-P4 (variant: esp32p4)
- **Display:** 8" 1280×800 MIPI DSI (JD9365), landscape
- **Touch:** GSL3670 capacitive
- **Network:** ESP32-C6 co-processor (WiFi via SDIO)
- **Audio:** ES8311 DAC + Class-D amp (2 W mono speaker)
- **Microphone:** ES7210 quad-ADC (dual mics)
- **Battery:** 2500 mAh Li-ion with USB-C charging
- **Grid:** 5×4 (20 slots)
- **Upstream PR:** [#885](https://github.com/jtenniswood/espcontrol/pull/885)
- **PR author:** @zacs
- **Upstream pin:** v2.6.3

## Notes

This is the first ESP32-P4 community port. Key differences from S3 devices:
- Uses `button_template.yaml` (not `button_template_4chunk.yaml`)
- Includes P4-specific files: `audio.yaml`, `microphone.yaml`, `power.yaml`
- Includes `esp32_c6_firmware_update.yaml` for the network co-processor
- Includes `api_navigate.yaml` for API navigation actions
- No `network_coprocessor.yaml` include (the PR omits the substitution-based suffix pattern)
- Display is native MIPI DSI (not SPI/RGB parallel)
