#!/usr/bin/env python3
"""
Scan Mednafen's memory for Dr. Mario specific patterns.
We'll look for known memory layout patterns.
"""

import subprocess
import sys

def get_mednafen_pid():
    result = subprocess.run(['pgrep', '-x', 'mednafen'],
                           capture_output=True, text=True)
    if result.returncode == 0 and result.stdout.strip():
        return int(result.stdout.strip().split('\n')[0])
    return None

def get_memory_regions(pid):
    regions = []
    with open(f'/proc/{pid}/maps', 'r') as f:
        for line in f:
            parts = line.split()
            if len(parts) >= 2:
                perms = parts[1]
                if 'r' in perms:
                    addr_range = parts[0].split('-')
                    start = int(addr_range[0], 16)
                    end = int(addr_range[1], 16)
                    name = parts[-1] if len(parts) > 5 else "anonymous"
                    regions.append((start, end, perms, name))
    return regions

def read_memory(pid, addr, size):
    try:
        with open(f'/proc/{pid}/mem', 'rb') as f:
            f.seek(addr)
            return f.read(size)
    except:
        return None

def search_pattern(pid, regions, pattern, max_results=20):
    """Search for a byte pattern in memory."""
    results = []
    for start, end, perms, name in regions:
        size = end - start
        if size > 0x10000000:  # Skip huge regions
            continue

        # Read in chunks
        chunk_size = 0x100000  # 1MB
        for chunk_start in range(start, end, chunk_size):
            chunk_end = min(chunk_start + chunk_size, end)
            data = read_memory(pid, chunk_start, chunk_end - chunk_start)
            if data is None:
                continue

            offset = 0
            while True:
                idx = data.find(pattern, offset)
                if idx == -1:
                    break
                results.append(chunk_start + idx)
                if len(results) >= max_results:
                    return results
                offset = idx + 1

    return results

def main():
    pid = get_mednafen_pid()
    if pid is None:
        print("Mednafen not running!")
        return 1

    print(f"Found Mednafen PID: {pid}")
    regions = get_memory_regions(pid)

    # Known Dr. Mario patterns:
    # - Virus tile values: $D0, $D1, $D2
    # - If we're in a game, player 2 playfield ($0500-$057F) should have viruses

    # Search for virus patterns - a sequence of virus tiles
    # In active game, playfield has viruses like D0, D1, D2 interspersed
    print("\nSearching for virus tile sequences...")

    # Look for sequences that look like virus patterns
    # Try searching for three consecutive different virus types
    patterns_to_try = [
        (bytes([0xD0, 0xD1, 0xD2]), "Yellow-Red-Blue sequence"),
        (bytes([0xD0, 0x00, 0xD1]), "Yellow-empty-Red"),
        (bytes([0xD1, 0x00, 0xD0]), "Red-empty-Yellow"),
    ]

    for pattern, desc in patterns_to_try:
        print(f"\nLooking for {desc}: {pattern.hex()}")
        results = search_pattern(pid, regions, pattern, 5)
        if results:
            print(f"  Found {len(results)} matches:")
            for addr in results:
                print(f"    {addr:016x}")
                # Dump context
                data = read_memory(pid, addr - 32, 128)
                if data:
                    for i in range(0, len(data), 16):
                        line_addr = addr - 32 + i
                        hex_part = ' '.join(f'{b:02x}' for b in data[i:i+16])
                        print(f"      {line_addr:016x}: {hex_part}")
        else:
            print("  No matches")

    # Also try to find the value 0x03 at what would be center column
    # or look for the frame counter pattern

    # Search for a 128-byte block that could be playfield
    # (8 columns x 16 rows, with virus tiles D0-D2)
    print("\n\nSearching for potential playfield (128 bytes with virus tiles)...")
    for start, end, perms, name in regions:
        size = end - start
        if size < 0x1000 or size > 0x1000000:
            continue

        data = read_memory(pid, start, min(size, 0x100000))
        if data is None:
            continue

        # Look for 128-byte blocks with D0/D1/D2 values
        for offset in range(0, len(data) - 128, 8):  # Check every 8 bytes
            block = data[offset:offset+128]
            virus_count = sum(1 for b in block if b in (0xD0, 0xD1, 0xD2))

            if 3 <= virus_count <= 20:  # Typical virus count
                empty_count = sum(1 for b in block if b == 0xFF or b == 0x00)
                if empty_count > 80:  # Mostly empty with some viruses
                    addr = start + offset
                    print(f"\nPotential playfield at {addr:016x} ({virus_count} viruses, {empty_count} empty)")
                    for row in range(16):
                        row_data = block[row*8:(row+1)*8]
                        hex_part = ' '.join(f'{b:02x}' for b in row_data)
                        print(f"  Row {row:2d}: {hex_part}")

                    # Check what's at -0x100 to -0x80 (might be player data)
                    player_area = read_memory(pid, addr - 0x100, 0x100)
                    if player_area:
                        print(f"\n  Player data area (at {addr-0x100:016x}):")
                        for i in range(0, 0x100, 16):
                            hex_part = ' '.join(f'{b:02x}' for b in player_area[i:i+16])
                            print(f"    {addr-0x100+i:016x}: {hex_part}")

                    return 0  # Found one, stop

    print("\nNo playfield pattern found.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
