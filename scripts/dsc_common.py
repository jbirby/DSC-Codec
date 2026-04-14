"""
DSC (Digital Selective Calling) codec common library.
Implements ITU-R M.493 standard for maritime DSC signaling.
"""

import numpy as np
from typing import Tuple, List, Optional, Dict

# DSC signal parameters
SAMPLE_RATE = 44100  # Hz
BAUD_RATE = 100     # baud (100 symbols/second)
MARK_FREQ = 1615.0  # Hz (binary 1)
SPACE_FREQ = 1785.0 # Hz (binary 0)

# Constants
SAMPLES_PER_SYMBOL = SAMPLE_RATE // BAUD_RATE  # 441 samples per symbol
BIT_TIME = 1.0 / BAUD_RATE  # 0.01 seconds per bit

# DSC Symbol constants
DOT_PATTERN_BITS = 200
DOT_PATTERN_SYMBOLS = DOT_PATTERN_BITS // 10
PHASING_REPEATS = 6

# DSC Symbol values
DX_SYMBOL = 126  # Phasing DX (request)
RX_SYMBOL = 127  # Phasing RX (response)
EOS_SYMBOLS = {120: 'ack_request', 121: 'ack', 122: 'no_info'}
ERROR_SYMBOL = 125
ARQ_SYMBOL = 110
ACK_RQ_SYMBOL = 104
ACK_BQ_SYMBOL = 105

# Format specifier codes
FORMAT_SPECIFIERS = {
    102: 'all_ships',
    112: 'selective_call',
    114: 'group_call',
    116: 'area_call',
    118: 'distress_alert',
    120: 'distress_ack',
    123: 'distress_relay',
}

REVERSE_FORMAT_SPECIFIERS = {v: k for k, v in FORMAT_SPECIFIERS.items()}

# Category codes
CATEGORIES = {
    100: 'routine',
    108: 'safety',
    110: 'urgency',
    112: 'distress',
}

REVERSE_CATEGORIES = {v: k for k, v in CATEGORIES.items()}

# Telecommand codes
TELECOMMANDS = {
    100: 'duplex_telephone_F3E_G3E',
    101: 'simplex_telephone_F3E_G3E',
    103: 'telephone_J3E',
    104: 'FEC_F1B_J2B',
    105: 'ARQ_F1B_J2B',
    109: 'data',
    118: 'distress_position_info',
    126: 'no_information',
}

REVERSE_TELECOMMANDS = {v: k for k, v in TELECOMMANDS.items()}

# Nature of distress codes
DISTRESS_CODES = {
    100: 'fire',
    101: 'flooding',
    102: 'collision',
    103: 'grounding',
    104: 'capsizing',
    105: 'sinking',
    106: 'disabled_adrift',
    107: 'undesignated',
    108: 'abandoning_ship',
    109: 'piracy',
    110: 'man_overboard',
    112: 'EPIRB_emission',
}

REVERSE_DISTRESS_CODES = {v: k for k, v in DISTRESS_CODES.items()}


def _popcount(value: int) -> int:
    """Count number of 1 bits in a value."""
    count = 0
    while value:
        count += value & 1
        value >>= 1
    return count


def dsc_encode_symbol(value: int) -> int:
    """
    Encode a DSC symbol value (0-127) into a 10-bit symbol with check bits.

    The 10-bit symbol consists of:
    - Bits 0-6: 7-bit information (must have 4 ones and 3 zeros)
    - Bits 7-9: 3-bit check bits (equals 7 - popcount of info bits)

    Args:
        value: Symbol value 0-127

    Returns:
        10-bit symbol with check bits (bits 0-9)
    """
    if not (0 <= value <= 127):
        raise ValueError(f"Symbol value must be 0-127, got {value}")

    info_bits = value & 0x7F  # 7 bits
    ones_count = _popcount(info_bits)

    # Check bits equal (7 - popcount) to maintain weight
    check_bits = (7 - ones_count) & 0x7  # 3 bits

    # Assemble: check bits in positions 7-9, info bits in 0-6
    symbol_10bit = (check_bits << 7) | info_bits

    return symbol_10bit


def dsc_decode_symbol(bits_10: int) -> Tuple[int, bool]:
    """
    Decode a 10-bit DSC symbol and validate check bits.

    Args:
        bits_10: 10-bit value

    Returns:
        Tuple of (symbol_value, is_error)
        is_error = True if check bits don't match expected value
    """
    bits_10 &= 0x3FF  # Mask to 10 bits

    info_bits = bits_10 & 0x7F       # Bits 0-6
    check_bits = (bits_10 >> 7) & 0x7  # Bits 7-9

    ones_count = _popcount(info_bits)
    expected_check = (7 - ones_count) & 0x7

    is_error = (check_bits != expected_check)

    return info_bits, is_error


def compute_ecc(symbols: List[int]) -> int:
    """
    Compute the ECC (Error Check Character) as XOR of all symbols.

    Args:
        symbols: List of 7-bit symbol values

    Returns:
        7-bit ECC value
    """
    ecc = 0
    for sym in symbols:
        ecc ^= (sym & 0x7F)
    return ecc & 0x7F


def apply_interleaving(symbols: List[int]) -> List[int]:
    """
    Apply DSC interleaving: each symbol repeated 5 positions later.

    For input [S0, S1, S2, S3, S4, S5, S6...]:
    The transmission pattern is: S0, S1, S2, S3, S4, S0_repeat, S5, S1_repeat, ...

    In 2-D array form (6 columns):
    Row 0: S0 S1 S2 S3 S4 S5
    Row 1: S0 S1 S2 S3 S4 S5

    Read column-wise: S0, S0_repeat, S1, S1_repeat, S2, S2_repeat, ...

    Args:
        symbols: List of symbol values

    Returns:
        Interleaved symbol sequence with repeats
    """
    if len(symbols) == 0:
        return []

    # Create interleaved output with repeats
    # Simple approach: just list each symbol twice to match the repeat pattern
    output = []
    for i in range(len(symbols)):
        output.append(symbols[i])
        output.append(symbols[i])  # Each symbol appears twice

    return output


def remove_interleaving(symbols: List[int]) -> List[int]:
    """
    Remove DSC interleaving and apply error correction.

    Symbols are sent with repeats: S0, S0_repeat, S1, S1_repeat, ...
    Uses error correction: if a symbol disagrees with its repeat,
    use the one with valid check bits.

    Args:
        symbols: Interleaved symbol sequence (symbol, symbol_repeat, symbol, ...)

    Returns:
        De-interleaved symbols with error correction applied
    """
    output = []

    # Extract symbols from interleaved pairs
    for i in range(0, len(symbols), 2):
        if i + 1 < len(symbols):
            copy1 = symbols[i]
            copy2 = symbols[i + 1]

            # Validate check bits on both
            val1, err1 = dsc_decode_symbol(copy1)
            val2, err2 = dsc_decode_symbol(copy2)

            # Choose the one with valid check bits, or first if both bad
            if not err1:
                output.append(val1)
            elif not err2:
                output.append(val2)
            else:
                output.append(val1)  # Both bad, use first
        else:
            # Odd number of symbols, take the last one
            val, _ = dsc_decode_symbol(symbols[i])
            output.append(val)

    return output


def build_dsc_call(
    format_spec: str,
    address_mmsi: str,
    category: str,
    self_mmsi: str,
    telecommand1: str,
    telecommand2: str,
    eos: str = 'no_info',
    distress_info: Optional[Dict] = None
) -> List[int]:
    """
    Build a complete DSC call as a list of symbol values.

    Args:
        format_spec: Call type ('all_ships', 'selective_call', 'group_call', 'area_call', 'distress_alert', etc.)
        address_mmsi: Destination MMSI (9 digits) or None for broadcast
        category: Call category ('routine', 'safety', 'urgency', 'distress')
        self_mmsi: Caller's MMSI (9 digits)
        telecommand1: First telecommand type
        telecommand2: Second telecommand type
        eos: End of sequence type ('ack_request', 'ack', 'no_info')
        distress_info: Dict with keys 'nature', 'latitude', 'longitude', 'time_hhmm' for distress alerts

    Returns:
        List of 7-bit symbol values (not yet encoded with check bits)
    """
    symbols = []

    # Phasing sequence: DX repeated 6 times (or RX for responses)
    symbols.extend([DX_SYMBOL] * PHASING_REPEATS)

    # Format specifier
    format_code = REVERSE_FORMAT_SPECIFIERS.get(format_spec)
    if format_code is None:
        raise ValueError(f"Unknown format specifier: {format_spec}")
    symbols.append(format_code)

    # Address (MMSI as 9 digits, or geographic for area calls)
    if format_spec == 'area_call':
        # Area calls use lat/lon pairs (5 pairs total)
        # For simplicity, encode as dummy pairs
        address_digits = address_mmsi[:9]
    else:
        address_digits = address_mmsi.zfill(9)

    for digit_char in address_digits:
        symbols.append(int(digit_char))

    # Category
    category_code = REVERSE_CATEGORIES.get(category)
    if category_code is None:
        raise ValueError(f"Unknown category: {category}")
    symbols.append(category_code)

    # Self-ID (caller's MMSI)
    self_mmsi_str = self_mmsi.zfill(9)
    for digit_char in self_mmsi_str:
        symbols.append(int(digit_char))

    # Telecommand 1
    tc1_code = REVERSE_TELECOMMANDS.get(telecommand1)
    if tc1_code is None:
        raise ValueError(f"Unknown telecommand1: {telecommand1}")
    symbols.append(tc1_code)

    # Telecommand 2
    tc2_code = REVERSE_TELECOMMANDS.get(telecommand2)
    if tc2_code is None:
        raise ValueError(f"Unknown telecommand2: {telecommand2}")
    symbols.append(tc2_code)

    # For distress alerts, add nature and position
    if format_spec == 'distress_alert' and distress_info:
        nature_code = REVERSE_DISTRESS_CODES.get(distress_info.get('nature'))
        if nature_code is None:
            nature_code = 107  # undesignated
        symbols.append(nature_code)

        # Position (lat/lon as 8 digits)
        lat = distress_info.get('latitude', 0)
        lon = distress_info.get('longitude', 0)
        lat_min = abs(int(lat * 60)) % 6000  # degrees*60 in 0-5999 range
        lon_min = abs(int(lon * 60)) % 36000  # degrees*60 in 0-35999 range

        # Encode as 4-digit pairs
        lat_str = str(lat_min).zfill(4)
        lon_str = str(lon_min).zfill(4)

        for digit_char in lat_str + lon_str:
            symbols.append(int(digit_char))

        # Time (HHMM UTC)
        time_hhmm = distress_info.get('time_hhmm', '0000')
        time_str = str(time_hhmm).zfill(4)
        for digit_char in time_str:
            symbols.append(int(digit_char))

    # End of Sequence
    eos_codes = {
        'ack_request': 120,
        'ack': 121,
        'no_info': 122,
    }
    eos_code = eos_codes.get(eos, 122)
    symbols.append(eos_code)

    # Compute and append ECC
    ecc = compute_ecc(symbols)
    symbols.append(ecc)

    return symbols


def symbols_to_bits(symbols: List[int]) -> List[int]:
    """Convert symbol values to bit sequence (MSB first)."""
    bits = []
    for sym in symbols:
        for i in range(6, -1, -1):
            bits.append((sym >> i) & 1)
    return bits


def bits_to_symbols(bits: List[int]) -> List[int]:
    """Convert bit sequence to symbol values (7 bits per symbol)."""
    symbols = []
    for i in range(0, len(bits), 7):
        if i + 7 <= len(bits):
            sym = 0
            for j in range(7):
                sym = (sym << 1) | bits[i + j]
            symbols.append(sym)
    return symbols


def fsk_modulate(
    bits: List[int],
    sample_rate: int = SAMPLE_RATE,
    baud_rate: int = BAUD_RATE,
    mark_freq: float = MARK_FREQ,
    space_freq: float = SPACE_FREQ
) -> np.ndarray:
    """
    Modulate bits to FSK audio using continuous phase.

    Args:
        bits: List of bits (0 or 1)
        sample_rate: Output sample rate in Hz
        baud_rate: Bit rate in bits/second
        mark_freq: Frequency for binary 1 in Hz
        space_freq: Frequency for binary 0 in Hz

    Returns:
        Audio samples as numpy array
    """
    samples_per_bit = sample_rate // baud_rate
    total_samples = len(bits) * samples_per_bit

    audio = np.zeros(total_samples, dtype=np.float32)
    phase = 0.0

    for bit_idx, bit in enumerate(bits):
        freq = mark_freq if bit == 1 else space_freq

        for sample_idx in range(samples_per_bit):
            global_idx = bit_idx * samples_per_bit + sample_idx
            t = global_idx / sample_rate

            # Continuous phase
            phase = (2 * np.pi * freq * t) % (2 * np.pi)
            audio[global_idx] = np.sin(phase)

    return audio


def fsk_demodulate(
    audio: np.ndarray,
    sample_rate: int = SAMPLE_RATE,
    baud_rate: int = BAUD_RATE,
    mark_freq: float = MARK_FREQ,
    space_freq: float = SPACE_FREQ
) -> List[int]:
    """
    Demodulate FSK audio to bits using energy detection.

    Args:
        audio: Audio samples as numpy array
        sample_rate: Sample rate in Hz
        baud_rate: Bit rate in bits/second
        mark_freq: Frequency for binary 1 in Hz
        space_freq: Frequency for binary 0 in Hz

    Returns:
        List of detected bits (0 or 1)
    """
    samples_per_bit = sample_rate // baud_rate
    num_bits = len(audio) // samples_per_bit

    bits = []

    for bit_idx in range(num_bits):
        start_idx = bit_idx * samples_per_bit
        end_idx = start_idx + samples_per_bit

        if end_idx > len(audio):
            break

        bit_samples = audio[start_idx:end_idx]

        # Correlate with mark (1) and space (0) frequencies
        t = np.arange(len(bit_samples)) / sample_rate

        mark_signal = np.sin(2 * np.pi * mark_freq * t)
        space_signal = np.sin(2 * np.pi * space_freq * t)

        mark_energy = np.sum(bit_samples * mark_signal) ** 2
        space_energy = np.sum(bit_samples * space_signal) ** 2

        bit = 1 if mark_energy > space_energy else 0
        bits.append(bit)

    return bits


def find_dot_pattern(bits: List[int]) -> int:
    """
    Find the bit synchronization dot pattern (200 alternating bits).

    Looks for the best match with both orientations.

    Returns the index where the pattern starts, or -1 if not found.
    """
    if len(bits) < 200:
        return -1

    best_idx = -1
    best_score = 0

    for start in range(len(bits) - 200):
        # Count matches with both orientations
        matches = sum(1 for i in range(200) if bits[start + i] == (i & 1))
        matches_inv = sum(1 for i in range(200) if bits[start + i] == (1 - (i & 1)))

        # Use the best match
        max_matches = max(matches, matches_inv)

        # Keep track of the best match (should be ~200)
        if max_matches > best_score:
            best_score = max_matches
            best_idx = start

    # Accept if at least 75% match (150 out of 200)
    if best_score >= 150:
        return best_idx

    return -1


def find_phasing_sequence(bits: List[int], start_idx: int = 0) -> Tuple[int, str]:
    """
    Find the phasing sequence (DX or RX repeated 6 times).

    The phasing sequence consists of 10-bit symbols:
    - DX (126) encoded as 10-bit = 0011111110 (binary)
    - RX (127) encoded as 10-bit = 0001111111 (binary)
    - Repeated 6 times = 60 bits

    Allows some tolerance for demodulation errors.

    Returns tuple of (index where sequence found, 'DX' or 'RX')
    or (-1, '') if not found.
    """
    # Extract 10-bit symbols and check for 6 repeats of roughly same value
    for start in range(start_idx, len(bits) - 60):
        symbols = []
        all_valid = True

        for sym_idx in range(6):
            bit_idx = start + sym_idx * 10

            if bit_idx + 10 > len(bits):
                all_valid = False
                break

            sym = 0
            for i in range(10):
                sym = (sym << 1) | (bits[bit_idx + i] if bit_idx + i < len(bits) else 0)

            symbols.append(sym)

        if not all_valid:
            continue

        # Check if all 6 symbols are similar (within 2-3 bits difference)
        # and have mostly 1s (indicating DX or RX)
        first = symbols[0]

        # DX should have ~6-9 ones (after demod errors), RX should have ~9-10 ones
        is_phasing = all(_popcount(sym) >= 5 for sym in symbols)  # At least 5 ones in each

        if is_phasing:
            # All symbols should be identical or very similar
            is_same = all(sym == first or _popcount(sym ^ first) <= 2 for sym in symbols)

            if is_same:
                # Determine if DX or RX based on popcount
                avg_ones = sum(_popcount(sym) for sym in symbols) / 6
                phasing_type = 'RX' if avg_ones >= 8.5 else 'DX'
                return start, phasing_type

    return -1, ''
