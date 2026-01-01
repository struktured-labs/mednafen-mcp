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
import time
import signal
from typing import Any

# MCP Protocol version
PROTOCOL_VERSION = "2024-11-05"

# Default ROM paths to search for Dr. Mario
DEFAULT_ROM_PATHS = [
    "/home/struktured/gaming/roms/NES/USA/drmario_vs_cpu.nes",
    "/home/struktured/gaming/roms/NES/USA/Dr. Mario (USA).nes",
    "/home/struktured/gaming/roms/NES/USA/drmario.nes",
    "drmario_vs_cpu.nes",
    "drmario.nes",
]

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

    # ==========================================================================
    # Dr. Mario Memory Map (from Data Crystal wiki)
    # Source: https://datacrystal.tcrf.net/wiki/Dr._Mario_(NES)/RAM_map
    # ==========================================================================

    # System/Global
    ADDR_FRAME_COUNTER = 0x0043   # Frame counter (0-255, wraps)
    ADDR_GAME_MODE = 0x0046       # Game mode/state
    ADDR_SPEED_CURSOR = 0x008B    # Speed setting cursor position
    ADDR_VIRUS_LEVEL = 0x0096     # Virus level setting
    ADDR_CAPSULE_ORIENT = 0x00A5  # Capsule orientation (0=horiz, 1=vert CCW, 2=reverse, 3=vert CW)

    # Player 1 Capsule State (base $0300)
    ADDR_P1_LEFT_COLOR = 0x0301   # P1 falling capsule left color (0=Yellow, 1=Red, 2=Blue)
    ADDR_P1_RIGHT_COLOR = 0x0302  # P1 falling capsule right color
    ADDR_P1_X_POS = 0x0305        # P1 falling capsule X position (0-7)
    ADDR_P1_Y_POS = 0x0306        # P1 falling capsule Y position (0-15)
    ADDR_P1_DROP_TIMER = 0x0312   # Frames remaining before P1 pill drops
    ADDR_P1_LEVEL = 0x0316        # P1 level number (0-20)
    ADDR_P1_SPEED = 0x030B        # P1 pill speed (0x26=fastest, 0x85=slowest)
    ADDR_P1_VIRUSES = 0x0324      # P1 virus count remaining (decimal)

    # Player 2 Capsule State (base $0380, offset +0x80 from P1)
    ADDR_P2_LEFT_COLOR = 0x0381   # P2 falling capsule left color
    ADDR_P2_RIGHT_COLOR = 0x0382  # P2 falling capsule right color
    ADDR_P2_X_POS = 0x0385        # P2 falling capsule X position
    ADDR_P2_Y_POS = 0x0386        # P2 falling capsule Y position
    ADDR_P2_DROP_TIMER = 0x0392   # Frames remaining before P2 pill drops
    ADDR_P2_LEVEL = 0x0396        # P2 level number
    ADDR_P2_SPEED = 0x038B        # P2 pill speed
    ADDR_P2_VIRUSES = 0x03A4      # P2 virus count remaining

    # Playfields (8 columns x 16 rows = 128 bytes each)
    ADDR_P1_PLAYFIELD = 0x0400    # P1 playfield tiles (top-left to bottom-right)
    ADDR_P2_PLAYFIELD = 0x0500    # P2 playfield tiles

    # Game Settings
    ADDR_NUM_PLAYERS = 0x0727     # Number of players (1 or 2)
    ADDR_FLOAT_PILLS = 0x0724     # Non-zero = pills float (don't fall after matches)
    ADDR_WINS_NEEDED = 0x0725     # Games needed to win in 2P mode
    ADDR_ANTI_PIRACY = 0x0740     # Anti-piracy flag (0x00=OK, 0xFF=failed)

    # Tile Values
    TILE_EMPTY = 0xFF             # Empty cell
    TILE_VIRUS_YELLOW = 0xD0      # Yellow virus
    TILE_VIRUS_RED = 0xD1         # Red virus
    TILE_VIRUS_BLUE = 0xD2        # Blue virus
    # Capsule half tiles: 0x4C-0x5B (various colors/orientations)

    # Color names for display
    COLOR_NAMES = ["Yellow", "Red", "Blue"]
    ORIENTATION_NAMES = ["Horizontal", "Vertical CCW", "Reverse", "Vertical CW"]

    def __init__(self):
        self.pid: int | None = None
        self.nes_ram_base: int | None = None  # Base address of NES RAM in process
        self._last_validate_frame: int = 0    # For RAM validation
        self._validation_failures: int = 0    # Track consecutive failures
        self._mednafen_process: subprocess.Popen | None = None  # Managed process

    def _find_rom(self, rom_path: str | None = None) -> str | None:
        """Find a Dr. Mario ROM file."""
        if rom_path and os.path.exists(rom_path):
            return rom_path

        for path in DEFAULT_ROM_PATHS:
            if os.path.exists(path):
                return path
        return None

    def launch(self, rom_path: str | None = None, headless: bool = True) -> dict:
        """
        Launch Mednafen with Dr. Mario ROM.

        Args:
            rom_path: Path to ROM file (optional, will search default locations)
            headless: Run without display using SDL dummy drivers
        """
        # Check if already running
        existing_pid = find_mednafen_pid()
        if existing_pid:
            self.pid = existing_pid
            self._discover_nes_ram()
            return {
                "success": True,
                "pid": existing_pid,
                "message": "Mednafen already running",
                "launched": False
            }

        # Find ROM
        rom = self._find_rom(rom_path)
        if not rom:
            return {
                "error": f"ROM not found. Searched: {DEFAULT_ROM_PATHS}",
                "hint": "Provide rom_path parameter or place ROM in default location"
            }

        # Build command
        env = os.environ.copy()
        if headless:
            env["SDL_VIDEODRIVER"] = "dummy"
            env["SDL_AUDIODRIVER"] = "dummy"

        cmd = ["mednafen", rom]

        try:
            # Launch Mednafen
            self._mednafen_process = subprocess.Popen(
                cmd,
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True  # Don't kill when parent exits
            )

            # Wait for process to start
            time.sleep(1.0)

            # Verify it's running
            if self._mednafen_process.poll() is not None:
                return {
                    "error": "Mednafen failed to start",
                    "returncode": self._mednafen_process.returncode
                }

            self.pid = self._mednafen_process.pid

            # Wait a bit more for game to initialize, then discover RAM
            time.sleep(1.0)
            self._discover_nes_ram()

            return {
                "success": True,
                "pid": self.pid,
                "rom": rom,
                "headless": headless,
                "nes_ram_base": hex(self.nes_ram_base) if self.nes_ram_base else None,
                "message": f"Launched Mednafen {'(headless)' if headless else ''} with {os.path.basename(rom)}",
                "launched": True
            }

        except FileNotFoundError:
            return {"error": "Mednafen not found in PATH"}
        except Exception as e:
            return {"error": f"Failed to launch: {str(e)}"}

    def shutdown(self) -> dict:
        """Shutdown the managed Mednafen process."""
        if self._mednafen_process is None:
            # Try to find and kill any running Mednafen
            pid = find_mednafen_pid()
            if pid:
                try:
                    os.kill(pid, signal.SIGTERM)
                    time.sleep(0.5)
                    # Check if still running
                    try:
                        os.kill(pid, 0)
                        os.kill(pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    self.pid = None
                    self.nes_ram_base = None
                    return {"success": True, "message": f"Terminated Mednafen (PID {pid})"}
                except Exception as e:
                    return {"error": f"Failed to terminate: {str(e)}"}
            return {"error": "No Mednafen process to shutdown"}

        try:
            self._mednafen_process.terminate()
            try:
                self._mednafen_process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self._mednafen_process.kill()
                self._mednafen_process.wait()

            pid = self._mednafen_process.pid
            self._mednafen_process = None
            self.pid = None
            self.nes_ram_base = None
            return {"success": True, "message": f"Shutdown Mednafen (PID {pid})"}
        except Exception as e:
            return {"error": f"Failed to shutdown: {str(e)}"}

    def _is_process_alive(self) -> bool:
        """Check if the connected process is still running."""
        if self.pid is None:
            return False
        try:
            # Check if process exists
            with open(f'/proc/{self.pid}/stat', 'r'):
                return True
        except (FileNotFoundError, PermissionError):
            return False

    def _validate_ram(self) -> bool:
        """
        Validate that our NES RAM base is still correct.
        Returns True if valid, False if needs rediscovery.
        """
        if self.pid is None or self.nes_ram_base is None:
            return False

        if not self._is_process_alive():
            self.pid = None
            self.nes_ram_base = None
            return False

        # Read a small sample and check it looks like valid Dr. Mario RAM
        data = read_process_memory(self.pid, self.nes_ram_base, 0x400)
        if data is None:
            self._validation_failures += 1
            if self._validation_failures > 3:
                self.nes_ram_base = None
            return False

        # Check that color values at known addresses are valid (0-2)
        p1_left = data[self.ADDR_P1_LEFT_COLOR]
        p1_right = data[self.ADDR_P1_RIGHT_COLOR]
        p2_left = data[self.ADDR_P2_LEFT_COLOR]
        p2_right = data[self.ADDR_P2_RIGHT_COLOR]

        # At least one player should have valid colors
        p1_valid = p1_left <= 2 and p1_right <= 2
        p2_valid = p2_left <= 2 and p2_right <= 2

        if p1_valid or p2_valid:
            self._validation_failures = 0
            return True
        else:
            self._validation_failures += 1
            if self._validation_failures > 5:
                # RAM location might have changed, need rediscovery
                self.nes_ram_base = None
            return False

    def connect(self) -> dict:
        """Connect to Mednafen process."""
        # Check if already connected to a valid process
        if self.pid is not None and self._is_process_alive():
            if self._validate_ram():
                return {
                    "success": True,
                    "pid": self.pid,
                    "nes_ram_base": hex(self.nes_ram_base) if self.nes_ram_base else None,
                    "message": f"Already connected to Mednafen (PID {self.pid})",
                    "reconnected": False
                }

        # Find Mednafen process
        self.pid = find_mednafen_pid()
        if self.pid is None:
            self.nes_ram_base = None
            return {"error": "Mednafen not running"}

        # Reset validation state
        self._validation_failures = 0

        # Try to auto-discover NES RAM
        ram_result = self._discover_nes_ram()

        return {
            "success": True,
            "pid": self.pid,
            "nes_ram_base": hex(self.nes_ram_base) if self.nes_ram_base else None,
            "message": f"Connected to Mednafen (PID {self.pid})" +
                      (f", NES RAM at {self.nes_ram_base:016x}" if self.nes_ram_base else ", NES RAM not found yet"),
            "reconnected": True
        }

    def ensure_connected(self) -> dict | None:
        """Ensure we're connected, reconnect if needed. Returns error dict or None."""
        if self.pid is None or not self._is_process_alive():
            result = self.connect()
            if "error" in result:
                return result
        if not self._validate_ram():
            # Try rediscovery
            self._discover_nes_ram()
            if self.nes_ram_base is None:
                return {"error": "NES RAM not found. Is a game running?"}
        return None

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
        # Auto-reconnect if needed
        error = self.ensure_connected()
        if error:
            return error

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
        # Auto-reconnect if needed
        error = self.ensure_connected()
        if error:
            return error

        if address < 0 or address > 0x7FF:
            return {"error": f"Address {address:04X} out of NES RAM range"}

        success = write_process_memory(self.pid, self.nes_ram_base + address, bytes(data))
        return {"success": success}

    def _parse_playfield(self, data: bytes, player: int = 2) -> dict:
        """Parse playfield data into structured format."""
        offset = self.ADDR_P1_PLAYFIELD if player == 1 else self.ADDR_P2_PLAYFIELD
        playfield = data[offset:offset + 128]

        viruses = []
        capsules = []
        for i, tile in enumerate(playfield):
            col = i % 8
            row = i // 8
            if tile in (self.TILE_VIRUS_YELLOW, self.TILE_VIRUS_RED, self.TILE_VIRUS_BLUE):
                color = {self.TILE_VIRUS_YELLOW: "yellow",
                        self.TILE_VIRUS_RED: "red",
                        self.TILE_VIRUS_BLUE: "blue"}[tile]
                viruses.append({"row": row, "col": col, "color": color, "tile": tile})
            elif tile != self.TILE_EMPTY and tile != 0x00:
                # Capsule half or other tile
                capsules.append({"row": row, "col": col, "tile": tile})

        return {
            "viruses": viruses,
            "capsules": capsules,
            "raw": playfield.hex()
        }

    def _render_playfield_ascii(self, data: bytes, player: int = 2) -> str:
        """Render playfield as ASCII art."""
        offset = self.ADDR_P1_PLAYFIELD if player == 1 else self.ADDR_P2_PLAYFIELD
        playfield = data[offset:offset + 128]

        # Tile to character mapping
        tile_chars = {
            self.TILE_EMPTY: '.',
            self.TILE_VIRUS_YELLOW: 'Y',
            self.TILE_VIRUS_RED: 'R',
            self.TILE_VIRUS_BLUE: 'B',
            0x00: ' ',  # Sometimes empty is 0
        }

        lines = [f"  P{player} Playfield", "  +---------+"]
        for row in range(16):
            row_tiles = playfield[row * 8:(row + 1) * 8]
            row_chars = []
            for tile in row_tiles:
                if tile in tile_chars:
                    row_chars.append(tile_chars[tile])
                elif 0x4C <= tile <= 0x5B:
                    # Capsule halves - color based on tile
                    # Yellow: 0x4C-0x4F, Red: 0x50-0x53, Blue: 0x54-0x57 (approx)
                    if tile < 0x50:
                        row_chars.append('y')
                    elif tile < 0x54:
                        row_chars.append('r')
                    elif tile < 0x58:
                        row_chars.append('b')
                    else:
                        row_chars.append('c')
                else:
                    row_chars.append('?')
            lines.append(f"{row:2d}|{''.join(row_chars)}|")
        lines.append("  +---------+")
        lines.append("   01234567")
        return '\n'.join(lines)

    def get_game_state(self) -> dict:
        """Get comprehensive Dr. Mario game state."""
        # Auto-reconnect if needed
        error = self.ensure_connected()
        if error:
            return error

        # Read all NES RAM (2KB)
        data = read_process_memory(self.pid, self.nes_ram_base, 0x800)
        if data is None:
            return {"error": "Failed to read memory"}

        # Global state
        frame = data[self.ADDR_FRAME_COUNTER]
        game_mode = data[self.ADDR_GAME_MODE]
        orientation = data[self.ADDR_CAPSULE_ORIENT]
        num_players = data[self.ADDR_NUM_PLAYERS] if self.ADDR_NUM_PLAYERS < len(data) else 0

        # Player 1 state
        p1 = {
            "left_color": data[self.ADDR_P1_LEFT_COLOR],
            "right_color": data[self.ADDR_P1_RIGHT_COLOR],
            "left_color_name": self.COLOR_NAMES[data[self.ADDR_P1_LEFT_COLOR]] if data[self.ADDR_P1_LEFT_COLOR] < 3 else "?",
            "right_color_name": self.COLOR_NAMES[data[self.ADDR_P1_RIGHT_COLOR]] if data[self.ADDR_P1_RIGHT_COLOR] < 3 else "?",
            "x_pos": data[self.ADDR_P1_X_POS],
            "y_pos": data[self.ADDR_P1_Y_POS],
            "drop_timer": data[self.ADDR_P1_DROP_TIMER],
            "level": data[self.ADDR_P1_LEVEL],
            "speed": data[self.ADDR_P1_SPEED],
            "virus_count": data[self.ADDR_P1_VIRUSES],
            "playfield": self._parse_playfield(data, 1)
        }

        # Player 2 state
        p2 = {
            "left_color": data[self.ADDR_P2_LEFT_COLOR],
            "right_color": data[self.ADDR_P2_RIGHT_COLOR],
            "left_color_name": self.COLOR_NAMES[data[self.ADDR_P2_LEFT_COLOR]] if data[self.ADDR_P2_LEFT_COLOR] < 3 else "?",
            "right_color_name": self.COLOR_NAMES[data[self.ADDR_P2_RIGHT_COLOR]] if data[self.ADDR_P2_RIGHT_COLOR] < 3 else "?",
            "x_pos": data[self.ADDR_P2_X_POS],
            "y_pos": data[self.ADDR_P2_Y_POS],
            "drop_timer": data[self.ADDR_P2_DROP_TIMER],
            "level": data[self.ADDR_P2_LEVEL],
            "speed": data[self.ADDR_P2_SPEED],
            "virus_count": data[self.ADDR_P2_VIRUSES],
            "playfield": self._parse_playfield(data, 2)
        }

        return {
            "frame": frame,
            "game_mode": game_mode,
            "orientation": orientation,
            "orientation_name": self.ORIENTATION_NAMES[orientation] if orientation < 4 else "?",
            "num_players": num_players,
            "player1": p1,
            "player2": p2
        }

    def get_playfield_ascii(self, player: int = 2) -> dict:
        """Get ASCII art visualization of playfield."""
        # Auto-reconnect if needed
        error = self.ensure_connected()
        if error:
            return error

        data = read_process_memory(self.pid, self.nes_ram_base, 0x600)
        if data is None:
            return {"error": "Failed to read memory"}

        ascii_art = self._render_playfield_ascii(data, player)
        return {"player": player, "playfield": ascii_art}

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
                "name": "launch",
                "description": "Launch Mednafen with Dr. Mario ROM (headless by default)",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "rom_path": {
                            "type": "string",
                            "description": "Path to ROM file (optional, searches default locations)"
                        },
                        "headless": {
                            "type": "boolean",
                            "description": "Run without display (default: true)",
                            "default": True
                        }
                    }
                }
            },
            {
                "name": "shutdown",
                "description": "Shutdown Mednafen process",
                "inputSchema": {
                    "type": "object",
                    "properties": {}
                }
            },
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
                "description": "Get comprehensive Dr. Mario game state for both players",
                "inputSchema": {
                    "type": "object",
                    "properties": {}
                }
            },
            {
                "name": "playfield",
                "description": "Get ASCII art visualization of playfield",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "player": {
                            "type": "integer",
                            "description": "Player number (1 or 2)",
                            "default": 2
                        }
                    }
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
    if name == "launch":
        return mcp.launch(
            arguments.get("rom_path"),
            arguments.get("headless", True)
        )
    elif name == "shutdown":
        return mcp.shutdown()
    elif name == "connect":
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
    elif name == "playfield":
        return mcp.get_playfield_ascii(
            arguments.get("player", 2)
        )
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
