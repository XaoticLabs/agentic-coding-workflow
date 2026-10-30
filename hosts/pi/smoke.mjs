#!/usr/bin/env node
/** Load the real Pi extension and exercise its policy without a provider call. */
import assert from "node:assert/strict";
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { pathToFileURL, fileURLToPath } from "node:url";

if (!process.env.WORKFLOW_PI_MODULE || !process.env.WORKFLOW_PI_SMOKE_PROJECT) {
  throw new Error("Set WORKFLOW_PI_MODULE to Pi's dist/index.js and WORKFLOW_PI_SMOKE_PROJECT to an isolated project");
}
const { AgentSession, DefaultResourceLoader, SettingsManager } = await import(pathToFileURL(process.env.WORKFLOW_PI_MODULE).href);
const root = fileURLToPath(new URL("../../", import.meta.url));
const cwd = process.env.WORKFLOW_PI_SMOKE_PROJECT;
const loader = new DefaultResourceLoader({
  cwd, agentDir: resolve(cwd, ".pi-fixture"), noExtensions: true,
  additionalExtensionPaths: [resolve(root, "hosts/pi/index.ts")],
  additionalSkillPaths: [resolve(root, "hosts/pi/generated/skills")],
  noContextFiles: true, noPromptTemplates: true, noThemes: true,
  settingsManager: SettingsManager.inMemory({}),
});
await loader.reload();
const loaded = loader.getExtensions();
assert.deepEqual(loaded.errors, []);
assert.equal(loaded.extensions.length, 1);
const extension = loaded.extensions[0];
const persisted = [];
loaded.runtime.appendEntry = (customType, data) => persisted.push({ customType, data });
let activeTools = [];
loaded.runtime.getActiveTools = () => activeTools;
loaded.runtime.setActiveTools = (names) => { activeTools = names; };
const notices = [];
const notificationLog = process.env.WORKFLOW_PI_SMOKE_NOTIFICATIONS;
if (!notificationLog) throw new Error("Native smoke requires an isolated notification recorder");
const desktop = () => existsSync(notificationLog) ? readFileSync(notificationLog, "utf8").trim().split("\n").filter(Boolean).map(JSON.parse) : [];
let aborted = 0;
let idle = true, queued = false;
let sessionIdentifier = "pi-native-fixture";
const worker = process.env.WORKFLOW_HOST_WORKER === "1";
const mode = worker ? "json" : process.env.WORKFLOW_PI_SMOKE_MODE ?? "tui";
const ctx = {
  cwd, hasUI: false, mode, signal: undefined,
  sessionManager: { getSessionId: () => sessionIdentifier, getEntries: () => [] },
  ui: { notify: (...args) => notices.push(args) },
  abort() { aborted++; }, isIdle: () => idle, hasPendingMessages: () => queued,
};
const call = async (event, data) => {
  let result;
  for (const handler of extension.handlers.get(event) ?? []) {
    const next = await handler({ type: event, ...data }, ctx);
    if (next !== undefined) result = next;
  }
  return result;
};
// Exercise the installed SDK's actual final boundary with isolated runtime
// ports. Handler calls alone must never send completion notifications.
const nativeSession = Object.assign(Object.create(AgentSession.prototype), {
  sessionManager: ctx.sessionManager, _agentRunAbortRequested: false,
  _deferredSettledActions: [],
  _extensionRunner: { emit: (event) => call(event.type, event) },
  _emit() {}, _resolveIdleWaitIfIdle() {},
});
const settle = async (wasAborted = false) => {
  nativeSession._agentRunAbortRequested = wasAborted;
  await nativeSession._emitAgentSettled();
};
assert.equal(extension.commands.size, 0, "user commands await native mode selection");
await call("session_start", {});
const blocked = await call("tool_call", { toolName: "read", input: { path: ".env" } });
assert.equal(blocked.block, true, JSON.stringify(blocked));
const safe = await call("tool_call", { toolName: "read", input: { path: "fixture.txt" } });
assert.equal(safe, undefined, JSON.stringify(safe));
if (worker) {
  assert.equal(extension.commands.size, 0);
  assert.equal(extension.tools.size, 0);
  assert.equal(extension.handlers.has("agent_before_settle"), false);
  const write = await call("tool_call", { toolName: "write", input: { path: "fixture.txt", content: "mutation" } });
  assert.equal(write.block, true);
  const leaked = await call("tool_call", { toolName: "mcp__other__write", input: {} });
  assert.equal(leaked.block, true);
  assert.equal(desktop().length, 0, "workers never notify the desktop");
} else {
  const catalog = JSON.parse(readFileSync(resolve(root, "hosts/catalog.json"), "utf8"));
  for (const [name, entry] of Object.entries({ ...catalog.commands, ...catalog.skills })) {
    assert.equal(extension.commands.has(name), entry.user_invocable && mode === "tui", name);
    const native = loader.getSkills().skills.find((skill) => skill.name === name);
    assert.equal(Boolean(native), entry.user_invocable, `native skill discovery: ${name}`);
    if (native) assert.equal(native.disableModelInvocation, !entry.model_invocable, name);
  }
  const workflow = extension.tools.get("Workflow").definition;
  const userOnly = await workflow.execute("fixture", { name: "ship" }, undefined, undefined, ctx);
  assert.equal(userOnly.isError, true);
  const modelOnly = await call("input", { text: "/skill:pr-reviewer", source: "interactive" });
  assert.equal(modelOnly.action, "handled");
  const question = extension.tools.get("AskUserQuestion").definition;
  assert.equal((await question.execute("fixture", { questions: [{ question: "Approve?" }] }, undefined, undefined, ctx)).isError, true);
  loaded.runtime.sendUserMessage = (value) => { loaded.runtime.fixturePrompt = value; };
  if (mode === "tui") {
    await extension.commands.get("test").handler("--focus unit suite", ctx);
  } else {
    const result = await call("input", { text: "/test --focus unit suite", source: "interactive" });
    assert.equal(result.action, "transform");
    loaded.runtime.fixturePrompt = result.text;
    assert.equal(extension.commands.size, 0, "print mode retains outer prompt ownership");
    // Explicit user invocation grants access only for this user turn.
    const file = resolve(root, "hosts/pi/generated/skills/ship/SKILL.md");
    assert.equal((await call("tool_call", { toolName: "read", input: { path: file } })).block, true);
    const ship = await call("input", { text: "/ship --draft", source: "rpc" });
    assert.equal(ship.action, "transform");
    assert.match(ship.text, /--draft/);
    assert.equal(await call("tool_call", { toolName: "read", input: { path: file } }), undefined);
    await call("input", { text: "A new user request", source: "interactive" });
    assert.equal((await call("tool_call", { toolName: "read", input: { path: file } })).block, true);
    const implicit = await call("input", { text: "/ship", source: "extension" });
    assert.equal(implicit.action, "handled");
    // A fresh actual user request permits verification to start again.
    await call("input", { text: "Run the tests", source: "interactive" });
  }
  assert.match(loaded.runtime.fixturePrompt, /unit suite/);
  assert.doesNotMatch(loaded.runtime.fixturePrompt, /\$\{CLAUDE_PLUGIN_ROOT\}/);
  await settle();
  assert.equal(desktop().length, 0, "a settled event without verification is not completion");
  // Real registered Stop scripts must repair failures, cap retries, and reset
  // only after a new user input. Native event shapes exercise the adapter.
  for (let attempt = 0; attempt < 3; attempt++) {
    const result = await call("agent_before_settle", { outcome: "completed", entries: [] });
    assert.equal(result.continue, true, `correction ${attempt}: ${JSON.stringify(result)}`);
  }
  const exhausted = await call("agent_before_settle", { outcome: "completed", entries: [] });
  assert.equal(exhausted.continue, false);
  assert.match(JSON.stringify(exhausted), /three attempts/);
  await settle();
  assert.equal(desktop().length, 0, "verification blocks and intermediate Stops never notify");
  await call("input", { text: "retry after repairing", source: "interactive" });
  const fresh = await call("agent_before_settle", { outcome: "completed", entries: [] });
  assert.equal(fresh.continue, true);
  assert.equal(persisted.at(-1).data.status, "blocked");
  writeFileSync(resolve(cwd, ".claude/project-commands.json"), JSON.stringify({ lint: "printf x >> .claude/pi-check-count", test: "true" }));
  assert.equal(await call("agent_before_settle", { outcome: "completed", entries: [] }), undefined);
  assert.equal(persisted.at(-1).data.status, "passed");
  assert.equal(readFileSync(resolve(cwd, ".claude/pi-check-count"), "utf8"), "x");
  await call("agent_before_settle", { outcome: "completed", entries: [] });
  assert.equal(readFileSync(resolve(cwd, ".claude/pi-check-count"), "utf8"), "x", "identical source reuses verification");
  writeFileSync(resolve(cwd, "fixture.txt"), "changed source\n");
  await call("agent_before_settle", { outcome: "completed", entries: [] });
  assert.equal(readFileSync(resolve(cwd, ".claude/pi-check-count"), "utf8"), "xx", "changed source invalidates verification");

  await settle(true);
  idle = false; await settle();
  idle = true; queued = true; await settle();
  assert.equal(desktop().length, 0, "abort, active work, and queued follow-ups are silent");
  queued = false;
  await call("agent_settled", { aborted: false });
  assert.equal(desktop().length, 0, "an extension settled callback is still too early");
  await settle();
  assert.equal(desktop().length, 1);
  assert.match(desktop()[0][0], /Pi: ready for you/);
  await settle();
  assert.equal(desktop().length, 1, "duplicate settled events do not repeat completion");

  const goalInput = async (argumentsText) => {
    if (mode === "tui") await extension.commands.get("goal").handler(argumentsText, ctx);
    else await call("input", { text: `/goal ${argumentsText}`, source: "interactive" });
  };
  await goalInput("Finish only after all work is accepted");
  assert.equal((await call("agent_before_settle", { outcome: "completed", entries: [] })).continue, true);
  await settle();
  await goalInput("pause");
  await call("agent_before_settle", { outcome: "completed", entries: [] });
  await settle();
  const goalTool = extension.tools.get("workflow_goal").definition;
  await goalTool.execute("fixture", { action: "blocked", reason: "Still waiting" });
  await call("agent_before_settle", { outcome: "completed", entries: [] });
  await settle();
  assert.equal(desktop().length, 1, "unfinished, paused, and blocked goals are not done");
  await goalInput("resume");
  await goalTool.execute("fixture", { action: "complete" });
  await call("agent_before_settle", { outcome: "completed", entries: [] });
  await settle();
  assert.equal(desktop().length, 2, "a completed verified goal notifies once");

  ctx.hasUI = true;
  await call("ui_prompt_start", { title: "Choose an option", kind: "select" });
  await call("ui_prompt_start", { title: "Same paused question flow", kind: "input" });
  assert.equal(desktop().length, 3, "one alert per paused input episode");
  assert.match(desktop().at(-1)[0], /Pi: input needed/);
  await call("turn_start", {});
  await call("ui_prompt_start", { title: "A new permission decision", kind: "confirm" });
  assert.equal(desktop().length, 4, "new questions after resumed work can notify");
  ctx.hasUI = false;
  await call("before_agent_start", { systemPrompt: "A new run" });
  await call("after_provider_response", { status: 429 });
  await call("message_end", { message: { role: "assistant", content: [{ type: "text", text: "API failure" }], stopReason: "error", errorMessage: "rate limit" } });
  await settle();
  assert.equal(desktop().length, 4, "API errors are recorded without desktop alerts");

  // Native /new and /resume can change the session ID without reloading the
  // extension. Completion ownership and persisted goals follow that ID.
  await goalInput("An unfinished goal in the previous session");
  await goalInput("pause");
  const previousSessionIdentifier = sessionIdentifier;
  sessionIdentifier = "pi-native-next";
  await call("input", { text: "A separate completed request", source: "interactive" });
  await call("agent_before_settle", { outcome: "completed", entries: [] });
  await call("agent_settled", { aborted: false });
  const previousNativeSession = Object.assign(Object.create(AgentSession.prototype), {
    sessionManager: { getSessionId: () => previousSessionIdentifier },
    _agentRunAbortRequested: false, _deferredSettledActions: [],
    _extensionRunner: { emit() {} }, _emit() {}, _resolveIdleWaitIfIdle() {},
  });
  await previousNativeSession._emitAgentSettled();
  assert.equal(desktop().length, 4, "switching sessions removes the previous completion callback");
  await settle();
  assert.equal(desktop().length, 5, "a previous session's paused goal cannot suppress a new session");
  sessionIdentifier = "pi-native-resumed";
  ctx.sessionManager.getEntries = () => [{ type: "custom", customType: "agentic-coding-workflow:goal", data: {
    objective: "A paused goal in the resumed session", status: "paused", turns: 1, maxTurns: 40,
  } }];
  await call("input", { text: "Inspect this resumed session", source: "interactive" });
  await call("agent_before_settle", { outcome: "completed", entries: [] });
  await settle();
  assert.equal(desktop().length, 5, "the current session's persisted paused goal is restored");

  // Native session resume restores restrictions before any model tool call.
  ctx.sessionManager.getEntries = () => [{ type: "custom", customType: "agentic-coding-workflow:role", data: { role: "evaluator", maxTurns: 2 } }];
  await call("session_start", {});
  assert.equal(activeTools.includes("write"), false);
  assert.equal((await call("tool_call", { toolName: "write", input: { path: "fixture.txt", content: "forbidden" } })).block, true);
  assert.equal((await call("tool_call", { toolName: "mcp__unexpected__mutate", input: {} })).block, true);
  const restoredPrompt = await call("before_agent_start", { systemPrompt: "Native Pi context" });
  assert.match(restoredPrompt.systemPrompt, /independent evaluation agent/);
  for (let turn = 0; turn < 3; turn++) await call("turn_start", {});
  assert.equal(aborted, 1);
  assert.equal(persisted.at(-1).data.status, "blocked");
}
console.log(JSON.stringify({ host: "pi", native_loader: true, worker, mode, policy: "passed", commands: extension.commands.size, skills: loader.getSkills().skills.length }));
