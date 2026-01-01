#!/usr/bin/env python3
"""
Mednafen MCP Server
Provides memory reading/writing capabilities for NES emulation in Mednafen.

Uses /proc/<pid>/mem for direct memory access to the emulator process.
"""

import json
import sys
import subprocess
import re
import os
import struct
from typing import Any

# MCP Protocol version
PROTOCOL_VERSION = "2024-11-05"

# Mednafen NES RAM typically mapped in the process memory
# We'll need to find the actual address dynamically

def find_mednafen_pid() -> int | None:
    """Find the PID of running Mednafen process."""
    try:
        result = subprocess.run(['pgrep', '-x', 'mednafen'],
                                capture_output=True, text=True)
        if result.returncode == 0:
            pids = result.stdout.strip().split('\n')
            if pids and pids[0]:
                return int(pids[0])
    except Exception:
        pass
    return None


def find_memory_region(pid: int, pattern: str = "heap") -> tuple[int, int] | None:
    """Find a memory region in the process maps."""
    try:
        with open(f'/proc/{pid}/maps', 'r') as f:
            for line in f:
                if pattern in line.lower():
                    parts = line.split()
                    addr_range = parts[0].split('-')
                    start = int(addr_range[0], 16)
                    end = int(addr_range[1], 16)
                    return (start, end)
    except Exception:
        pass
    return None


def read_process_memory(pid: int, address: int, size: int) -> bytes | None:
    """Read memory from a process."""
    try:
        with open(f'/proc/{pid}/mem', 'rb') as f:
            f.seek(address)
            return f.read(size)
    except Exception as e:
        return None


def write_process_memory(pid: int, address: int, data: bytes) -> bool:
    """Write memory to a process."""
    try:
        with open(f'/proc/{pid}/mem', 'wb') as f:
            f.seek(address)
            f.write(data)
            return True
    except Exception:
        return False


def search_memory_for_pattern(pid: int, pattern: bytes,
                               start: int, end: int) -> list[int]:
    """Search for a byte pattern in process memory."""
    results = []
    try:
        with open(f'/proc/{pid}/mem', 'rb') as f:
            chunk_size = 0x10000
            for addr in range(start, end, chunk_size):
                try:
                    f.seek(addr)
                    data = f.read(min(chunk_size, end - addr))
                    offset = 0
                    while True:
                        idx = data.find(pattern, offset)
                        if idx == -1:
                            break
                        results.append(addr + idx)
                        offset = idx + 1
                except Exception:
                    continue
    except Exception:
        pass
    return results


def get_all_memory_regions(pid: int) -> list[tuple[int, int, str, str]]:
    """Get all readable/writable memory regions."""
    regions = []
    try:
        with open(f'/proc/{pid}/maps', 'r') as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 2:
                    perms = parts[1]
                    if 'r' in perms and 'w' in perms:
                        addr_range = parts[0].split('-')
                        start = int(addr_range[0], 16)
                        end = int(addr_range[1], 16)
                        name = parts[-1] if len(parts) > 5 else "anonymous"
                        regions.append((start, end, perms, name))
    except Exception:
        pass
    return regions


class MednafenMCP:
    """MCP Server for Mednafen."""

    # Dr. Mario memory addresses
    ADDR_LEFT_COLOR = 0x0381      # Current capsule left color (0-2)
    ADDR_RIGHT_COLOR = 0x0382     # Current capsule right color (0-2)
    ADDR_X_POS = 0x0385           # Current capsule X position
    ADDR_Y_POS = 0x0386           # Current capsule Y position
    ADDR_P1_VIRUSES = 0x0324      # Player 1 virus count
    ADDR_P2_VIRUSES = 0x03A4      # Player 2 virus count
    ADDR_P1_PLAYFIELD = 0x0400    # Player 1 playfield (128 bytes)
    ADDR_P2_PLAYFIELD = 0x0500    # Player 2 playfield (128 bytes)
    ADDR_GAME_MODE = 0x0046       # Game mode/state
    ADDR_FRAME_COUNTER = 0x0043   # Frame counter

    # Virus tile values
    VIRUS_YELLOW = 0xD0
    VIRUS_RED = 0xD1
    VIRUS_BLUE = 0xD2

    def __init__(self):
        self.pid: int | None = None
        self.nes_ram_base: int | None = None  # Base address of NES RAM in process

    def connect(self) -> dict:
        """Connect to Mednafen process."""
        self.pid = find_mednafen_pid()
        if self.pid is None:
            return {"error": "Mednafen not running"}

        # Try to auto-discover NES RAM
        ram_result = self._discover_nes_ram()

        return {
            "success": True,
            "pid": self.pid,
            "nes_ram_base": hex(self.nes_ram_base) if self.nes_ram_base else None,
            "message": f"Connected to Mednafen (PID {self.pid})" +
                      (f", NES RAM at {self.nes_ram_base:016x}" if self.nes_ram_base else ", NES RAM not found yet")
        }

    def _discover_nes_ram(self) -> dict:
        """
        Discover NES RAM by searching for Dr. Mario playfield patterns.

        Strategy: Look for 128-byte blocks that match playfield characteristics:
        - Contains virus tiles (0xD0, 0xD1, 0xD2)
        - Contains empty cells (0xFF)
        - At offset -0x500, color values at 0x381/0x382 are valid (0-2)
        """
        if self.pid is None:
            return {"error": "Not connected"}

        regions = get_all_memory_regions(self.pid)
        candidates = []

        for start, end, perms, name in regions:
            size = end - start
            if size < 0x800 or size > 0x10000000:
                continue

            data = read_process_memory(self.pid, start, min(size, 0x1000000))
            if data is None or len(data) < 0x600:
                continue

            # Search for playfield pattern (at offset 0x500 from RAM base)
            for offset in range(0, len(data) - 0x600, 16):
                playfield = data[offset + 0x500:offset + 0x580]
                if len(playfield) < 128:
                    continue

                # Count viruses and empty cells
                virus_count = sum(1 for b in playfield if b in (0xD0, 0xD1, 0xD2))
                empty_count = sum(1 for b in playfield if b == 0xFF)

                # Valid playfield: some viruses, mostly empty
                if 3 <= virus_count <= 84 and empty_count > 40:
                    # Validate color values at expected addresses
                    color_left = data[offset + 0x381]
                    color_right = data[offset + 0x382]

                    if color_left <= 2 and color_right <= 2:
                        ram_base = start + offset
                        candidates.append({
                            "address": ram_base,
                            "virus_count": virus_count,
                            "empty_count": empty_count,
                            "left_color": color_left,
                            "right_color": color_right
                        })

                        # Use first valid candidate
                        if len(candidates) == 1:
                            self.nes_ram_base = ram_base

                if len(candidates) >= 3:
                    break
            if len(candidates) >= 3:
                break

        return {
            "found": len(candidates) > 0,
            "candidates": candidates[:5],
            "nes_ram_base": hex(self.nes_ram_base) if self.nes_ram_base else None
        }

    def read_nes_ram(self, address: int, size: int = 1) -> dict:
        """Read from NES RAM (address $0000-$07FF)."""
        if self.pid is None:
            return {"error": "Not connected"}

        if self.nes_ram_base is None:
            # Try to discover RAM first
            self._discover_nes_ram()
            if self.nes_ram_base is None:
                return {"error": "NES RAM not found. Is a game running?"}

        if address < 0 or address > 0x7FF:
            return {"error": f"Address {address:04X} out of NES RAM range"}

        data = read_process_memory(self.pid, self.nes_ram_base + address, size)
        if data is None:
            return {"error": "Failed to read memory"}

        return {
            "address": f"${address:04X}",
            "size": size,
            "data": data.hex(),
            "values": list(data)
        }

    def write_nes_ram(self, address: int, data: list[int]) -> dict:
        """Write to NES RAM."""
        if self.pid is None:
            return {"error": "Not connected"}

        if self.nes_ram_base is None:
            return {"error": "NES RAM not found"}

        if address < 0 or address > 0x7FF:
            return {"error": f"Address {address:04X} out of NES RAM range"}

        success = write_process_memory(self.pid, self.nes_ram_base + address, bytes(data))
        return {"success": success}

    def get_game_state(self) -> dict:
        """Get current Dr. Mario game state."""
        if self.pid is None:
            return {"error": "Not connected"}

        if self.nes_ram_base is None:
            self._discover_nes_ram()
            if self.nes_ram_base is None:
                return {"error": "NES RAM not found"}

        # Read key game state values
        data = read_process_memory(self.pid, self.nes_ram_base, 0x600)
        if data is None:
            return {"error": "Failed to read memory"}

        # Parse Dr. Mario specific values
        p2_playfield = data[0x500:0x580]
        viruses = []
        for i, b in enumerate(p2_playfield):
            if b in (0xD0, 0xD1, 0xD2):
                col = i % 8
                row = i // 8
                color = {0xD0: "yellow", 0xD1: "red", 0xD2: "blue"}[b]
                viruses.append({"row": row, "col": col, "color": color})

        return {
            "left_color": data[0x381],
            "right_color": data[0x382],
            "x_pos": data[0x385],
            "y_pos": data[0x386],
            "p2_virus_count": data[0x3A4],
            "frame_counter": data[0x43],
            "viruses": viruses,
            "playfield_hex": p2_playfield.hex()
        }

    def find_nes_ram(self) -> dict:
        """
        Attempt to find NES RAM in Mednafen's process memory.
        """
        if self.pid is None:
            return {"error": "Not connected"}

        return self._discover_nes_ram()

    def get_process_maps(self) -> dict:
        """Get all memory maps for the Mednafen process."""
        if self.pid is None:
            return {"error": "Not connected"}

        try:
            with open(f'/proc/{self.pid}/maps', 'r') as f:
                maps = f.read()
            return {"maps": maps}
        except Exception as e:
            return {"error": str(e)}


# MCP Protocol handlers
def handle_initialize(params: dict) -> dict:
    """Handle initialization request."""
    return {
        "protocolVersion": PROTOCOL_VERSION,
        "capabilities": {
            "tools": {}
        },
        "serverInfo": {
            "name": "mednafen-mcp",
            "version": "0.1.0"
        }
    }


def handle_tools_list(params: dict) -> dict:
    """List available tools."""
    return {
        "tools": [
            {
                "name": "connect",
                "description": "Connect to running Mednafen process and auto-discover NES RAM",
                "inputSchema": {
                    "type": "object",
                    "properties": {}
                }
            },
            {
                "name": "read_memory",
                "description": "Read bytes from NES RAM (0x0000-0x07FF)",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "address": {
                            "type": "integer",
                            "description": "NES RAM address (0x0000-0x07FF)"
                        },
                        "size": {
                            "type": "integer",
                            "description": "Number of bytes to read",
                            "default": 1
                        }
                    },
                    "required": ["address"]
                }
            },
            {
                "name": "write_memory",
                "description": "Write bytes to NES RAM",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "address": {
                            "type": "integer",
                            "description": "NES RAM address (0x0000-0x07FF)"
                        },
                        "data": {
                            "type": "array",
                            "items": {"type": "integer"},
                            "description": "Bytes to write (as array of integers 0-255)"
                        }
                    },
                    "required": ["address", "data"]
                }
            },
            {
                "name": "game_state",
                "description": "Get Dr. Mario game state (capsule colors, position, viruses)",
                "inputSchema": {
                    "type": "object",
                    "properties": {}
                }
            },
            {
                "name": "find_ram",
                "description": "Search for NES RAM in process memory",
                "inputSchema": {
                    "type": "object",
                    "properties": {}
                }
            },
            {
                "name": "get_maps",
                "description": "Get process memory maps (debugging)",
                "inputSchema": {
                    "type": "object",
                    "properties": {}
                }
            }
        ]
    }


# Global MCP instance
mcp = MednafenMCP()


def handle_tool_call(name: str, arguments: dict) -> dict:
    """Handle a tool call."""
    if name == "connect":
        return mcp.connect()
    elif name == "read_memory":
        return mcp.read_nes_ram(
            arguments.get("address", 0),
            arguments.get("size", 1)
        )
    elif name == "write_memory":
        return mcp.write_nes_ram(
            arguments.get("address", 0),
            arguments.get("data", [])
        )
    elif name == "game_state":
        return mcp.get_game_state()
    elif name == "get_maps":
        return mcp.get_process_maps()
    elif name == "find_ram":
        return mcp.find_nes_ram()
    else:
        return {"error": f"Unknown tool: {name}"}


def process_message(message: dict) -> dict:
    """Process an incoming MCP message."""
    method = message.get("method", "")
    params = message.get("params", {})
    msg_id = message.get("id")

    if method == "initialize":
        result = handle_initialize(params)
    elif method == "tools/list":
        result = handle_tools_list(params)
    elif method == "tools/call":
        tool_name = params.get("name", "")
        tool_args = params.get("arguments", {})
        content = handle_tool_call(tool_name, tool_args)
        result = {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(content, indent=2)
                }
            ]
        }
    else:
        result = {"error": f"Unknown method: {method}"}

    response = {"jsonrpc": "2.0", "id": msg_id, "result": result}
    return response


def main():
    """Main MCP server loop using stdio."""
    while True:
        try:
            line = sys.stdin.readline()
            if not line:
                break

            message = json.loads(line)
            response = process_message(message)

            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()

        except json.JSONDecodeError:
            continue
        except Exception as e:
            error_response = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32603, "message": str(e)}
            }
            sys.stdout.write(json.dumps(error_response) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
