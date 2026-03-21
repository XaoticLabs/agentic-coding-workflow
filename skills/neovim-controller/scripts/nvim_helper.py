#!/usr/bin/env python3
"""
Neovim RPC Helper for Claude Code

Usage:
    python nvim_helper.py --socket /tmp/nvim --action <action> [options]

Actions:
    open        Open file (--file, --line, --col, --split)
    diff        Diff files (--file, --file2)
    state       Get current state (buffer, cursor, etc.)
    exec        Execute command (--cmd)
    eval        Evaluate expression (--expr)
    lsp         Run LSP operation (--lsp-action)
    buffers     List all buffers
    diagnostics Get LSP diagnostics
"""

import argparse
import json
import sys
from pathlib import Path

try:
    import pynvim
except ImportError:
    print("Error: pynvim not installed. Run: pip install pynvim", file=sys.stderr)
    sys.exit(1)


def connect(socket_path: str) -> pynvim.Nvim:
    """Connect to Neovim socket."""
    try:
        return pynvim.attach('socket', path=socket_path)
    except Exception as e:
        print(f"Error: Cannot connect to {socket_path}: {e}", file=sys.stderr)
        sys.exit(1)


def action_open(nvim: pynvim.Nvim, args: argparse.Namespace) -> None:
    """Open a file with optional position and split."""
    if not args.file:
        print("Error: --file required", file=sys.stderr)
        sys.exit(1)

    file_path = str(Path(args.file).resolve())

    if args.split == 'vertical':
        nvim.command(f'vsplit {file_path}')
    elif args.split == 'horizontal':
        nvim.command(f'split {file_path}')
    elif args.split == 'tab':
        nvim.command(f'tabedit {file_path}')
    else:
        nvim.command(f'edit {file_path}')

    if args.line:
        col = args.col or 0
        nvim.call('cursor', args.line, col)

    print(json.dumps({
        'status': 'ok',
        'file': file_path,
        'line': args.line,
        'col': args.col
    }))


def action_diff(nvim: pynvim.Nvim, args: argparse.Namespace) -> None:
    """Open two files in diff mode."""
    if not args.file or not args.file2:
        print("Error: --file and --file2 required", file=sys.stderr)
        sys.exit(1)

    file1 = str(Path(args.file).resolve())
    file2 = str(Path(args.file2).resolve())

    nvim.command('tabnew')
    nvim.command(f'edit {file1}')
    nvim.command('diffthis')
    nvim.command(f'vsplit {file2}')
    nvim.command('diffthis')

    print(json.dumps({
        'status': 'ok',
        'diff': [file1, file2]
    }))


def action_state(nvim: pynvim.Nvim, args: argparse.Namespace) -> None:
    """Get current Neovim state."""
    buf = nvim.current.buffer
    win = nvim.current.window

    state = {
        'buffer': {
            'number': buf.number,
            'name': buf.name,
            'lines': len(buf),
            'modified': nvim.eval('&modified'),
            'filetype': nvim.eval('&filetype'),
        },
        'cursor': {
            'line': win.cursor[0],
            'col': win.cursor[1],
        },
        'window': {
            'number': win.number,
            'height': win.height,
            'width': win.width,
        },
        'mode': nvim.eval('mode()'),
        'cwd': nvim.eval('getcwd()'),
    }

    print(json.dumps(state, indent=2))


def action_exec(nvim: pynvim.Nvim, args: argparse.Namespace) -> None:
    """Execute Ex command."""
    if not args.cmd:
        print("Error: --cmd required", file=sys.stderr)
        sys.exit(1)

    try:
        result = nvim.command_output(args.cmd)
        print(json.dumps({'status': 'ok', 'output': result}))
    except pynvim.NvimError as e:
        print(json.dumps({'status': 'error', 'message': str(e)}))
        sys.exit(1)


def action_eval(nvim: pynvim.Nvim, args: argparse.Namespace) -> None:
    """Evaluate expression."""
    if not args.expr:
        print("Error: --expr required", file=sys.stderr)
        sys.exit(1)

    try:
        result = nvim.eval(args.expr)
        print(json.dumps({'status': 'ok', 'result': result}, default=str))
    except pynvim.NvimError as e:
        print(json.dumps({'status': 'error', 'message': str(e)}))
        sys.exit(1)


def action_lsp(nvim: pynvim.Nvim, args: argparse.Namespace) -> None:
    """Execute LSP operation."""
    lsp_actions = {
        'definition': 'vim.lsp.buf.definition()',
        'references': 'vim.lsp.buf.references()',
        'hover': 'vim.lsp.buf.hover()',
        'rename': f"vim.lsp.buf.rename('{args.new_name}')" if args.new_name else 'vim.lsp.buf.rename()',
        'format': 'vim.lsp.buf.format()',
        'code_action': 'vim.lsp.buf.code_action()',
        'declaration': 'vim.lsp.buf.declaration()',
        'type_definition': 'vim.lsp.buf.type_definition()',
        'implementation': 'vim.lsp.buf.implementation()',
    }

    if args.lsp_action not in lsp_actions:
        print(f"Error: Unknown LSP action. Available: {list(lsp_actions.keys())}", file=sys.stderr)
        sys.exit(1)

    lua_cmd = lsp_actions[args.lsp_action]
    nvim.command(f'lua {lua_cmd}')
    print(json.dumps({'status': 'ok', 'action': args.lsp_action}))


def action_buffers(nvim: pynvim.Nvim, args: argparse.Namespace) -> None:
    """List all buffers."""
    buffers = []
    for buf in nvim.buffers:
        if buf.valid:
            buffers.append({
                'number': buf.number,
                'name': buf.name or '[No Name]',
                'loaded': nvim.call('bufloaded', buf.number),
                'modified': nvim.call('getbufvar', buf.number, '&modified'),
                'lines': len(buf),
            })

    print(json.dumps({'buffers': buffers}, indent=2))


def action_diagnostics(nvim: pynvim.Nvim, args: argparse.Namespace) -> None:
    """Get LSP diagnostics for current buffer."""
    diagnostics = nvim.exec_lua('''
        local diags = vim.diagnostic.get(0)
        return vim.tbl_map(function(d)
            return {
                line = d.lnum + 1,
                col = d.col,
                end_line = d.end_lnum and d.end_lnum + 1 or nil,
                end_col = d.end_col,
                message = d.message,
                severity = d.severity,
                source = d.source,
                code = d.code,
            }
        end, diags)
    ''')

    severity_names = {1: 'ERROR', 2: 'WARN', 3: 'INFO', 4: 'HINT'}
    for d in diagnostics:
        d['severity_name'] = severity_names.get(d['severity'], 'UNKNOWN')

    print(json.dumps({
        'buffer': nvim.current.buffer.name,
        'count': len(diagnostics),
        'diagnostics': diagnostics
    }, indent=2))


def main():
    parser = argparse.ArgumentParser(description='Neovim RPC Helper')
    parser.add_argument('--socket', '-s', default='/tmp/nvim',
                        help='Neovim socket path (default: /tmp/nvim)')
    parser.add_argument('--action', '-a', required=True,
                        choices=['open', 'diff', 'state', 'exec', 'eval', 'lsp', 'buffers', 'diagnostics'],
                        help='Action to perform')

    # Open action options
    parser.add_argument('--file', '-f', help='File path')
    parser.add_argument('--file2', help='Second file (for diff)')
    parser.add_argument('--line', '-l', type=int, help='Line number')
    parser.add_argument('--col', '-c', type=int, help='Column number')
    parser.add_argument('--split', choices=['vertical', 'horizontal', 'tab'],
                        help='Split type')

    # Exec/eval options
    parser.add_argument('--cmd', help='Ex command to execute')
    parser.add_argument('--expr', help='Expression to evaluate')

    # LSP options
    parser.add_argument('--lsp-action', help='LSP action to perform')
    parser.add_argument('--new-name', help='New name for LSP rename')

    args = parser.parse_args()

    nvim = connect(args.socket)

    actions = {
        'open': action_open,
        'diff': action_diff,
        'state': action_state,
        'exec': action_exec,
        'eval': action_eval,
        'lsp': action_lsp,
        'buffers': action_buffers,
        'diagnostics': action_diagnostics,
    }

    actions[args.action](nvim, args)


if __name__ == '__main__':
    main()
