# Mednafen MCP Server

MCP (Model Context Protocol) server for reading/writing NES memory in Mednafen emulator.
Specifically designed for Dr. Mario game state inspection and manipulation.

## Features

- Auto-discovers NES RAM in Mednafen's process memory
- Read/write NES RAM ($0000-$07FF)
- Comprehensive Dr. Mario game state parsing (both players)
- ASCII art playfield visualization
- Auto-reconnection on process restart
- RAM validation to detect game state changes

## Requirements

- Linux (uses `/proc/<pid>/mem` for memory access)
- Mednafen running with Dr. Mario
- Python 3.10+

## Usage

### As MCP Server (for Claude Code)
```bash
python3 mcp_server.py
```

### Testing standalone
```bash
# Start Mednafen with Dr. Mario in VS CPU mode, then:
python3 test_mcp.py
```

## MCP Tools

| Tool | Description |
|------|-------------|
| `connect` | Connect to Mednafen and auto-discover NES RAM |
| `read_memory` | Read bytes from NES RAM (address, size) |
| `write_memory` | Write bytes to NES RAM (address, data[]) |
| `game_state` | Get comprehensive game state for both players |
| `playfield` | Get ASCII art visualization (player: 1 or 2) |
| `find_ram` | Search for NES RAM in process memory |
| `get_maps` | Get process memory maps (debugging) |

## Dr. Mario Memory Map

Source: [Data Crystal Wiki](https://datacrystal.tcrf.net/wiki/Dr._Mario_(NES)/RAM_map)

### System/Global

| Address | Description |
|---------|-------------|
| $0043 | Frame counter (0-255) |
| $0046 | Game mode |
| $008B | Speed cursor position |
| $0096 | Virus level setting |
| $00A5 | Capsule orientation (0=horiz, 1=vert CCW, 2=reverse, 3=vert CW) |

### Player 1 State (base $0300)

| Address | Description |
|---------|-------------|
| $0301 | Falling capsule left color (0=Yellow, 1=Red, 2=Blue) |
| $0302 | Falling capsule right color |
| $0305 | Falling capsule X position (0-7) |
| $0306 | Falling capsule Y position (0-15) |
| $030B | Pill speed (0x26=fastest, 0x85=slowest) |
| $0312 | Frames until drop |
| $0316 | Level number (0-20) |
| $0324 | Virus count remaining |
| $0400-$047F | Playfield tiles (8x16 = 128 bytes) |

### Player 2 State (base $0380, offset +0x80 from P1)

| Address | Description |
|---------|-------------|
| $0381 | Falling capsule left color |
| $0382 | Falling capsule right color |
| $0385 | Falling capsule X position |
| $0386 | Falling capsule Y position |
| $038B | Pill speed |
| $0392 | Frames until drop |
| $0396 | Level number |
| $03A4 | Virus count remaining |
| $0500-$057F | Playfield tiles |

### Game Settings

| Address | Description |
|---------|-------------|
| $0724 | Float pills (non-zero = pills don't fall after matches) |
| $0725 | Wins needed in 2P mode |
| $0727 | Number of players |
| $0740 | Anti-piracy flag (0x00=OK) |

### Tile Values

| Value | Description |
|-------|-------------|
| $FF | Empty cell |
| $D0 | Yellow virus |
| $D1 | Red virus |
| $D2 | Blue virus |
| $4C-$5B | Capsule half tiles |

## Playfield ASCII Legend

```
Y = Yellow virus    y = Yellow capsule half
R = Red virus       r = Red capsule half
B = Blue virus      b = Blue capsule half
. = Empty (0xFF)    ? = Unknown tile
```
