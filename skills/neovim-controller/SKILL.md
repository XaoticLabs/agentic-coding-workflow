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
user-invocable: false
---

# Neovim RPC Controller

Control a Neovim instance started with `nvim --listen <socket>` via msgpack-RPC.

## Prerequisites

```bash
which nvr                          # neovim-remote CLI
python3 -c "import pynvim"        # pynvim library
```

If missing: `pip install neovim-remote pynvim`

## Socket Discovery

```bash
ls /tmp/nvim* 2>/dev/null
ls /run/user/$(id -u)/nvim* 2>/dev/null
echo $NVIM_LISTEN_ADDRESS
nvr --serverlist || echo "No nvim server found"
```

If socket path is unclear, ask the user. Default: `/tmp/nvim` or `/tmp/nvim.sock`.

## Essential Commands

| Command | Effect |
|---------|--------|
| `nvr --remote <file>` | Open file in current window |
| `nvr -O file1 file2` | Open in vertical splits |
| `nvr --remote +42 file.py` | Open file at line 42 |
| `nvr -c "write"` | Execute Ex command |
| `nvr -d file1 file2` | Diff two files |
| `nvr --remote-expr "expand('%:p')"` | Get current file path |
| `nvr --remote-expr "line('.')"` | Get current line number |
| `nvr --remote-tab +42 file.py` | Open in new tab at line |
| `nvr --remote-send "<C-o>"` | Send key sequence |
| `nvr --serverlist` | List available servers |

## LSP Operations

```bash
nvr -c "lua vim.lsp.buf.definition()"       # Go to definition
nvr -c "lua vim.lsp.buf.references()"       # Find references
nvr -c "lua vim.lsp.buf.hover()"            # Hover docs
nvr -c "lua vim.lsp.buf.rename('newName')"  # Rename symbol
nvr -c "lua vim.lsp.buf.code_action()"      # Code actions
nvr -c "lua vim.lsp.buf.format()"           # Format buffer
nvr -c "lua vim.diagnostic.open_float()"    # Show diagnostic
nvr -c "lua vim.diagnostic.goto_next()"     # Next diagnostic
```

Check if LSP is attached: `nvr --remote-expr "luaeval('#vim.lsp.get_clients({bufnr=0})')"`

## Helper Script

For multi-step operations:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/neovim-controller/scripts/nvim_helper.py \
    --socket /tmp/nvim --action open --file main.py --line 42
```

## Useful Expressions

For use with `nvr --remote-expr` or pynvim `nvim.eval()`:

| Expression | Returns |
|------------|---------|
| `expand('%:p')` | Full file path |
| `expand('%:t')` | Filename only |
| `line('.')` | Current line number |
| `col('.')` | Current column |
| `bufnr('%')` | Current buffer number |
| `mode()` | Current mode (n, i, v) |
| `exists(':Telescope')` | Check if command exists |
| `luaeval('#vim.diagnostic.get(0)')` | Diagnostic count |

## Error Handling

| Error | Cause | Fix |
|-------|-------|-----|
| `E247: no registered server` | Socket not found | Verify socket path |
| `Connection refused` | nvim not running | Start `nvim --listen /tmp/nvim` |
| `FileNotFoundError` | Wrong socket path | Ask user for correct path |
| `E492: Not an editor command` | Invalid Ex command | Check syntax |
