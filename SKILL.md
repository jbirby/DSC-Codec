---
name: dsc-codec
description: >
  Encode and decode DSC (Digital Selective Calling) maritime radio signals in
  audio WAV format. DSC is the GMDSS-mandated digital signaling system on marine
  VHF Channel 70 and MF/HF frequencies for distress calls, vessel hailing, and
  automated radio calls. Uses 100 baud FSK with 170 Hz shift. Use this skill
  whenever the user mentions DSC, Digital Selective Calling, VHF Channel 70,
  marine radio digital, GMDSS DSC, maritime distress call, MMSI call, ship
  calling, marine VHF decoder, or wants to create/analyze DSC audio WAV files.
  Covers encoding (calls to WAV) and decoding (WAV to call data).
---

# dsc-codec

Encode and decode DSC (Digital Selective Calling) maritime radio signals in audio WAV format. DSC is the digital signaling system used on marine VHF, MF, and HF radio to initiate distress calls, hail specific vessels, and make automated radio calls. It is mandatory under GMDSS on VHF Channel 70 (156.525 MHz) and various MF/HF frequencies worldwide.

Supports encoding DSC calls with full customization (format, MMSI addressing, categories, telecommands, distress alerts with position/time), and decoding real SDR recordings from marine VHF radio. Uses 100 baud FSK with 170 Hz shift (1615/1785 Hz). Perfect for SDR hobbyists, sailors, and maritime VHF enthusiasts who record and analyze marine radio traffic.

## Features

- **DSC Call Encoding**: Create all standard DSC call types (all-ships, selective/individual, group, area, distress)
- **DSC Call Decoding**: Extract calls from WAV audio with robust bit synchronization and symbol error correction
- **Distress Alerts**: Full support for distress calls with nature of distress codes, position, and UTC time
- **Error Correction**: Two-character error correction via symbol interleaving and dual copies
- **Check Bit Validation**: 3-bit error detection on each 10-bit symbol
- **ECC Verification**: XOR error check character validation for call integrity

## Usage

```bash
# Encode a call to a specific vessel (MMSI 123456789)
python3 scripts/dsc_encode.py call.wav --address 123456789 --channel 72

# Encode a distress alert with position
python3 scripts/dsc_encode.py distress.wav --format distress \
  --address 123456789 --category distress \
  --distress-nature sinking --position 51.2,-1.5 --time 1245

# Decode a WAV recording from marine VHF SDR
python3 scripts/dsc_decode.py recording.wav output.txt
```

## Triggers

Use this skill whenever the user mentions: DSC, Digital Selective Calling, VHF Channel 70, marine radio digital, GMDSS DSC, maritime distress call, MMSI call, ship calling, marine VHF decoder, DSC decoder, 156.525 MHz, 2187.5 kHz, selective calling, marine radio SDR, VHF FSK decoder.
