# Mednafen MCP Server

MCP (Model Context Protocol) server for reading/writing NES memory in Mednafen emulator.
Specifically designed for Dr. Mario game state inspection and manipulation.

## Features

- Auto-discovers NES RAM in Mednafen's process memory
- Read/write NES RAM ($0000-$07FF)
- Dr. Mario game state parsing (capsule colors, position, viruses)
- Process memory inspection tools

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

- `connect` - Connect to Mednafen and auto-discover NES RAM
- `read_memory` - Read bytes from NES RAM
- `write_memory` - Write bytes to NES RAM
- `game_state` - Get Dr. Mario game state (colors, position, viruses)
- `find_ram` - Search for NES RAM in process memory

## Dr. Mario Memory Map

| Address | Description |
|---------|-------------|
| $0043 | Frame counter |
| $0046 | Game mode |
| $0381 | Current capsule left color (0=Yellow, 1=Red, 2=Blue) |
| $0382 | Current capsule right color |
| $0385 | Current capsule X position |
| $0386 | Current capsule Y position |
| $0324 | Player 1 virus count |
| $03A4 | Player 2 virus count |
| $0400-$047F | Player 1 playfield (8x16) |
| $0500-$057F | Player 2 playfield (8x16) |

Virus tile values: `$D0`=Yellow, `$D1`=Red, `$D2`=Blue, `$FF`=Empty
