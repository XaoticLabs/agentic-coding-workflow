/** Host-independent policy helpers. No Pi imports: test with Node's TS loader. */
import { spawn } from "node:child_process";
import { realpathSync } from "node:fs";
import { resolve, relative, isAbsolute, sep } from "node:path";
import { StringDecoder } from "node:string_decoder";

export interface Entry {
  source: string;
  body: string;
  description: string;
  allowed_tools: string[];
  user_invocable: boolean;
  model_invocable: boolean;
  max_turns?: number | null;
  effort?: string | null;
  tools?: string[];
  disallowed_tools?: string[];
}

export interface Catalog {
  schema_version: number;
  commands: Record<string, Entry>;
  skills: Record<string, Entry>;
  agents: Record<string, Entry>;
}

export interface HookResult {
  action: "allow" | "repair" | "halt";
  reason: string;
  context: string[];
}

export const READ_TOOLS = ["read", "grep", "find", "ls"];
export const WRITE_TOOLS = [...READ_TOOLS, "bash", "write", "edit"];
const TOOL_NAMES: Record<string, string> = {
  bash: "Bash", read: "Read", write: "Write", edit: "Edit",
  grep: "Grep", find: "Glob", ls: "Glob",
};

export function roleTools(role: string, entry?: Entry): string[] {
  const mapping: Record<string, string[]> = {
    Read: ["read"], Glob: ["find", "ls"], Grep: ["grep"], Bash: ["bash"],
    Write: ["write"], Edit: ["edit"],
  };
  const configured = entry?.tools?.length
    ? [...new Set(entry.tools.flatMap((tool) => mapping[tool] ?? []))]
    : [...WRITE_TOOLS];
  const denied = new Set((entry?.disallowed_tools ?? []).flatMap((tool) => mapping[tool] ?? []));
  const tools = configured.filter((tool) => !denied.has(tool));
  if (role === "evaluator") return tools.filter((tool) => READ_TOOLS.includes(tool));
  if (role === "runtime-verifier") return tools.filter((tool) => [...READ_TOOLS, "bash"].includes(tool));
  return tools;
}

export function expandPath(value: string, root: string, project: string): string {
  return value.replaceAll("${CLAUDE_PLUGIN_ROOT}", root).replaceAll("${CLAUDE_PROJECT_DIR}", project);
}

export function sourcePath(value: unknown, root: string, project: string): string | undefined {
  if (typeof value !== "string") return undefined;
  const path = resolve(project, expandPath(value, root, project));
  let canonical = path;
  try { canonical = realpathSync(path); } catch { /* A future write need not exist. */ }
  const local = relative(root, canonical);
  if (local === ".." || local.startsWith(`..${sep}`) || isAbsolute(local)) return undefined;
  return local.split(sep).join("/");
}

export function protectedRead(path: unknown, project: string): boolean {
  if (typeof path !== "string") return false;
  const candidates = [resolve(project, path)];
  try { candidates.push(realpathSync(candidates[0])); } catch { /* Checked again by the tool. */ }
  return candidates.some((value) => value.split(sep).some((part) =>
    [".env", ".aws", ".ssh", "secrets"].includes(part) || part.startsWith(".env."),
  ));
}

export function hookPayload(toolName: string, input: Record<string, unknown>, cwd: string, session: string) {
  return {
    cwd, session_id: session,
    tool_name: TOOL_NAMES[toolName] ?? toolName,
    tool_input: { ...input, ...(typeof input.path === "string" ? { file_path: resolve(cwd, input.path) } : {}) },
  };
}

/** Subprocesses always use argv, bounded capture, cancellation and owned groups. */
export async function run(
  command: string, args: string[], options: {
    cwd: string; input?: string; timeout?: number; signal?: AbortSignal;
    env?: NodeJS.ProcessEnv; maxBytes?: number;
  },
): Promise<{ stdout: string; stderr: string; code: number }> {
  if (options.signal?.aborted) throw new Error("Operation cancelled");
  return await new Promise((done, fail) => {
    const child = spawn(command, args, {
      cwd: options.cwd, env: options.env ?? process.env,
      stdio: ["pipe", "pipe", "pipe"], detached: process.platform !== "win32",
    });
    let stdout = "", stderr = "", failure: Error | undefined, killTimer: ReturnType<typeof setTimeout>;
    const outputDecoder = new StringDecoder("utf8"), errorDecoder = new StringDecoder("utf8");
    let capturedBytes = 0;
    const stop = (error: Error) => {
      if (failure) return;
      failure = error;
      const kill = (signal: NodeJS.Signals) => {
        try {
          if (process.platform !== "win32" && child.pid) process.kill(-child.pid, signal);
          else child.kill(signal);
        } catch { /* Process already exited. */ }
      };
      kill("SIGTERM");
      killTimer = setTimeout(() => kill("SIGKILL"), 1000);
      killTimer.unref();
    };
    const abort = () => stop(new Error("Operation cancelled"));
    const timer = setTimeout(() => stop(new Error(`${command} timed out`)), options.timeout ?? 30_000);
    timer.unref();
    options.signal?.addEventListener("abort", abort, { once: true });
    const capture = (value: Buffer, error: boolean) => {
      if (failure) return;
      if (error) stderr += errorDecoder.write(value); else stdout += outputDecoder.write(value);
      capturedBytes += value.length;
      if (capturedBytes > (options.maxBytes ?? 4 * 1024 * 1024)) {
        stop(new Error(`${command} exceeded its output limit`));
      }
    };
    child.stdout.on("data", (chunk) => capture(chunk, false));
    child.stderr.on("data", (chunk) => capture(chunk, true));
    child.on("error", (error) => { failure = error; });
    child.on("close", (code) => {
      clearTimeout(timer); clearTimeout(killTimer);
      stdout += outputDecoder.end(); stderr += errorDecoder.end();
      options.signal?.removeEventListener("abort", abort);
      if (failure) fail(failure); else done({ stdout, stderr, code: code ?? 1 });
    });
    child.stdin.on("error", () => {}); // Early child exit is reported by close.
    child.stdin.end(options.input ?? "");
  });
}

export async function bridge(root: string, args: string[], cwd: string, input?: unknown, signal?: AbortSignal): Promise<any> {
  const result = await run(process.env.WORKFLOW_PYTHON ?? "python3", [resolve(root, "scripts/host-bridge.py"), ...args], {
    cwd, input: input === undefined ? undefined : typeof input === "string" ? input : JSON.stringify(input),
    timeout: args[0] === "event" ? 660_000 : 35_000, signal,
    env: { ...process.env, WORKFLOW_HOST: "pi", CLAUDE_PLUGIN_ROOT: root, CLAUDE_PROJECT_DIR: cwd },
  });
  if (result.code !== 0) throw new Error(`Workflow bridge exited ${result.code}: ${result.stderr || result.stdout}`);
  let value: any;
  try { value = JSON.parse(result.stdout); } catch { throw new Error("Workflow bridge returned invalid JSON"); }
  if (!value || typeof value !== "object") throw new Error("Workflow bridge returned no result");
  return value;
}

export function finalMessage(stdout: string): { text: string; models: string[]; turns: number; failed: boolean } {
  let text = "", failed = false, settled = false, turns = 0, stopReason = "";
  const models = new Set<string>();
  for (const line of stdout.split("\n")) {
    if (!line.trim()) continue;
    const event = JSON.parse(line);
    if (event.type === "message_end" && event.message?.role === "assistant") {
      turns++;
      const message = event.message;
      text = (message.content ?? []).filter((part: any) => part.type === "text").map((part: any) => part.text).join("\n");
      if (typeof message.model === "string") models.add(typeof message.provider === "string" ? `${message.provider}/${message.model}` : message.model);
      stopReason = message.stopReason;
    }
    if (event.type === "agent_settled") { settled = true; if (event.aborted) failed = true; }
    if (event.type === "entry_appended" && event.entry?.customType === "agentic-coding-workflow:verification" && event.entry.data?.status === "blocked") failed = true;
  }
  return { text, models: [...models].sort(), turns, failed: failed || !settled || stopReason !== "stop" || !text.trim() };
}
