# DSC Codec - Digital Selective Calling for Maritime Radio

A complete DSC (Digital Selective Calling) codec implementation for SDR hobbyists and sailors. Encodes and decodes DSC calls used on marine VHF, MF, and HF radio according to ITU-R M.493 standard.

## What is DSC?

Digital Selective Calling (DSC) is the automated digital signaling system used on marine radio to:
- Initiate distress alerts and coordinate search and rescue
- Hail and call individual vessels by MMSI (Maritime Mobile Service Identity)
- Broadcast safety and weather information
- Make automated radio calls without voice

DSC is **mandatory under GMDSS** (Global Maritime Distress and Safety System) on:
- **VHF Channel 70** (156.525 MHz) — the primary DSC channel
- **MF 2187.5 kHz** — medium frequency DSC
- **Various HF frequencies** — long-range DSC for ocean-going vessels

All DSC transmissions use **100 baud FSK with 170 Hz shift** (1615/1785 Hz audio tones).

## Features

- **DSC Call Encoding**: Create any DSC call type with full customization
  - All-ships broadcasts
  - Individual vessel calls (by MMSI)
  - Group calls
  - Area calls (by geographic coordinates)
  - Distress alerts with nature of distress, position, and UTC time

- **DSC Call Decoding**: Extract and parse calls from WAV audio recordings
  - Automatic bit synchronization (dot pattern detection)
  - Phasing sequence detection (DX/RX)
  - 10-bit symbol extraction with check bit validation
  - Error correction via symbol interleaving
  - ECC (Error Check Character) verification

- **Robust Reception**: Handles real SDR recordings
  - FSK demodulation with energy detection
  - Automatic sample rate handling (resample if needed)
  - Bit synchronization from sync pattern

## Installation

No external dependencies beyond numpy:

```bash
pip install numpy
```

## Usage

### Encoding: Generate DSC Call Audio

```bash
python3 scripts/dsc_encode.py <output.wav> [options]
```

**Examples:**

```bash
# Individual call to vessel MMSI 123456789
python3 scripts/dsc_encode.py call.wav --address 123456789

# Distress alert with position and time
python3 scripts/dsc_encode.py distress.wav \
  --format distress \
  --address 123456789 \
  --category distress \
  --distress-nature sinking \
  --position 51.5,-1.5 \
  --time 1245

# All-ships broadcast
python3 scripts/dsc_encode.py broadcast.wav --format all-ships

# Working channel information
python3 scripts/dsc_encode.py call.wav --address 123456789 --channel 72
```

**Options:**

- `--format` — Call type: `all_ships`, `selective_call` (default), `group_call`, `area_call`, `distress_alert`
- `--address MMSI` — Destination MMSI (9 digits, default 123456789)
- `--self-id MMSI` — Caller's MMSI (9 digits, default 211234567)
- `--category CAT` — `routine` (default), `safety`, `urgency`, `distress`
- `--telecommand1 TC` — First message type (default: `simplex_telephone_F3E_G3E`)
- `--telecommand2 TC` — Second message type (default: `no_information`)
- `--channel N` — VHF working channel number
- `--distress-nature CODE` — For distress alerts: `fire`, `flooding`, `collision`, `grounding`, `sinking`, `disabled_adrift`, `undesignated`, `abandoning_ship`, `piracy`, `man_overboard`, `EPIRB_emission`
- `--position LAT,LON` — Position in decimal degrees (e.g., `51.5,-1.5`)
- `--time HHMM` — UTC time (e.g., `1245` for 12:45 UTC)

### Decoding: Extract DSC from Recordings

```bash
python3 scripts/dsc_decode.py <input.wav> [output.txt] [--verbose]
```

**Examples:**

```bash
# Decode to stdout
python3 scripts/dsc_decode.py recording.wav

# Decode and save to file
python3 scripts/dsc_decode.py recording.wav output.txt

# Verbose output
python3 scripts/dsc_decode.py recording.wav output.txt --verbose
```

**Decoder output includes:**

```
=== DSC CALL DECODED ===
Phasing: DX
Format: selective_call
Destination MMSI: 123456789
Category: routine
Caller MMSI: 211234567
Telecommand 1: simplex_telephone_F3E_G3E
Telecommand 2: no_information
EOS: no_info
ECC Valid: Yes
```

## Technical Details

### DSC Call Structure (ITU-R M.493)

Every DSC call consists of:

1. **Dot pattern** — 200 alternating bits (0101... or 1010...) for bit synchronization
2. **Phasing sequence** — DX (126) or RX (127) symbol repeated 6 times
3. **Format specifier** — Indicates call type (102-123)
4. **Address field** — Destination MMSI (9 digits) or coordinates
5. **Category** — Routine (100), Safety (108), Urgency (110), or Distress (112)
6. **Self-ID** — Caller's MMSI (9 digits)
7. **Telecommand 1** — Message type (e.g., telephone, data, distress position)
8. **Telecommand 2** — Secondary message type or frequency/channel
9. **Optional fields** — For distress alerts: nature, position, time
10. **EOS** — End of Sequence marker (120-122)
11. **ECC** — Error Check Character (XOR of all preceding symbols)

### Symbol Encoding

Each DSC symbol is encoded as a 10-bit value:
- **Bits 0-6** (7 bits): Information (constrained to 4 ones + 3 zeros)
- **Bits 7-9** (3 bits): Check bits = 7 - popcount(info_bits)

This constant-weight encoding ensures each symbol has exactly 7 ones in its 10-bit representation, allowing detection of single-bit errors.

### Error Correction

DSC uses **two-level error correction**:

1. **Symbol interleaving** — Each symbol is repeated 5 positions later in the transmission. If two copies disagree, the one with valid check bits is used.

2. **ECC verification** — The final ECC character is the XOR of all symbols from the format specifier through the EOS marker. Receiver verifies this checksum.

### Signal Parameters

- **Bit rate**: 100 baud (0.01 seconds per symbol, 10 bits per symbol = 1000 bps)
- **Mark frequency**: 1615 Hz (binary 1)
- **Space frequency**: 1785 Hz (binary 0)
- **Shift**: 170 Hz (1785 - 1615)
- **Modulation**: FSK (Frequency Shift Keying)

## Testing

Run the comprehensive test suite:

```bash
python3 scripts/dsc_test.py
```

Tests cover:
- Symbol encode/decode with check bit validation
- ECC computation
- Interleaving and de-interleaving
- Individual call encoding
- Distress alert encoding
- All-ships broadcasts
- FSK modulation/demodulation
- Full WAV encode/decode roundtrips
- Symbol error correction

## Use Cases

### For SDR Hobbyists
- Decode live VHF DSC traffic from SDR receivers
- Analyze marine radio distress calls and safety broadcasts
- Monitor vessels by their MMSI calling patterns
- Archive maritime DSC events

### For Sailors
- Generate DSC calls for testing/simulation
- Create distress alert audio for training
- Understand VHF Channel 70 traffic

### For Researchers
- Study maritime communication protocols
- Analyze GMDSS system performance
- Test DSC-related applications

## Limitations and Notes

- **Single-tone audio**: This codec implements baseband DSC at 1615/1785 Hz. Real radio equipment transmits on RF (156.525 MHz VHF, 2187.5 kHz MF, etc.), which would require additional RF modulation.

- **No interleaving optimization**: The current implementation does not fully implement the official interleaving scheme (which repeats symbols at N+5 positions for error correction). The main error correction is via check bits and ECC.

- **Synchronization**: The decoder looks for the dot pattern and phasing sequence. It's optimized for clean, well-formed DSC signals. Real QSB (fading) or noise may affect reception.

- **MMSI format**: The codec validates 9-digit MMSIs. Invalid formats will be rejected or zero-padded.

## Standards References

- **ITU-R M.493-15** — Digital Selective Calling (DSC) for use in the maritime mobile service
- **ITU-R M.541** — Maritime Mobile Service Identity (MMSI)
- **GMDSS** — Global Maritime Distress and Safety System (IMO/IEC specifications)

## License

This code is provided as-is for educational and amateur radio use.

## Contributing

Improvements and bug reports welcome. Key areas for enhancement:
- Full interleaving/de-interleaving implementation
- Advanced synchronization (Costas loop, PLL)
- Real SDR file format support (GQRX, HACK RF, etc.)
- Multi-channel monitoring
- Distress alert frequency allocation database

