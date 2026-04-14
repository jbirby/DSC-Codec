#!/usr/bin/env python3
"""
DSC (Digital Selective Calling) decoder.
Decodes DSC calls from WAV audio recordings.

Usage:
    python3 dsc_decode.py <input.wav> [output.txt] [options]

Examples:
    # Decode and display to stdout
    python3 dsc_decode.py recording.wav

    # Decode and save to file
    python3 dsc_decode.py recording.wav output.txt
"""

import argparse
import sys
import wave
import numpy as np
from typing import List, Optional, Tuple
from dsc_common import (
    SAMPLE_RATE, BAUD_RATE, MARK_FREQ, SPACE_FREQ,
    dsc_decode_symbol, compute_ecc, fsk_demodulate,
    find_dot_pattern, find_phasing_sequence,
    FORMAT_SPECIFIERS, CATEGORIES, TELECOMMANDS, DISTRESS_CODES,
    DX_SYMBOL, RX_SYMBOL, EOS_SYMBOLS
)


def read_wav(filename: str) -> Tuple[np.ndarray, int]:
    """Read WAV file and return audio samples and sample rate."""
    with wave.open(filename, 'rb') as f:
        n_channels = f.getnchannels()
        sample_width = f.getsampwidth()
        frame_rate = f.getframerate()
        n_frames = f.getnframes()

        audio_bytes = f.readframes(n_frames)

    # Convert to numpy array
    audio = np.frombuffer(audio_bytes, dtype=np.int16)
    audio = audio.astype(np.float32) / 32768.0

    # If stereo, take first channel
    if n_channels == 2:
        audio = audio[::2]

    return audio, frame_rate


def resample_audio(audio: np.ndarray, orig_rate: int, target_rate: int) -> np.ndarray:
    """Simple linear interpolation resampling."""
    if orig_rate == target_rate:
        return audio

    ratio = target_rate / orig_rate
    new_length = int(len(audio) * ratio)
    indices = np.linspace(0, len(audio) - 1, new_length)
    resampled = np.interp(indices, np.arange(len(audio)), audio)

    return resampled


def extract_10bit_symbols(bits: List[int]) -> List[int]:
    """Extract 10-bit symbols from bit sequence."""
    symbols = []
    i = 0
    while i + 10 <= len(bits):
        symbol_bits = bits[i:i+10]
        symbol_10bit = 0
        for bit in symbol_bits:
            symbol_10bit = (symbol_10bit << 1) | bit
        symbols.append(symbol_10bit)
        i += 10

    return symbols


def decode_dsc_call(symbols: List[int]) -> Optional[dict]:
    """
    Decode a DSC call from 10-bit symbols.

    Returns a dictionary with call information, or None if decode fails.
    """
    if len(symbols) < 20:
        return None

    result = {
        'valid': False,
        'phasing_sequence': None,
        'format': None,
        'address': None,
        'category': None,
        'self_id': None,
        'telecommand1': None,
        'telecommand2': None,
        'eos': None,
        'ecc_valid': False,
        'errors': []
    }

    idx = 0

    # Helper to decode a 10-bit symbol
    def decode_10bit(sym_10bit):
        sym_val, sym_err = dsc_decode_symbol(sym_10bit)
        return sym_val, sym_err

    # Decode phasing sequence (6 repetitions of DX or RX)
    phasing_type = None
    for i in range(6):
        if idx >= len(symbols):
            result['errors'].append('Truncated at phasing sequence')
            return result

        sym_val, sym_err = decode_10bit(symbols[idx])
        idx += 1

        if i == 0:
            phasing_type = 'DX' if sym_val == DX_SYMBOL else 'RX' if sym_val == RX_SYMBOL else 'unknown'
            result['phasing_sequence'] = phasing_type

    # Decode format specifier
    if idx >= len(symbols):
        result['errors'].append('Truncated at format specifier')
        return result

    sym_val, sym_err = decode_10bit(symbols[idx])
    idx += 1

    format_name = FORMAT_SPECIFIERS.get(sym_val, f'unknown({sym_val})')
    result['format'] = format_name

    # Decode address (MMSI as 9 digits)
    address_digits = []
    for i in range(9):
        if idx >= len(symbols):
            result['errors'].append('Truncated at address')
            return result

        sym_val, sym_err = decode_10bit(symbols[idx])
        idx += 1

        if 0 <= sym_val <= 9:
            address_digits.append(str(sym_val))
        else:
            result['errors'].append(f'Invalid digit in address: {sym_val}')

    result['address'] = ''.join(address_digits) if address_digits else None

    # Decode category
    if idx >= len(symbols):
        result['errors'].append('Truncated at category')
        return result

    sym_val, sym_err = decode_10bit(symbols[idx])
    idx += 1

    category_name = CATEGORIES.get(sym_val, f'unknown({sym_val})')
    result['category'] = category_name

    # Decode self-ID (caller's MMSI, 9 digits)
    self_id_digits = []
    for i in range(9):
        if idx >= len(symbols):
            result['errors'].append('Truncated at self-ID')
            return result

        sym_val, sym_err = decode_10bit(symbols[idx])
        idx += 1

        if 0 <= sym_val <= 9:
            self_id_digits.append(str(sym_val))

    result['self_id'] = ''.join(self_id_digits) if self_id_digits else None

    # Decode telecommand 1
    if idx >= len(symbols):
        result['errors'].append('Truncated at telecommand1')
        return result

    sym_val, sym_err = decode_10bit(symbols[idx])
    idx += 1

    tc1_name = TELECOMMANDS.get(sym_val, f'unknown({sym_val})')
    result['telecommand1'] = tc1_name

    # Decode telecommand 2
    if idx >= len(symbols):
        result['errors'].append('Truncated at telecommand2')
        return result

    sym_val, sym_err = decode_10bit(symbols[idx])
    idx += 1

    tc2_name = TELECOMMANDS.get(sym_val, f'unknown({sym_val})')
    result['telecommand2'] = tc2_name

    # For distress alerts, decode additional fields
    if format_name == 'distress_alert':
        # Nature of distress
        if idx >= len(symbols):
            result['errors'].append('Truncated at distress nature')
            return result

        sym_val, sym_err = decode_10bit(symbols[idx])
        idx += 1

        distress_nature = DISTRESS_CODES.get(sym_val, f'unknown({sym_val})')
        result['distress_nature'] = distress_nature

        # Position (8 digits: 4 for latitude, 4 for longitude)
        position_digits = []
        for i in range(8):
            if idx >= len(symbols):
                result['errors'].append('Truncated at position')
                return result

            sym_val, sym_err = decode_10bit(symbols[idx])
            idx += 1

            if 0 <= sym_val <= 9:
                position_digits.append(str(sym_val))

        if len(position_digits) == 8:
            lat_min = int(''.join(position_digits[:4]))
            lon_min = int(''.join(position_digits[4:]))
            result['latitude_min'] = lat_min
            result['longitude_min'] = lon_min

        # Time (4 digits: HHMM UTC)
        time_digits = []
        for i in range(4):
            if idx >= len(symbols):
                result['errors'].append('Truncated at time')
                return result

            sym_val, sym_err = decode_10bit(symbols[idx])
            idx += 1

            if 0 <= sym_val <= 9:
                time_digits.append(str(sym_val))

        if len(time_digits) == 4:
            result['time_hhmm'] = ''.join(time_digits)

    # Decode EOS (End of Sequence)
    if idx >= len(symbols):
        result['errors'].append('Truncated at EOS')
        return result

    sym_val, sym_err = decode_10bit(symbols[idx])
    idx += 1

    eos_name = EOS_SYMBOLS.get(sym_val, f'unknown({sym_val})')
    result['eos'] = eos_name

    # Extract ECC (should be last symbol)
    if idx >= len(symbols):
        result['errors'].append('No ECC found')
        return result

    received_ecc, ecc_err = decode_10bit(symbols[idx])
    idx += 1

    # Verify ECC: compute XOR of all symbols before ECC
    ecc_symbols = []
    for i in range(idx - 1):  # All except the last ECC symbol
        sym_val, _ = decode_10bit(symbols[i])
        ecc_symbols.append(sym_val)

    computed_ecc = compute_ecc(ecc_symbols)
    result['ecc_valid'] = (received_ecc == computed_ecc)

    result['valid'] = True

    return result


def format_result(result: dict) -> str:
    """Format decoded DSC call for display."""
    lines = []

    if not result['valid']:
        lines.append("=== INVALID DSC CALL ===")
        if result['errors']:
            lines.append("Errors:")
            for err in result['errors']:
                lines.append(f"  - {err}")
        return '\n'.join(lines)

    lines.append("=== DSC CALL DECODED ===")

    if result['phasing_sequence']:
        lines.append(f"Phasing: {result['phasing_sequence']}")

    if result['format']:
        lines.append(f"Format: {result['format']}")

    if result['address']:
        lines.append(f"Destination MMSI: {result['address']}")

    if result['category']:
        lines.append(f"Category: {result['category']}")

    if result['self_id']:
        lines.append(f"Caller MMSI: {result['self_id']}")

    if result['telecommand1']:
        lines.append(f"Telecommand 1: {result['telecommand1']}")

    if result['telecommand2']:
        lines.append(f"Telecommand 2: {result['telecommand2']}")

    if 'distress_nature' in result:
        lines.append(f"Nature: {result['distress_nature']}")

    if 'latitude_min' in result:
        lines.append(f"Position: {result['latitude_min']} min lat, {result['longitude_min']} min lon")

    if 'time_hhmm' in result:
        lines.append(f"Time: {result['time_hhmm']} UTC")

    if result['eos']:
        lines.append(f"EOS: {result['eos']}")

    lines.append(f"ECC Valid: {'Yes' if result['ecc_valid'] else 'No'}")

    if result['errors']:
        lines.append("Warnings:")
        for err in result['errors']:
            lines.append(f"  - {err}")

    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(
        description='Decode DSC calls from WAV audio',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument('input', help='Input WAV filename')
    parser.add_argument('output', nargs='?', help='Output text file (optional)')
    parser.add_argument(
        '--verbose', action='store_true',
        help='Verbose output'
    )

    args = parser.parse_args()

    # Read WAV file
    try:
        audio, sample_rate = read_wav(args.input)
        print(f"Read {args.input}: {sample_rate} Hz, {len(audio)} samples", file=sys.stderr)
    except Exception as e:
        print(f"Error reading WAV: {e}", file=sys.stderr)
        sys.exit(1)

    # Resample if needed
    if sample_rate != SAMPLE_RATE:
        audio = resample_audio(audio, sample_rate, SAMPLE_RATE)
        sample_rate = SAMPLE_RATE

    # Demodulate to bits
    bits = fsk_demodulate(audio, SAMPLE_RATE, BAUD_RATE, MARK_FREQ, SPACE_FREQ)

    if args.verbose:
        print(f"Demodulated {len(bits)} bits", file=sys.stderr)

    # Find dot pattern
    dot_idx = find_dot_pattern(bits)
    if dot_idx >= 0:
        bits = bits[dot_idx + 200:]  # Skip past dot pattern
        if args.verbose:
            print(f"Found dot pattern at bit {dot_idx}", file=sys.stderr)
    else:
        if args.verbose:
            print("Warning: dot pattern not found", file=sys.stderr)

    # Find phasing sequence
    phasing_idx, phasing_type = find_phasing_sequence(bits)
    if phasing_idx >= 0:
        bits = bits[phasing_idx:]  # Skip to phasing start
        if args.verbose:
            print(f"Found phasing sequence ({phasing_type}) at bit {phasing_idx}", file=sys.stderr)
    else:
        if args.verbose:
            print("Warning: phasing sequence not found", file=sys.stderr)

    # Extract 10-bit symbols
    symbols = extract_10bit_symbols(bits)
    if args.verbose:
        print(f"Extracted {len(symbols)} 10-bit symbols", file=sys.stderr)

    # Decode DSC call
    result = decode_dsc_call(symbols)

    if result is None:
        print("Error: Failed to decode DSC call", file=sys.stderr)
        sys.exit(1)

    # Format and output
    output_text = format_result(result)
    print(output_text)

    if args.output:
        with open(args.output, 'w') as f:
            f.write(output_text)
        print(f"Wrote {args.output}", file=sys.stderr)


if __name__ == '__main__':
    main()
