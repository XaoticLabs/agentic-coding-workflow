# Neovim RPC Reference

Complete API reference for nvr CLI and pynvim library.

## nvr (neovim-remote) CLI

### Connection Options

```bash
nvr --servername /tmp/nvim    # Explicit socket path
nvr --nostart                 # Don't start new nvim if not found
nvr --serverlist              # List available servers
```

### File Opening Flags

| Flag | Effect | Example |
|------|--------|---------|
| `--remote` | Open in current window | `nvr --remote file.py` |
| `--remote-tab` | Open in new tab | `nvr --remote-tab file.py` |
| `-o` | Open in horizontal split | `nvr -o file.py` |
| `-O` | Open in vertical split | `nvr -O file.py` |
| `-p` | Open in tab(s) | `nvr -p file1.py file2.py` |
| `-d` | Open in diff mode | `nvr -d file1.py file2.py` |
| `--remote-wait` | Wait for buffer close | `nvr --remote-wait file.py` |
| `--remote-silent` | Suppress errors | `nvr --remote-silent file.py` |

### Command Execution

| Flag | Effect | Example |
|------|--------|---------|
| `-c <cmd>` | Execute Ex command | `nvr -c "set number"` |
| `--remote-send <keys>` | Send key sequence | `nvr --remote-send "gg"` |
| `--remote-expr <expr>` | Evaluate expression | `nvr --remote-expr "line('.')"` |
| `-s` | Silent mode | `nvr -s -c "write"` |
| `-l` | Literal (don't expand) | `nvr -l <file>` |
| `+<cmd>` | Execute on file open | `nvr --remote +42 file.py` |
| `+/<pattern>` | Search on open | `nvr --remote +/TODO file.py` |

### Combining Flags

```bash
# Open file at line 42 in new tab
nvr --remote-tab +42 file.py

# Open two files in vertical splits, both in diff mode
nvr -O -d file1.py file2.py

# Execute command then open file
nvr -c "cd /project" --remote file.py

# Multiple commands
nvr -c "set wrap" -c "set linebreak" -c "set breakindent"
```

### Exit Codes

- `0`: Success
- `1`: Error (connection failed, invalid command)

## pynvim Library

### Connection

```python
import pynvim

# Socket connection
nvim = pynvim.attach('socket', path='/tmp/nvim')

# TCP connection
nvim = pynvim.attach('tcp', address='127.0.0.1', port=6666)

# Child process
nvim = pynvim.attach('child', argv=['nvim', '--embed'])
```

### Buffer Operations

```python
# Current buffer
buf = nvim.current.buffer

# Buffer properties
buf.name                  # Full path
buf.number               # Buffer number
buf.valid                # Is buffer valid
len(buf)                 # Line count
buf.options['filetype']  # Buffer option

# Read lines
buf[0]                   # First line (0-indexed)
buf[:]                   # All lines
buf[10:20]               # Lines 11-20

# Modify lines
buf[0] = 'new first line'
buf[:] = ['line1', 'line2']
buf.append('new line')
buf.append(['multiple', 'lines'])

# Buffer commands
nvim.command(f'buffer {buf.number}')
nvim.command(f'bdelete {buf.number}')
```

### Window Operations

```python
# Current window
win = nvim.current.window

# Window properties
win.buffer               # Window's buffer
win.cursor               # (row, col) 1-indexed row, 0-indexed col
win.height              # Window height
win.width               # Window width
win.number              # Window number
win.valid               # Is window valid

# Cursor manipulation
win.cursor = (42, 0)    # Go to line 42, col 0
row, col = win.cursor

# All windows
for win in nvim.windows:
    print(win.buffer.name)
```

### Tab Operations

```python
# Current tab
tab = nvim.current.tabpage

# Tab properties
tab.number              # Tab number
tab.windows             # Windows in tab
tab.valid               # Is tab valid

# All tabs
for tab in nvim.tabpages:
    print(f"Tab {tab.number}: {len(tab.windows)} windows")
```

### Command Execution

```python
# Ex command
nvim.command('write')
nvim.command('split file.py')
nvim.command('lua vim.lsp.buf.definition()')

# Evaluate expression (returns result)
line_num = nvim.eval("line('.')")
file_path = nvim.eval("expand('%:p')")
exists = nvim.eval("exists(':Telescope')")

# Call vim function
nvim.call('cursor', 42, 10)
nvim.call('append', 0, ['line1', 'line2'])
result = nvim.call('search', 'pattern')

# Call nvim API function
nvim.api.nvim_set_current_line('new line')
nvim.api.nvim_feedkeys('gg', 'n', True)

# Lua execution
nvim.exec_lua('vim.notify("Hello")')
result = nvim.exec_lua('return vim.api.nvim_get_current_line()')
```

### Async Operations

```python
# Subscribe to events
nvim.subscribe('my_event')

# Run async
nvim.async_call(lambda: nvim.command('echo "async"'))

# Request (blocking)
result = nvim.request('nvim_eval', '1+1')
```

## nvim_* RPC Functions

Core API functions available via RPC.

### Buffer API

```python
# Create/delete
nvim.api.nvim_create_buf(listed=True, scratch=False)
nvim.api.nvim_buf_delete(buf.handle, {'force': True})

# Content
nvim.api.nvim_buf_get_lines(buf.handle, 0, -1, False)  # All lines
nvim.api.nvim_buf_set_lines(buf.handle, 0, -1, False, ['new', 'content'])
nvim.api.nvim_buf_line_count(buf.handle)

# Properties
nvim.api.nvim_buf_get_name(buf.handle)
nvim.api.nvim_buf_set_name(buf.handle, '/new/path')
nvim.api.nvim_buf_get_option(buf.handle, 'filetype')
nvim.api.nvim_buf_set_option(buf.handle, 'modifiable', False)

# Marks
nvim.api.nvim_buf_get_mark(buf.handle, 'a')
nvim.api.nvim_buf_set_mark(buf.handle, 'a', 10, 0, {})
```

### Window API

```python
# Create
nvim.api.nvim_open_win(buf.handle, enter=True, config={
    'relative': 'editor',
    'width': 80,
    'height': 20,
    'row': 5,
    'col': 10,
    'style': 'minimal',
    'border': 'rounded'
})

# Properties
nvim.api.nvim_win_get_cursor(win.handle)  # [row, col]
nvim.api.nvim_win_set_cursor(win.handle, [42, 0])
nvim.api.nvim_win_get_height(win.handle)
nvim.api.nvim_win_set_height(win.handle, 30)
nvim.api.nvim_win_get_buf(win.handle)
nvim.api.nvim_win_set_buf(win.handle, buf.handle)
nvim.api.nvim_win_close(win.handle, force=True)
```

### Tab API

```python
nvim.api.nvim_list_tabpages()
nvim.api.nvim_get_current_tabpage()
nvim.api.nvim_set_current_tabpage(tab.handle)
nvim.api.nvim_tabpage_list_wins(tab.handle)
nvim.api.nvim_tabpage_get_win(tab.handle)
```

### Global API

```python
# Current state
nvim.api.nvim_get_current_buf()
nvim.api.nvim_get_current_win()
nvim.api.nvim_get_current_line()
nvim.api.nvim_set_current_line('new line')

# Lists
nvim.api.nvim_list_bufs()
nvim.api.nvim_list_wins()

# Commands
nvim.api.nvim_command('echo "hello"')
nvim.api.nvim_exec2('echo "hello"', {'output': True})

# Input
nvim.api.nvim_input('ihello<Esc>')
nvim.api.nvim_feedkeys('gg', 'n', True)

# Options
nvim.api.nvim_get_option('number')
nvim.api.nvim_set_option('number', True)

# Variables
nvim.api.nvim_get_var('my_var')          # g:my_var
nvim.api.nvim_set_var('my_var', 'value')
nvim.api.nvim_del_var('my_var')

# Registers
nvim.api.nvim_call_function('getreg', ['"'])
nvim.api.nvim_call_function('setreg', ['"', 'content'])
```

### Extmarks and Highlights

```python
# Create namespace
ns_id = nvim.api.nvim_create_namespace('my_namespace')

# Add extmark
nvim.api.nvim_buf_set_extmark(buf.handle, ns_id, line, col, {
    'end_line': line,
    'end_col': col + 5,
    'hl_group': 'ErrorMsg'
})

# Add virtual text
nvim.api.nvim_buf_set_extmark(buf.handle, ns_id, line, 0, {
    'virt_text': [['virtual text', 'Comment']],
    'virt_text_pos': 'eol'
})

# Clear namespace
nvim.api.nvim_buf_clear_namespace(buf.handle, ns_id, 0, -1)
```

## Useful Vim Expressions

For use with `nvr --remote-expr` or `nvim.eval()`:

```vim
" File info
expand('%:p')           " Full path
expand('%:t')           " Filename only
expand('%:e')           " Extension
expand('%:h')           " Directory

" Cursor position
line('.')               " Current line
col('.')                " Current column
getpos('.')             " [bufnum, line, col, off]

" Marks
getpos("'a")            " Position of mark a
line("'<")              " Start of visual selection
line("'>")              " End of visual selection

" Buffer info
bufnr('%')              " Current buffer number
bufname('%')            " Current buffer name
getbufinfo()            " All buffer info

" Window info
winnr()                 " Current window number
winnr('$')              " Total windows
win_getid()             " Window ID
getwininfo()            " All window info

" Search
searchpos('pattern')    " Find pattern position
search('pattern')       " Search forward

" Mode
mode()                  " Current mode (n, i, v, etc.)

" Checks
exists(':CommandName')  " Check if command exists (returns 2 if exists)
exists('g:variable')    " Check if variable exists
has('feature')          " Check if feature available
```

## Common nvr Recipes

```bash
# Get diagnostic count in current file
nvr --remote-expr "luaeval('#vim.diagnostic.get(0)')"

# Check if file is modified
nvr --remote-expr "getbufinfo('%')[0].changed"

# Get current word under cursor
nvr --remote-expr "expand('<cword>')"

# Get visual selection (after selecting)
nvr --remote-expr "getreg('*')"

# List all marks
nvr --remote-expr "execute('marks')"

# Get undo tree
nvr --remote-expr "undotree()"

# Check LSP client attached
nvr --remote-expr "luaeval('#vim.lsp.get_clients({bufnr=0})')"
```
