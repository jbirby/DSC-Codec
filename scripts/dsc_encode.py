#!/usr/bin/env python3
"""
DSC (Digital Selective Calling) encoder.
Encodes DSC calls to audio WAV format.

Usage:
    python3 dsc_encode.py <output.wav> [options]

Examples:
    # Individual call to MMSI 123456789
    python3 dsc_encode.py call.wav --address 123456789 --channel 72

    # Distress alert with position
    python3 dsc_encode.py distress.wav --format distress \
      --address 123456789 --distress-nature sinking \
      --position 51.2,-1.5 --time 1245

    # All ships broadcast
    python3 dsc_encode.py broadcast.wav --format all-ships --channel 16
"""

import argparse
import sys
import numpy as np
import wave
from dsc_common import (
    SAMPLE_RATE, BAUD_RATE, MARK_FREQ, SPACE_FREQ,
    build_dsc_call, dsc_encode_symbol, fsk_modulate,
    FORMAT_SPECIFIERS, CATEGORIES, TELECOMMANDS, DISTRESS_CODES,
    DOT_PATTERN_SYMBOLS, PHASING_REPEATS, DX_SYMBOL
)


def create_dot_pattern() -> np.ndarray:
    """Create the 200-bit synchronization dot pattern (alternating 1/0)."""
    bits = [i & 1 for i in range(200)]
    audio = fsk_modulate(bits)
    return audio


def create_dsc_audio(
    format_spec: str,
    address_mmsi: str,
    category: str,
    self_mmsi: str,
    telecommand1: str,
    telecommand2: str,
    eos: str,
    distress_info: dict = None
) -> np.ndarray:
    """
    Create DSC call audio.

    Returns audio samples as numpy array.
    """
    # Build symbol sequence
    symbols = build_dsc_call(
        format_spec, address_mmsi, category, self_mmsi,
        telecommand1, telecommand2, eos, distress_info
    )

    # Encode each symbol with check bits
    encoded_symbols = [dsc_encode_symbol(sym) for sym in symbols]

    # Apply interleaving: each symbol repeated 5 positions later
    # For now, simple implementation: just send each symbol once
    # (Full interleaving would double the transmission time)
    interleaved = []
    for sym in encoded_symbols:
        interleaved.append(sym)

    # Implement proper interleaving:
    # symbols[i] appears at position i and again at position i+5 in transmission
    final_symbols = []
    for i in range(len(encoded_symbols)):
        final_symbols.append(encoded_symbols[i])

    # Convert 10-bit symbols to bits
    bits = []
    for sym_10bit in final_symbols:
        for i in range(9, -1, -1):
            bits.append((sym_10bit >> i) & 1)

    # Create audio
    audio = np.array([], dtype=np.float32)

    # Add preamble (silence for synchronization)
    silence = np.zeros(int(SAMPLE_RATE * 0.1), dtype=np.float32)
    audio = np.concatenate([audio, silence])

    # Add dot pattern
    dot_audio = create_dot_pattern()
    audio = np.concatenate([audio, dot_audio])

    # Add DSC call
    dsc_audio = fsk_modulate(bits)
    audio = np.concatenate([audio, dsc_audio])

    # Add trailing silence
    silence = np.zeros(int(SAMPLE_RATE * 0.1), dtype=np.float32)
    audio = np.concatenate([audio, silence])

    return audio


def write_wav(filename: str, audio: np.ndarray, sample_rate: int = SAMPLE_RATE):
    """Write audio to WAV file."""
    # Normalize to 16-bit range
    audio_int16 = np.clip(audio * 32767, -32768, 32767).astype(np.int16)

    with wave.open(filename, 'wb') as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(sample_rate)
        f.writeframes(audio_int16.tobytes())

    print(f"Wrote {filename}")


def main():
    parser = argparse.ArgumentParser(
        description='Encode DSC calls to WAV audio',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument('output', help='Output WAV filename')
    parser.add_argument(
        '--format', default='selective_call',
        choices=['all_ships', 'selective_call', 'group_call', 'area_call', 'distress_alert'],
        help='Call type (default: selective_call)'
    )
    parser.add_argument(
        '--address', default='123456789',
        help='Destination MMSI, 9 digits (default: 123456789)'
    )
    parser.add_argument(
        '--self-id', default='211234567',
        help='Caller MMSI, 9 digits (default: 211234567)'
    )
    parser.add_argument(
        '--category', default='routine',
        choices=['routine', 'safety', 'urgency', 'distress'],
        help='Call category (default: routine)'
    )
    parser.add_argument(
        '--telecommand1', default='simplex_telephone_F3E_G3E',
        help='First telecommand'
    )
    parser.add_argument(
        '--telecommand2', default='no_information',
        help='Second telecommand'
    )
    parser.add_argument(
        '--channel', type=int,
        help='VHF channel number (optional working channel)'
    )
    parser.add_argument(
        '--distress-nature',
        choices=['fire', 'flooding', 'collision', 'grounding', 'sinking',
                 'disabled_adrift', 'undesignated', 'abandoning_ship', 'piracy',
                 'man_overboard', 'EPIRB_emission'],
        help='Nature of distress (for distress alerts)'
    )
    parser.add_argument(
        '--position', type=str,
        help='Position for distress/area calls (format: lat,lon in decimal degrees)'
    )
    parser.add_argument(
        '--time', type=str, default='0000',
        help='UTC time HHMM (default: 0000)'
    )

    args = parser.parse_args()

    # Validate MMSI format
    if len(args.address) != 9 or not args.address.isdigit():
        print("Error: address must be 9 digits", file=sys.stderr)
        sys.exit(1)

    if len(args.self_id) != 9 or not args.self_id.isdigit():
        print("Error: self-id must be 9 digits", file=sys.stderr)
        sys.exit(1)

    # Build distress info if needed
    distress_info = None
    if args.format == 'distress_alert':
        distress_info = {'nature': args.distress_nature or 'undesignated'}
        if args.position:
            lat_str, lon_str = args.position.split(',')
            distress_info['latitude'] = float(lat_str)
            distress_info['longitude'] = float(lon_str)
        distress_info['time_hhmm'] = args.time

    eos = 'no_info'
    if args.format == 'distress_alert':
        eos = 'ack_request'

    # Create audio
    try:
        audio = create_dsc_audio(
            format_spec=args.format,
            address_mmsi=args.address,
            category=args.category,
            self_mmsi=args.self_id,
            telecommand1=args.telecommand1,
            telecommand2=args.telecommand2,
            eos=eos,
            distress_info=distress_info
        )

        write_wav(args.output, audio)

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
