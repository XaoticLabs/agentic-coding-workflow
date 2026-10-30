import assert from "node:assert/strict";
import { test } from "node:test";
import { mkdtempSync, symlinkSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { hookPayload, roleTools, protectedRead, sourcePath, finalMessage, run } from "./core.ts";
import { observeSettlement } from "./settlement.ts";

test("Pi file inputs become the actual blocker schema", () => {
  const payload = hookPayload("read", { path: ".env", offset: 2 }, "/tmp/project", "native-session");
  assert.equal(payload.tool_name, "Read");
  assert.equal(payload.tool_input.file_path, "/tmp/project/.env");
  assert.equal(payload.session_id, "native-session");
  assert.equal(hookPayload("bash", { command: "git status" }, "/tmp/project", "s").tool_input.command, "git status");
});

test("role policies retain shell-free evaluator and shell-capable runtime verifier", () => {
  assert.deepEqual(roleTools("evaluator"), ["read", "grep", "find", "ls"]);
  assert.deepEqual(roleTools("runtime-verifier"), ["read", "grep", "find", "ls", "bash"]);
  assert.deepEqual(roleTools("custom", { tools: ["Read", "Bash", "Write"], disallowed_tools: ["Bash"] }), ["read", "write"]);
});

test("evaluator secret denies follow symlinks", () => {
  const scratch = mkdtempSync(join(tmpdir(), "workflow-pi-policy-"));
  writeFileSync(join(scratch, ".env.production"), "fixture");
  symlinkSync(join(scratch, ".env.production"), join(scratch, "public.txt"));
  assert.equal(protectedRead("public.txt", scratch), true);
  assert.equal(protectedRead(".aws/credentials", scratch), true);
  assert.equal(protectedRead("src/main.py", scratch), false);
});

test("trusted instruction rendering never reaches outside the plugin root", () => {
  assert.equal(sourcePath("${CLAUDE_PLUGIN_ROOT}/commands/plan.md", "/tmp/plugin", "/tmp/project"), "commands/plan.md");
  assert.equal(sourcePath("../secrets.md", "/tmp/plugin", "/tmp/project"), undefined);
});

test("child event parsing rejects model failures despite process exit success", () => {
  const message = (stopReason, text = "candidate") => JSON.stringify({ type: "message_end", message: {
    role: "assistant", content: [{ type: "text", text }], model: "fixture", stopReason,
  } }) + "\n" + JSON.stringify({ type: "agent_settled", aborted: false });
  assert.equal(finalMessage(message("stop")).text, "candidate");
  assert.equal(finalMessage(message("stop")).failed, false);
  assert.equal(finalMessage(message("error")).failed, true);
  assert.equal(finalMessage(message("length")).failed, true);
  assert.equal(finalMessage(message("toolUse")).failed, true);
  assert.equal(finalMessage(message("error") + "\n" + message("stop")).failed, false);
  assert.equal(finalMessage("").failed, true);
  assert.throws(() => finalMessage("not JSON"));
});

test("subprocess transport uses literal argv and rejects timeout and oversize output", async () => {
  const result = await run("printf", ["%s", "$(echo secret); literal"], { cwd: tmpdir() });
  assert.equal(result.stdout, "$(echo secret); literal");
  const unicode = await run("bash", ["-c", "printf '\\360\\237'; sleep 0.01; printf '\\220\\210'"], { cwd: tmpdir() });
  assert.equal(unicode.stdout, "🐈");
  await assert.rejects(run("sleep", ["5"], { cwd: tmpdir(), timeout: 30 }), /timed out/);
  await assert.rejects(run("printf", ["%s", "x".repeat(10000)], { cwd: tmpdir(), maxBytes: 10 }), /output limit/);
});

test("completion observes only the outermost native deferred-settlement drain", async () => {
  class NativeSession {
    sessionManager = { getSessionId: () => "native-fixture" };
    calls = 0;
    async _emitAgentSettled() {
      this.calls++;
      if (this.calls === 1) {
        // Native settlement splices its actions before executing either one.
        // The first nested settlement therefore sees an empty native queue.
        const deferred = [() => this._emitAgentSettled(), () => this._emitAgentSettled()];
        for (const action of deferred) await action();
      }
      return "native-result";
    }
  }
  const observer = observeSettlement(NativeSession);
  const wrapped = NativeSession.prototype._emitAgentSettled;
  assert.ok(observer);
  assert.ok(observeSettlement(NativeSession));
  assert.equal(NativeSession.prototype._emitAgentSettled, wrapped, "reload does not wrap twice");
  const owner = Symbol("owner"), replacement = Symbol("replacement");
  const completions = [];
  observer.register("native-fixture", owner, (session) => { completions.push(session.calls); });
  const session = new NativeSession();
  assert.equal(await session._emitAgentSettled(), "native-result");
  assert.deepEqual(completions, [3], "no notice between either nested continuation");
  observer.register("native-fixture", replacement, () => { completions.push("reloaded"); });
  observer.unregister("native-fixture", owner);
  await session._emitAgentSettled();
  assert.deepEqual(completions, [3, "reloaded"], "old shutdown cannot unregister a replacement");
  observer.unregister("native-fixture", replacement);
  await session._emitAgentSettled();
  assert.equal(completions.length, 2);
  assert.equal(observeSettlement(class Unsupported {}), undefined);
  class FailedSession {
    sessionManager = { getSessionId: () => "failed-fixture" };
    async _emitAgentSettled() { throw new Error("native failure"); }
  }
  const failed = observeSettlement(FailedSession);
  failed.register("failed-fixture", owner, () => assert.fail("failure is not completion"));
  await assert.rejects(new FailedSession()._emitAgentSettled(), /native failure/);
});
