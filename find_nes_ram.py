#!/usr/bin/env python3
"""
Find NES RAM in Mednafen's process memory.
Uses known memory patterns from Dr. Mario to locate the RAM base.
"""

import subprocess
import sys
import os

def get_mednafen_pid():
    result = subprocess.run(['pgrep', '-x', 'mednafen'],
                           capture_output=True, text=True)
    if result.returncode == 0 and result.stdout.strip():
        return int(result.stdout.strip().split('\n')[0])
    return None

def get_memory_regions(pid):
    """Get readable/writable memory regions."""
    regions = []
    with open(f'/proc/{pid}/maps', 'r') as f:
        for line in f:
            parts = line.split()
            if len(parts) >= 2:
                perms = parts[1]
                if 'r' in perms and 'w' in perms:  # readable + writable
                    addr_range = parts[0].split('-')
                    start = int(addr_range[0], 16)
                    end = int(addr_range[1], 16)
                    name = parts[-1] if len(parts) > 5 else "anonymous"
                    regions.append((start, end, perms, name))
    return regions

def read_memory(pid, addr, size):
    """Read memory from process."""
    try:
        with open(f'/proc/{pid}/mem', 'rb') as f:
            f.seek(addr)
            return f.read(size)
    except Exception as e:
        return None

def search_for_nes_ram(pid, regions):
    """
    Search for NES RAM by looking for the characteristic 2KB RAM pattern.
    NES RAM is mirrored: $0000-$07FF repeats at $0800, $1000, $1800.

    We look for a 2KB region where bytes repeat every 2KB (mirroring).
    """
    print(f"Searching {len(regions)} memory regions for NES RAM...")

    candidates = []

    for start, end, perms, name in regions:
        size = end - start
        if size < 0x800:  # Need at least 2KB
            continue
        if size > 0x10000000:  # Skip huge regions
            continue

        # Read up to 8KB to check for mirroring pattern
        data = read_memory(pid, start, min(size, 0x2000))
        if data is None or len(data) < 0x800:
            continue

        # Check if first 2KB mirrors (NES characteristic)
        if len(data) >= 0x1000:
            first_2k = data[:0x800]
            second_2k = data[0x800:0x1000]
            if first_2k == second_2k:
                print(f"  Found mirrored 2KB at {start:016x} ({name})")
                candidates.append((start, "mirrored"))

        # Also check for non-zero RAM content
        non_zero = sum(1 for b in data[:0x800] if b != 0)
        if non_zero > 100:  # Has meaningful content
            candidates.append((start, f"active ({non_zero} non-zero bytes)"))

    return candidates

def dump_memory_around(pid, addr, context=0x100):
    """Dump memory around an address."""
    data = read_memory(pid, addr, context)
    if data:
        print(f"\nMemory at {addr:016x}:")
        for i in range(0, len(data), 16):
            hex_part = ' '.join(f'{b:02x}' for b in data[i:i+16])
            ascii_part = ''.join(chr(b) if 32 <= b < 127 else '.' for b in data[i:i+16])
            print(f"  {addr+i:016x}: {hex_part:<48} {ascii_part}")

def main():
    pid = get_mednafen_pid()
    if pid is None:
        print("Mednafen not running!")
        return 1

    print(f"Found Mednafen PID: {pid}")

    regions = get_memory_regions(pid)
    print(f"Found {len(regions)} rw memory regions")

    # Show key regions
    print("\nKey memory regions:")
    for start, end, perms, name in regions[:15]:
        size = end - start
        print(f"  {start:016x}-{end:016x} ({size:>10} bytes) {name}")

    # Search for NES RAM
    print("\nSearching for NES RAM pattern...")
    candidates = search_for_nes_ram(pid, regions)

    if candidates:
        print(f"\nFound {len(candidates)} candidate regions:")
        for addr, desc in candidates[:10]:
            print(f"  {addr:016x}: {desc}")
            dump_memory_around(pid, addr, 0x40)
    else:
        print("\nNo obvious NES RAM found. Trying heap region...")
        # Just dump the start of heap
        for start, end, perms, name in regions:
            if 'heap' in name:
                dump_memory_around(pid, start, 0x100)
                break

    return 0

if __name__ == "__main__":
    sys.exit(main())
