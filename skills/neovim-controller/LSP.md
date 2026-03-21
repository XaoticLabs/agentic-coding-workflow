# Neovim LSP Operations via RPC

Complete guide to executing LSP operations through Neovim's RPC interface.

## Prerequisites

User must have LSP configured (nvim-lspconfig, mason, or manual setup).

```bash
# Check if LSP client is attached to current buffer
nvr --remote-expr "luaeval('#vim.lsp.get_clients({bufnr=0})')"
# Returns 0 if no LSP, >0 if LSP attached

# List active LSP clients
nvr -c "lua print(vim.inspect(vim.tbl_map(function(c) return c.name end, vim.lsp.get_clients())))"
```

## Navigation

### Go to Definition

```bash
nvr -c "lua vim.lsp.buf.definition()"
```

With pynvim (to capture result):
```python
nvim.exec_lua('''
    vim.lsp.buf.definition()
''')
```

### Go to Declaration

```bash
nvr -c "lua vim.lsp.buf.declaration()"
```

### Go to Type Definition

```bash
nvr -c "lua vim.lsp.buf.type_definition()"
```

### Go to Implementation

```bash
nvr -c "lua vim.lsp.buf.implementation()"
```

### Find References

```bash
# Opens in quickfix
nvr -c "lua vim.lsp.buf.references()"
```

## Information

### Hover Documentation

```bash
nvr -c "lua vim.lsp.buf.hover()"
```

### Signature Help

```bash
nvr -c "lua vim.lsp.buf.signature_help()"
```

### Document Symbols

```bash
nvr -c "lua vim.lsp.buf.document_symbol()"
```

### Workspace Symbols

```bash
# Search for symbol across workspace
nvr -c "lua vim.lsp.buf.workspace_symbol('ClassName')"
```

## Refactoring

### Rename Symbol

```bash
# Interactive (prompts user)
nvr -c "lua vim.lsp.buf.rename()"

# Programmatic (specify new name)
nvr -c "lua vim.lsp.buf.rename('newName')"
```

### Code Actions

```bash
# Show available actions (user selects)
nvr -c "lua vim.lsp.buf.code_action()"

# Filter by kind
nvr -c "lua vim.lsp.buf.code_action({context = {only = {'quickfix'}}})"
nvr -c "lua vim.lsp.buf.code_action({context = {only = {'refactor'}}})"
nvr -c "lua vim.lsp.buf.code_action({context = {only = {'source.organizeImports'}}})"
```

### Format

```bash
# Format entire buffer
nvr -c "lua vim.lsp.buf.format()"

# Format with options
nvr -c "lua vim.lsp.buf.format({async = true})"

# Format range (visual selection)
nvr -c "lua vim.lsp.buf.format({range = {['start'] = {line('\"<'), 0}, ['end'] = {line('\">'), 0}}})"
```

## Diagnostics

### View Diagnostics

```bash
# Float at current position
nvr -c "lua vim.diagnostic.open_float()"

# Open all in location list
nvr -c "lua vim.diagnostic.setloclist()"

# Open all in quickfix
nvr -c "lua vim.diagnostic.setqflist()"
```

### Navigate Diagnostics

```bash
# Next diagnostic
nvr -c "lua vim.diagnostic.goto_next()"

# Previous diagnostic
nvr -c "lua vim.diagnostic.goto_prev()"

# Next error only
nvr -c "lua vim.diagnostic.goto_next({severity = vim.diagnostic.severity.ERROR})"

# Previous warning or error
nvr -c "lua vim.diagnostic.goto_prev({severity = {min = vim.diagnostic.severity.WARN}})"
```

### Query Diagnostics

```bash
# Count diagnostics in current buffer
nvr --remote-expr "luaeval('#vim.diagnostic.get(0)')"

# Get error count only
nvr --remote-expr "luaeval('#vim.diagnostic.get(0, {severity = vim.diagnostic.severity.ERROR})')"
```

With pynvim:
```python
diagnostics = nvim.exec_lua('''
    local diags = vim.diagnostic.get(0)
    return vim.tbl_map(function(d)
        return {
            line = d.lnum + 1,
            col = d.col,
            message = d.message,
            severity = d.severity
        }
    end, diags)
''')
for d in diagnostics:
    print(f"Line {d['line']}: {d['message']}")
```

### Diagnostic Severity Levels

```lua
vim.diagnostic.severity.ERROR  -- 1
vim.diagnostic.severity.WARN   -- 2
vim.diagnostic.severity.INFO   -- 3
vim.diagnostic.severity.HINT   -- 4
```

## Incoming/Outgoing Calls

```bash
# Incoming calls (who calls this)
nvr -c "lua vim.lsp.buf.incoming_calls()"

# Outgoing calls (what does this call)
nvr -c "lua vim.lsp.buf.outgoing_calls()"
```

## LSP Server Management

### Restart LSP

```bash
nvr -c "LspRestart"
```

### Stop LSP

```bash
nvr -c "LspStop"
```

### Start LSP

```bash
nvr -c "LspStart"
```

### LSP Info

```bash
nvr -c "LspInfo"
```

## Codelens

```bash
# Show codelens
nvr -c "lua vim.lsp.codelens.refresh()"

# Run codelens at cursor
nvr -c "lua vim.lsp.codelens.run()"
```

## Inlay Hints (Neovim 0.10+)

```bash
# Enable inlay hints
nvr -c "lua vim.lsp.inlay_hint.enable(true)"

# Disable inlay hints
nvr -c "lua vim.lsp.inlay_hint.enable(false)"

# Toggle
nvr -c "lua vim.lsp.inlay_hint.enable(not vim.lsp.inlay_hint.is_enabled())"
```

## Advanced: Get LSP Results Programmatically

For operations that return data (useful with pynvim):

```python
import pynvim

nvim = pynvim.attach('socket', path='/tmp/nvim')

# Get definition location without jumping
result = nvim.exec_lua('''
    local params = vim.lsp.util.make_position_params()
    local results = vim.lsp.buf_request_sync(0, 'textDocument/definition', params, 1000)
    if results then
        for client_id, result in pairs(results) do
            if result.result then
                return result.result
            end
        end
    end
    return nil
''')
print(result)  # Contains URI and range

# Get hover content
hover = nvim.exec_lua('''
    local params = vim.lsp.util.make_position_params()
    local results = vim.lsp.buf_request_sync(0, 'textDocument/hover', params, 1000)
    if results then
        for _, result in pairs(results) do
            if result.result and result.result.contents then
                local contents = result.result.contents
                if type(contents) == 'string' then
                    return contents
                elseif contents.value then
                    return contents.value
                end
            end
        end
    end
    return nil
''')
print(hover)

# Get all references
refs = nvim.exec_lua('''
    local params = vim.lsp.util.make_position_params()
    params.context = { includeDeclaration = true }
    local results = vim.lsp.buf_request_sync(0, 'textDocument/references', params, 3000)
    if results then
        for _, result in pairs(results) do
            if result.result then
                return vim.tbl_map(function(r)
                    return {
                        uri = r.uri,
                        line = r.range.start.line + 1,
                        col = r.range.start.character
                    }
                end, result.result)
            end
        end
    end
    return {}
''')
for ref in refs:
    print(f"{ref['uri']}:{ref['line']}:{ref['col']}")
```

## Common LSP Workflows

### Navigate to Definition and Back

```bash
# Go to definition
nvr -c "lua vim.lsp.buf.definition()"

# Jump back (Ctrl-O)
nvr --remote-send "<C-o>"
```

### Quick Fix All Diagnostics

```bash
# Apply first available fix to all diagnostics
nvr -c "lua vim.lsp.buf.code_action({context = {only = {'quickfix'}}, apply = true})"
```

### Organize Imports

```bash
nvr -c "lua vim.lsp.buf.code_action({context = {only = {'source.organizeImports'}}, apply = true})"
```

### Format on Location

```bash
# Jump to line, format, save
nvr -c "42" -c "lua vim.lsp.buf.format()" -c "write"
```

## Plugin-Specific LSP Features

### Telescope.nvim

```bash
# LSP references in telescope
nvr -c "Telescope lsp_references"

# LSP definitions
nvr -c "Telescope lsp_definitions"

# LSP document symbols
nvr -c "Telescope lsp_document_symbols"

# LSP workspace symbols
nvr -c "Telescope lsp_workspace_symbols"

# Diagnostics
nvr -c "Telescope diagnostics"
```

### Trouble.nvim

```bash
nvr -c "Trouble diagnostics"
nvr -c "Trouble lsp_references"
```

### saga (lspsaga.nvim)

```bash
nvr -c "Lspsaga hover_doc"
nvr -c "Lspsaga finder"
nvr -c "Lspsaga code_action"
nvr -c "Lspsaga rename"
```
