#!/usr/bin/env python3
"""
Test the Mednafen MCP server functionality.
Run this while Mednafen is running with Dr. Mario in a VS match.
"""

import sys
sys.path.insert(0, '.')
from mcp_server import MednafenMCP

def main():
    mcp = MednafenMCP()

    print("Testing Mednafen MCP Server")
    print("=" * 50)

    # Test connect
    print("\n1. Connecting to Mednafen...")
    result = mcp.connect()
    print(f"   Result: {result}")

    if "error" in result:
        print("\nMednafen not running. Start it with Dr. Mario VS CPU mode.")
        return 1

    # Test find_ram
    print("\n2. Finding NES RAM...")
    result = mcp.find_nes_ram()
    print(f"   Found: {result.get('found', False)}")
    if result.get('candidates'):
        for c in result['candidates']:
            print(f"   - {c['address']:016x}: {c['virus_count']} viruses")

    if not result.get('found'):
        print("\n   NES RAM not found. Make sure you're in an active VS match!")
        return 1

    # Test game_state
    print("\n3. Getting game state...")
    state = mcp.get_game_state()
    if "error" not in state:
        colors = ["Yellow", "Red", "Blue"]
        print(f"   Left color: {colors[state['left_color']]}")
        print(f"   Right color: {colors[state['right_color']]}")
        print(f"   Position: X={state['x_pos']}, Y={state['y_pos']}")
        print(f"   P2 Viruses: {state['p2_virus_count']}")
        print(f"   Frame: {state['frame_counter']}")
        print(f"   Virus positions: {len(state['viruses'])} found")
        for v in state['viruses'][:5]:
            print(f"     - Row {v['row']}, Col {v['col']}: {v['color']}")
        if len(state['viruses']) > 5:
            print(f"     ... and {len(state['viruses']) - 5} more")
    else:
        print(f"   Error: {state['error']}")

    # Test read_memory
    print("\n4. Reading specific addresses...")
    for addr, name in [(0x0381, "Left Color"), (0x0382, "Right Color"),
                       (0x0385, "X Pos"), (0x03A4, "P2 Viruses")]:
        result = mcp.read_nes_ram(addr, 1)
        if "error" not in result:
            print(f"   ${addr:04X} ({name}): {result['values'][0]:#04x}")
        else:
            print(f"   ${addr:04X} ({name}): Error - {result['error']}")

    print("\n" + "=" * 50)
    print("MCP Server test complete!")
    return 0

if __name__ == "__main__":
    sys.exit(main())
