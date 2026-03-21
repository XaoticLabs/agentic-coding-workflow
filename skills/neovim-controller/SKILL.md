---
name: neovim-controller
description: |
  Control a running Neovim instance via RPC socket connection. Use when the user mentions:
  nvim --listen, neovim socket, nvim RPC, neovim-remote, nvr, editor listening, open in nvim,
  show diff in editor, LSP go-to-definition, find references, hover docs, rename symbol,
  navigate to line, split window, open tab, execute Ex command, run vim command,
  buffer state, window layout, nvim plugins, editor integration.
allowed-tools:
  - Bash
  - Read
  - Glob
  - Grep
---

# Neovim RPC Controller

Control a Neovim instance started with `nvim --listen <socket>` via msgpack-RPC.

## Prerequisites

```bash
# Check if tools are available
which nvr        # neovim-remote CLI
python3 -c "import pynvim"  # pynvim library
```

If missing: `pip install neovim-remote pynvim`

## Socket Discovery

Default socket: `/tmp/nvim` or `/tmp/nvim.sock`

```bash
# Find nvim sockets
ls /tmp/nvim* 2>/dev/null
ls /run/user/$(id -u)/nvim* 2>/dev/null
echo $NVIM_LISTEN_ADDRESS
```

If socket path unclear, ask the user.

## Quick Reference

### Open Files

```bash
# Current window
nvr --remote <file>

# New vertical split
nvr -O <file>

# New horizontal split
nvr -o <file>

# New tab
nvr --remote-tab <file>

# Multiple files in splits
nvr -O file1.py file2.py file3.py
```

### Navigate to Location

```bash
# Open file at line
nvr --remote +42 file.py

# Open file at line:column (via Ex command)
nvr --remote file.py -c "call cursor(42, 10)"

# Jump to line in current buffer
nvr -c "42"

# Go to specific location
nvr -c "edit +42 file.py"
```

### Execute Commands

```bash
# Ex command
nvr -c "write"
nvr -c "split | terminal"

# Multiple commands
nvr -c "set number" -c "set relativenumber"

# Lua command
nvr -c "lua vim.notify('Hello from Claude')"

# Silent command (no output)
nvr -s -c "write"
```

### Diff Mode

```bash
# Diff two files
nvr -d file1.py file2.py

# Diff current buffer against file
nvr -c "diffthis" --remote file2.py -c "diffthis"

# Exit diff mode
nvr -c "diffoff!"
```

### Buffer/Window Operations

```bash
# List buffers
nvr --remote-expr "execute('ls')"

# Current file
nvr --remote-expr "expand('%:p')"

# Current line number
nvr --remote-expr "line('.')"

# Window count
nvr --remote-expr "winnr('$')"

# Close current buffer
nvr -c "bdelete"

# Close window
nvr -c "close"
```

## LSP Operations

See [LSP.md](./LSP.md) for complete LSP reference.

### Quick LSP Commands

```bash
# Go to definition
nvr -c "lua vim.lsp.buf.definition()"

# Find references
nvr -c "lua vim.lsp.buf.references()"

# Hover documentation
nvr -c "lua vim.lsp.buf.hover()"

# Rename symbol (prompts user)
nvr -c "lua vim.lsp.buf.rename()"

# Rename symbol (programmatic)
nvr -c "lua vim.lsp.buf.rename('newName')"

# Code actions
nvr -c "lua vim.lsp.buf.code_action()"

# Format buffer
nvr -c "lua vim.lsp.buf.format()"

# Diagnostics
nvr -c "lua vim.diagnostic.open_float()"
nvr -c "lua vim.diagnostic.goto_next()"
```

## Complex Operations with pynvim

For multi-step operations, use the helper script or inline Python:

```bash
python3 neovim-controller/scripts/nvim_helper.py --socket /tmp/nvim --action open --file main.py --line 42
```

Or inline for custom operations:

```python
python3 << 'EOF'
import pynvim
nvim = pynvim.attach('socket', path='/tmp/nvim')

# Open file and navigate
nvim.command('edit main.py')
nvim.call('cursor', 42, 0)

# Get current context
buf = nvim.current.buffer
win = nvim.current.window
print(f"File: {buf.name}, Line: {win.cursor[0]}")
EOF
```

## Workflow: Before Complex Operations

1. **Verify connection**:
   ```bash
   nvr --serverlist || echo "No nvim server found"
   ```

2. **Discover user's setup** (optional but helpful):
   ```bash
   # Check for common plugins
   nvr --remote-expr "exists(':Telescope')"   # telescope.nvim
   nvr --remote-expr "exists(':NvimTreeToggle')"  # nvim-tree
   nvr --remote-expr "exists(':Lazy')"        # lazy.nvim

   # List loaded LSP clients
   nvr -c "lua print(vim.inspect(vim.lsp.get_clients()))"
   ```

3. **Get current state**:
   ```bash
   nvr --remote-expr "expand('%:p')"  # Current file
   nvr --remote-expr "line('.')"      # Current line
   ```

## Error Handling

| Error | Cause | Fix |
|-------|-------|-----|
| `E247: no registered server` | Socket not found | Verify socket path, ensure nvim is listening |
| `Connection refused` | nvim not running | User needs to start `nvim --listen /tmp/nvim` |
| `FileNotFoundError: /tmp/nvim` | Wrong socket path | Ask user for correct path |
| `E492: Not an editor command` | Invalid Ex command | Check command syntax |

### Fallback: No Socket

If no socket exists and user wants editor integration:

```bash
# Start nvim in background with socket
nvim --listen /tmp/nvim --headless &

# Or suggest user run in their terminal
echo "Run: nvim --listen /tmp/nvim"
```

## Common Patterns

### Open File at Search Result

```bash
# After grep finds something at file.py:42
nvr --remote +42 file.py
```

### Side-by-Side Comparison

```bash
nvr -c "tabnew" -O old_version.py new_version.py -c "windo diffthis"
```

### Send to Quickfix

```bash
# Populate quickfix with grep results
nvr -c "cexpr system('grep -rn TODO src/')" -c "copen"
```

### Run Terminal Command in nvim

```bash
nvr -c "split | terminal pytest tests/"
```

### Insert Text at Cursor

```bash
nvr -c "normal! iText inserted by Claude"
```

### Get Selected Text (visual mode)

```bash
nvr --remote-expr "getreg('\"')"  # After yank
```

## Environment Variables

```bash
export NVIM_LISTEN_ADDRESS=/tmp/nvim  # Default for nvr
```

## Reference Files

- [REFERENCE.md](./REFERENCE.md) - Full nvr/pynvim API reference
- [LSP.md](./LSP.md) - Complete LSP operations guide
- [scripts/nvim_helper.py](./scripts/nvim_helper.py) - Python helper for complex operations
