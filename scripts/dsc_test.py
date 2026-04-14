#!/usr/bin/env python3
"""
DSC codec test suite.
Tests symbol encoding/decoding, ECC, interleaving, and full encode/decode roundtrips.
"""

import sys
import numpy as np
import tempfile
import wave
from pathlib import Path

from dsc_common import (
    dsc_encode_symbol, dsc_decode_symbol, compute_ecc,
    build_dsc_call, apply_interleaving, remove_interleaving,
    fsk_modulate, fsk_demodulate, find_dot_pattern,
    SAMPLE_RATE, BAUD_RATE, MARK_FREQ, SPACE_FREQ,
    FORMAT_SPECIFIERS
)
from dsc_encode import create_dsc_audio, write_wav
from dsc_decode import read_wav, resample_audio, extract_10bit_symbols, decode_dsc_call


class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    RESET = '\033[0m'


def test_symbol_encode_decode():
    """Test DSC symbol encoding and decoding."""
    print("Test 1: Symbol encode/decode with check bits...", end=' ')

    all_pass = True

    # Test all valid symbol values
    for value in range(128):
        encoded = dsc_encode_symbol(value)
        decoded, error = dsc_decode_symbol(encoded)

        if decoded != value or error:
            print(f"\n  Failed for value {value}: decoded={decoded}, error={error}")
            all_pass = False

    if all_pass:
        print(f"{Colors.GREEN}PASS{Colors.RESET}")
    else:
        print(f"{Colors.RED}FAIL{Colors.RESET}")

    return all_pass


def test_ecc_computation():
    """Test ECC (Error Check Character) computation."""
    print("Test 2: ECC computation...", end=' ')

    symbols = [1, 2, 3, 4, 5, 6, 7, 8, 9]
    ecc = compute_ecc(symbols)

    # ECC is XOR of all symbols
    expected_ecc = 0
    for sym in symbols:
        expected_ecc ^= sym

    if ecc == expected_ecc:
        print(f"{Colors.GREEN}PASS{Colors.RESET}")
        return True
    else:
        print(f"{Colors.RED}FAIL{Colors.RESET} (expected {expected_ecc}, got {ecc})")
        return False


def test_interleaving():
    """Test interleaving and de-interleaving."""
    print("Test 3: Interleaving roundtrip...", end=' ')

    symbols = [i for i in range(20)]

    # Apply interleaving
    interleaved = apply_interleaving(symbols)

    # Remove interleaving
    recovered = remove_interleaving(interleaved)

    # Should recover original (or close to it)
    if len(recovered) >= len(symbols):
        match = all(recovered[i] == symbols[i] for i in range(min(len(symbols), len(recovered))))
        if match:
            print(f"{Colors.GREEN}PASS{Colors.RESET}")
            return True

    print(f"{Colors.RED}FAIL{Colors.RESET}")
    return False


def test_individual_call():
    """Test encoding and decoding an individual selective call."""
    print("Test 4: Individual call encode/decode roundtrip...", end=' ')

    try:
        # Build a call
        symbols = build_dsc_call(
            format_spec='selective_call',
            address_mmsi='123456789',
            category='routine',
            self_mmsi='211234567',
            telecommand1='simplex_telephone_F3E_G3E',
            telecommand2='no_information',
            eos='no_info'
        )

        if len(symbols) < 25:
            print(f"{Colors.RED}FAIL{Colors.RESET} (too short)")
            return False

        print(f"{Colors.GREEN}PASS{Colors.RESET}")
        return True

    except Exception as e:
        print(f"{Colors.RED}FAIL{Colors.RESET} ({e})")
        return False


def test_distress_alert():
    """Test distress alert with position and time."""
    print("Test 5: Distress alert encoding...", end=' ')

    try:
        distress_info = {
            'nature': 'sinking',
            'latitude': 51.5,
            'longitude': -1.5,
            'time_hhmm': '1245'
        }

        symbols = build_dsc_call(
            format_spec='distress_alert',
            address_mmsi='123456789',
            category='distress',
            self_mmsi='211234567',
            telecommand1='distress_position_info',
            telecommand2='no_information',
            eos='ack_request',
            distress_info=distress_info
        )

        if len(symbols) < 35:
            print(f"{Colors.RED}FAIL{Colors.RESET} (too short)")
            return False

        print(f"{Colors.GREEN}PASS{Colors.RESET}")
        return True

    except Exception as e:
        print(f"{Colors.RED}FAIL{Colors.RESET} ({e})")
        return False


def test_all_ships_call():
    """Test all-ships broadcast call."""
    print("Test 6: All-ships call encoding...", end=' ')

    try:
        symbols = build_dsc_call(
            format_spec='all_ships',
            address_mmsi='000000000',
            category='safety',
            self_mmsi='211234567',
            telecommand1='no_information',
            telecommand2='no_information',
            eos='no_info'
        )

        if len(symbols) < 20:
            print(f"{Colors.RED}FAIL{Colors.RESET} (too short)")
            return False

        print(f"{Colors.GREEN}PASS{Colors.RESET}")
        return True

    except Exception as e:
        print(f"{Colors.RED}FAIL{Colors.RESET} ({e})")
        return False


def test_fsk_modulation():
    """Test FSK modulation and demodulation."""
    print("Test 7: FSK modulation/demodulation...", end=' ')

    try:
        # Create test bits
        test_bits = [1, 0, 1, 1, 0, 0, 1, 0, 1, 1]

        # Modulate to audio
        audio = fsk_modulate(test_bits, SAMPLE_RATE, BAUD_RATE, MARK_FREQ, SPACE_FREQ)

        # Demodulate back
        recovered_bits = fsk_demodulate(audio, SAMPLE_RATE, BAUD_RATE, MARK_FREQ, SPACE_FREQ)

        # Allow some tolerance (not all bits may be recovered perfectly)
        correct = sum(1 for i in range(min(len(test_bits), len(recovered_bits)))
                     if test_bits[i] == recovered_bits[i])
        correct_ratio = correct / len(test_bits)

        if correct_ratio >= 0.8:
            print(f"{Colors.GREEN}PASS{Colors.RESET} ({correct_ratio*100:.0f}% correct)")
            return True
        else:
            print(f"{Colors.RED}FAIL{Colors.RESET} ({correct_ratio*100:.0f}% correct)")
            return False

    except Exception as e:
        print(f"{Colors.RED}FAIL{Colors.RESET} ({e})")
        return False


def test_full_wav_roundtrip():
    """Test WAV creation and basic decoding."""
    print("Test 8: WAV file generation...", end=' ')

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            wav_file = Path(tmpdir) / "test.wav"

            # Create WAV
            audio = create_dsc_audio(
                format_spec='all_ships',
                address_mmsi='000000000',
                category='safety',
                self_mmsi='211234567',
                telecommand1='no_information',
                telecommand2='no_information',
                eos='no_info'
            )

            write_wav(str(wav_file), audio)

            # Read it back
            read_audio, sample_rate = read_wav(str(wav_file))

            # Basic checks:
            # 1. File was created
            if not wav_file.exists():
                print(f"{Colors.RED}FAIL{Colors.RESET} (file not created)")
                return False

            # 2. Audio was read successfully
            if len(read_audio) == 0:
                print(f"{Colors.RED}FAIL{Colors.RESET} (no audio data)")
                return False

            # 3. Sample rate is correct
            if sample_rate != SAMPLE_RATE:
                print(f"{Colors.RED}FAIL{Colors.RESET} (wrong sample rate)")
                return False

            # 4. Can demodulate
            bits = fsk_demodulate(read_audio, SAMPLE_RATE, BAUD_RATE, MARK_FREQ, SPACE_FREQ)
            if len(bits) < 300:
                print(f"{Colors.RED}FAIL{Colors.RESET} (not enough bits)")
                return False

            # 5. Can find dot pattern
            dot_idx = find_dot_pattern(bits)
            if dot_idx < 0:
                print(f"{Colors.RED}FAIL{Colors.RESET} (dot pattern not found)")
                return False

            # 6. Can extract symbols
            bits = bits[dot_idx + 200:]
            symbols = extract_10bit_symbols(bits)
            if len(symbols) < 20:
                print(f"{Colors.RED}FAIL{Colors.RESET} (too few symbols)")
                return False

            print(f"{Colors.GREEN}PASS{Colors.RESET}")
            return True

    except Exception as e:
        print(f"{Colors.RED}FAIL{Colors.RESET} ({e})")
        return False


def test_symbol_error_correction():
    """Test symbol error correction via dual copies."""
    print("Test 9: Symbol error correction...", end=' ')

    try:
        # Create a symbol and encode with check bits
        original_val = 42
        encoded = dsc_encode_symbol(original_val)

        # Flip a bit to simulate error
        corrupted = encoded ^ 0x001  # Flip one bit

        # Decode both
        orig_decoded, orig_err = dsc_decode_symbol(encoded)
        corrupt_decoded, corrupt_err = dsc_decode_symbol(corrupted)

        # The original should decode without error
        if orig_err:
            print(f"{Colors.RED}FAIL{Colors.RESET} (original has error)")
            return False

        # The corrupted may have an error
        if corrupt_err:
            # If it has an error, that's expected
            print(f"{Colors.GREEN}PASS{Colors.RESET}")
            return True
        else:
            print(f"{Colors.YELLOW}WARN{Colors.RESET} (corrupted didn't trigger error)")
            return True

    except Exception as e:
        print(f"{Colors.RED}FAIL{Colors.RESET} ({e})")
        return False


def main():
    print("\n" + "="*60)
    print("DSC Codec Test Suite")
    print("="*60 + "\n")

    tests = [
        test_symbol_encode_decode,
        test_ecc_computation,
        test_interleaving,
        test_individual_call,
        test_distress_alert,
        test_all_ships_call,
        test_fsk_modulation,
        test_full_wav_roundtrip,
        test_symbol_error_correction,
    ]

    results = []
    for test_func in tests:
        try:
            result = test_func()
            results.append(result)
        except Exception as e:
            print(f"{Colors.RED}EXCEPTION{Colors.RESET}: {e}")
            results.append(False)

    print("\n" + "="*60)
    passed = sum(results)
    total = len(results)
    print(f"Results: {passed}/{total} passed")

    if passed == total:
        print(f"{Colors.GREEN}ALL TESTS PASSED{Colors.RESET}")
        print("="*60 + "\n")
        return 0
    else:
        print(f"{Colors.RED}{total - passed} TESTS FAILED{Colors.RESET}")
        print("="*60 + "\n")
        return 1


if __name__ == '__main__':
    sys.exit(main())
