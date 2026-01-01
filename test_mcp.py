#!/usr/bin/env python3
"""
Test the Mednafen MCP server functionality.
Run this while Mednafen is running with Dr. Mario in a VS match.
"""

import sys
import os
os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, '.')
from mcp_server import MednafenMCP

def main():
    mcp = MednafenMCP()

    print("Testing Mednafen MCP Server")
    print("=" * 60)

    # Test connect
    print("\n1. Connecting to Mednafen...")
    result = mcp.connect()
    if "error" in result:
        print(f"   Error: {result['error']}")
        print("\nMednafen not running. Start it with Dr. Mario VS CPU mode.")
        return 1
    print(f"   PID: {result['pid']}")
    print(f"   RAM Base: {result.get('nes_ram_base', 'Not found')}")
    print(f"   Reconnected: {result.get('reconnected', False)}")

    # Test find_ram
    print("\n2. Verifying NES RAM discovery...")
    result = mcp.find_nes_ram()
    print(f"   Found: {result.get('found', False)}")
    if result.get('candidates'):
        for c in result['candidates'][:3]:
            print(f"   - 0x{c['address']:x}: {c['virus_count']} viruses, colors={c['left_color']},{c['right_color']}")

    if not result.get('found'):
        print("\n   NES RAM not found. Make sure you're in an active VS match!")
        return 1

    # Test comprehensive game_state
    print("\n3. Getting comprehensive game state...")
    state = mcp.get_game_state()
    if "error" in state:
        print(f"   Error: {state['error']}")
        return 1

    print(f"   Frame: {state['frame']}")
    print(f"   Game Mode: {state['game_mode']}")
    print(f"   Orientation: {state['orientation_name']} ({state['orientation']})")
    print(f"   Players: {state['num_players']}")

    print("\n   Player 1:")
    p1 = state['player1']
    print(f"     Capsule: {p1['left_color_name']}-{p1['right_color_name']}")
    print(f"     Position: ({p1['x_pos']}, {p1['y_pos']})")
    print(f"     Drop Timer: {p1['drop_timer']}")
    print(f"     Level: {p1['level']}, Speed: {p1['speed']:#04x}")
    print(f"     Viruses: {p1['virus_count']}")
    print(f"     Playfield: {len(p1['playfield']['viruses'])} viruses, {len(p1['playfield']['capsules'])} capsule tiles")

    print("\n   Player 2:")
    p2 = state['player2']
    print(f"     Capsule: {p2['left_color_name']}-{p2['right_color_name']}")
    print(f"     Position: ({p2['x_pos']}, {p2['y_pos']})")
    print(f"     Drop Timer: {p2['drop_timer']}")
    print(f"     Level: {p2['level']}, Speed: {p2['speed']:#04x}")
    print(f"     Viruses: {p2['virus_count']}")
    print(f"     Playfield: {len(p2['playfield']['viruses'])} viruses, {len(p2['playfield']['capsules'])} capsule tiles")

    # Test playfield ASCII
    print("\n4. Playfield visualizations:")
    for player in [1, 2]:
        result = mcp.get_playfield_ascii(player)
        if "error" not in result:
            print(f"\n{result['playfield']}")
        else:
            print(f"   Player {player} Error: {result['error']}")

    # Test read_memory with new addresses
    print("\n5. Reading key memory addresses...")
    addresses = [
        (0x0043, "Frame Counter"),
        (0x0046, "Game Mode"),
        (0x00A5, "Capsule Orientation"),
        (0x0301, "P1 Left Color"),
        (0x0302, "P1 Right Color"),
        (0x0305, "P1 X Position"),
        (0x0306, "P1 Y Position"),
        (0x0316, "P1 Level"),
        (0x0324, "P1 Virus Count"),
        (0x0381, "P2 Left Color"),
        (0x0382, "P2 Right Color"),
        (0x0385, "P2 X Position"),
        (0x0386, "P2 Y Position"),
        (0x03A4, "P2 Virus Count"),
    ]
    for addr, name in addresses:
        result = mcp.read_nes_ram(addr, 1)
        if "error" not in result:
            print(f"   ${addr:04X} ({name:18s}): {result['values'][0]:#04x} ({result['values'][0]:3d})")
        else:
            print(f"   ${addr:04X} ({name:18s}): Error - {result['error']}")

    print("\n" + "=" * 60)
    print("MCP Server test complete!")
    return 0

if __name__ == "__main__":
    sys.exit(main())
