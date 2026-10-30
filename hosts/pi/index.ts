/** Official Pi adapter. Source workflows and hook policy remain in the Claude plugin. */
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { randomUUID } from "node:crypto";
import { AgentSession, type ExtensionAPI, type ExtensionContext } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";
import {
  bridge, expandPath, finalMessage, hookPayload, protectedRead, roleTools, run, sourcePath,
  type Catalog, type HookResult,
} from "./core.ts";
import { observeSettlement } from "./settlement.ts";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
const STATE = "agentic-coding-workflow:goal";
const textResult = (text: string, details: object = {}, isError = false) => ({
  content: [{ type: "text" as const, text }], details, ...(isError ? { isError } : {}),
});
type Goal = { objective: string; status: "active" | "paused" | "complete" | "blocked"; turns: number; maxTurns: number; completionRequested?: boolean; reason?: string };

export default function workflowExtension(pi: ExtensionAPI) {
  const catalog = JSON.parse(readFileSync(resolve(ROOT, "hosts/catalog.json"), "utf8")) as Catalog;
  if (catalog.schema_version !== 1) throw new Error("Unsupported workflow catalog. Run maak sync-hosts.");
  const worker = process.env.WORKFLOW_HOST_WORKER === "1";
  let role = process.env.WORKFLOW_HOST_ROLE ?? "";
  let roleEntry = role ? catalog.agents[role] : undefined;
  if (role && !roleEntry) throw new Error(`Unknown workflow role: ${role}`);
  if (worker && !roleEntry) throw new Error("A workflow worker requires an explicit canonical role");
  let allowed = role && (worker || roleEntry?.tools?.length)
    ? new Set(roleTools(role, roleEntry)) : undefined;
  let maxTurns = Number(process.env.WORKFLOW_HOST_MAX_TURNS ?? roleEntry?.max_turns ?? 40);
  if (!Number.isSafeInteger(maxTurns) || maxTurns < 1) throw new Error("Worker max turns must be a positive integer");
  let turns = 0, correction = false, blockedReason = "", planMode = false;
  let verificationPassed = false, completionNotified = false, inputNotified = false;
  let roleUnavailable = false;
  let previousTools: string[] = [], goal: Goal | undefined, lastAssistant = "";
  let userCommandsRegistered = false;
  const authorized = new Set<string>();
  const session = (ctx: ExtensionContext) => ctx.sessionManager.getSessionId();
  const reset = () => { correction = false; verificationPassed = false; completionNotified = false; inputNotified = false; if (!roleUnavailable) blockedReason = ""; turns = 0; authorized.clear(); };
  const hook = async (event: string, data: object, ctx: ExtensionContext): Promise<HookResult> => {
    const result = await bridge(ROOT, ["event", "--event", event], ctx.cwd, {
      cwd: ctx.cwd, session_id: session(ctx), ...data,
    }, ctx.signal);
    if (!["allow", "repair", "halt"].includes(result.action) || !Array.isArray(result.context)) {
      throw new Error("Workflow hook bridge returned an invalid decision");
    }
    return result;
  };
  const observe = async (event: string, data: object, ctx: ExtensionContext) => {
    try {
      const result = await hook(event, data, ctx);
      if (result.context.length) pi.sendMessage({ customType: "workflow-observation", content: result.context.join("\n"), display: false });
    } catch { /* Observations and notifications fail open, as on Claude. */ }
  };
  const saveGoal = () => { pi.appendEntry(STATE, goal ?? null); };
  const render = (kind: string, name: string, args: string, ctx: ExtensionContext) => bridge(ROOT, [
    "render", "--host", "pi", "--kind", kind, "--name", name,
    `--arguments=${args}`, "--project", ctx.cwd,
  ], ctx.cwd, undefined, ctx.signal);
  const entryForPath = (source: string) => {
    for (const [kind, entries] of [["command", catalog.commands], ["skill", catalog.skills]] as const) {
      for (const [name, entry] of Object.entries(entries)) {
        if (source === entry.source || ["skills", "model-skills"].some((directory) => source === `hosts/pi/generated/${directory}/${name}/SKILL.md`)) return { kind, name, entry };
      }
    }
  };

  // A deny hook complements the native active set: codemode and late tools
  // cannot enlarge a restricted role's capabilities.
  pi.on("tool_call", async (event, ctx) => {
    const input = event.input as Record<string, unknown>;
    for (const key of ["path", "file_path"]) {
      if (typeof input[key] === "string") input[key] = expandPath(input[key] as string, ROOT, ctx.cwd);
    }
    if (blockedReason) return { block: true, terminate: true, reason: blockedReason };
    if (allowed && !allowed.has(event.toolName)) return { block: true, reason: `Role ${role} cannot use ${event.toolName}` };
    if (role === "evaluator" && protectedRead(input.path ?? input.file_path, ctx.cwd)) {
      return { block: true, reason: "Evaluator access to secrets is denied" };
    }
    if (planMode && !["read", "grep", "find", "ls", "AskUserQuestion", "ExitPlanMode", "Workflow"].includes(event.toolName)) {
      return { block: true, reason: "Plan mode permits inspection only. Obtain plan approval through ExitPlanMode." };
    }
    const source = sourcePath(input.path ?? input.file_path, ROOT, ctx.cwd);
    const workflow = source ? entryForPath(source) : undefined;
    if (workflow && !workflow.entry.model_invocable && !authorized.has(workflow.name)) {
      return { block: true, reason: `${workflow.name} requires explicit user invocation` };
    }
    try {
      const result = await hook("PreToolUse", hookPayload(event.toolName, input, ctx.cwd, session(ctx)), ctx);
      if (result.action !== "allow") return { block: true, reason: result.reason || "Workflow policy blocked this tool" };
    } catch (error) {
      return { block: true, reason: `Workflow policy is unavailable: ${String(error)}` };
    }
  });

  pi.on("tool_result", async (event, ctx) => {
    if (!worker && !event.isError && ["write", "edit"].includes(event.toolName)) {
      await observe("PostToolUse", hookPayload(event.toolName, event.input, ctx.cwd, session(ctx)), ctx);
    }
    if (event.isError || event.toolName !== "read") return;
    const source = sourcePath(event.input.path, ROOT, ctx.cwd);
    if (!source?.endsWith(".md")) return;
    try {
      const definition = source.startsWith("hosts/pi/generated/") && source.endsWith("/SKILL.md")
        ? entryForPath(source) : undefined;
      if (definition) {
        const result = await render(definition.kind, definition.name, "", ctx);
        if (typeof result.prompt !== "string") throw new Error("Workflow renderer returned no prompt");
        return { content: [{ type: "text", text: result.prompt }] };
      }
      const content = [];
      for (const block of event.content) {
        if (block.type !== "text") { content.push(block); continue; }
        const result = await bridge(ROOT, ["render-text", "--host", "pi", "--source", source, "--project", ctx.cwd], ctx.cwd, block.text, ctx.signal);
        if (typeof result.text !== "string") throw new Error("Workflow renderer returned no text");
        content.push({ ...block, text: result.text });
      }
      return { content };
    } catch (error) {
      return { content: [{ type: "text", text: `Workflow instructions could not be rendered: ${String(error)}` }], isError: true };
    }
  });

  pi.on("session_start", (_event, ctx) => {
    if (!process.env.WORKFLOW_HOST_ROLE) {
      for (const entry of ctx.sessionManager.getEntries()) {
        if (entry.type !== "custom" || entry.customType !== "agentic-coding-workflow:role") continue;
        const stored = entry.data as { role?: string; maxTurns?: number };
        if (!stored?.role || !catalog.agents[stored.role] || (stored.maxTurns !== undefined && (!Number.isSafeInteger(stored.maxTurns) || stored.maxTurns < 1))) {
          roleUnavailable = true;
          allowed = new Set(); blockedReason = "The resumed workflow role is unavailable";
          pi.appendEntry("agentic-coding-workflow:verification", { status: "blocked", reason: blockedReason });
          pi.setActiveTools([]); ctx.ui.notify(blockedReason, "error"); return;
        }
        role = stored.role; roleEntry = catalog.agents[role];
        maxTurns = stored.maxTurns ?? roleEntry.max_turns ?? 40;
        allowed = worker || roleEntry.tools?.length ? new Set(roleTools(role, roleEntry)) : undefined;
      }
    }
    if (role) pi.appendEntry("agentic-coding-workflow:role", { role, maxTurns });
    if (allowed) pi.setActiveTools([...allowed]);
    process.env.CLAUDE_PLUGIN_ROOT = ROOT;
    process.env.CLAUDE_PROJECT_DIR = ctx.cwd;
  });
  pi.on("turn_start", (_event, ctx) => {
    if (worker || role) {
      turns++;
      if (turns > maxTurns) {
        blockedReason = `Workflow ${role || "worker"} exhausted ${maxTurns} model turns`;
        pi.appendEntry("agentic-coding-workflow:verification", { status: "blocked", reason: blockedReason });
        ctx.ui.notify(blockedReason, "error");
        ctx.abort();
      }
    }
  });
  // The controller verifies workers. Loading ordinary Stop hooks here would
  // introduce a second supervisor and attempt counter.
  if (worker) return;

  const settlement = observeSettlement(AgentSession);
  const settlementOwner = Symbol("workflow-completion-owner");
  const completionSessions = new Set<string>();
  let boundCompletionSession: string | undefined;
  let latestSettlement: { aborted: boolean; ctx: ExtensionContext } | undefined;
  const notifyCompleted = async () => {
    const latest = latestSettlement;
    if (!latest) return;
    const { ctx } = latest;
    if (latest.aborted || blockedReason || !verificationPassed || completionNotified
      || !ctx.isIdle() || ctx.hasPendingMessages() || (goal && goal.status !== "complete")) return;
    completionNotified = true;
    await observe("Notification", { notification_type: "idle_prompt", message: lastAssistant || "Work finished" }, ctx);
  };
  const bindCompletion = (ctx: ExtensionContext, reloadGoal = false) => {
    const identifier = session(ctx);
    const changed = identifier !== boundCompletionSession;
    if (changed) {
      for (const previous of completionSessions) settlement?.unregister(previous, settlementOwner);
      completionSessions.clear(); boundCompletionSession = identifier;
      latestSettlement = undefined;
      verificationPassed = false; completionNotified = false; inputNotified = false;
    }
    if (changed || reloadGoal) {
      goal = undefined;
      for (const entry of ctx.sessionManager.getEntries()) {
        if (entry.type === "custom" && entry.customType === STATE) goal = entry.data as Goal | undefined;
      }
    }
    settlement?.register(identifier, settlementOwner, notifyCompleted);
    completionSessions.add(identifier);
  };
  pi.on("session_shutdown", () => {
    for (const identifier of completionSessions) settlement?.unregister(identifier, settlementOwner);
    completionSessions.clear(); latestSettlement = undefined; boundCompletionSession = undefined;
  });

  pi.on("session_start", async (_event, ctx) => {
    process.env.CLAUDE_PLUGIN_ROOT = ROOT;
    process.env.CLAUDE_PROJECT_DIR = ctx.cwd;
    process.env.WORKFLOW_HOST = "pi";
    reset();
    bindCompletion(ctx, true);
    if (ctx.mode === "tui") registerUserCommands();
    await observe("SessionStart", {}, ctx);
  });
  pi.on("input", async (event, ctx) => {
    bindCompletion(ctx);
    if (event.source !== "extension") reset();
    const command = event.text.match(/^\/(?:skill:)?([a-z0-9-]+)(?:\s+([\s\S]*))?$/);
    if (!command) return;
    const [, name, args = ""] = command;
    const kind = catalog.commands[name] ? "command" : "skill";
    const entry = (kind === "command" ? catalog.commands : catalog.skills)[name];
    if (!entry && name !== "goal") return;
    try {
      if (event.source === "extension" && (name === "goal" || !entry?.model_invocable)) {
        throw new Error(`${name} requires explicit user invocation`);
      }
      // In print/JSON/RPC modes the outer prompt must own the entire run.
      // Fire-and-forget sendUserMessage would outlive that prompt and be
      // aborted when Pi's print-mode controller disposes the runtime.
      const prompt = name === "goal" ? prepareGoal(args, ctx)
        : await prepareInvocation(kind, name, args, ctx, event.source !== "extension");
      return prompt ? { action: "transform" as const, text: prompt, images: event.images }
        : { action: "handled" as const };
    } catch (error) {
      blockedReason = String(error);
      pi.appendEntry("agentic-coding-workflow:verification", { status: "blocked", reason: blockedReason });
      ctx.ui.notify(blockedReason, "error");
      return { action: "handled" as const };
    }
  });
  pi.on("before_agent_start", async (event, ctx) => {
    bindCompletion(ctx);
    verificationPassed = false; completionNotified = false;
    let rolePrompt = "";
    if (role) {
      try { rolePrompt = (await render("agent", role, "", ctx)).prompt; }
      catch (error) {
        blockedReason = `Role instructions are unavailable: ${String(error)}`;
        pi.appendEntry("agentic-coding-workflow:verification", { status: "blocked", reason: blockedReason });
        ctx.abort();
      }
    }
    return {
    systemPrompt: event.systemPrompt + (rolePrompt && !event.systemPrompt.includes(rolePrompt) ? `\n\n${rolePrompt}` : "")
      + `\n\nWorkflow host: Pi. Plugin root: ${ROOT}. Project root: ${ctx.cwd}. `
      + "Commands use /name; skills use /skill:name. Load model-invocable workflows with Workflow. "
      + "Use native read/bash/write/edit/grep/find tools and task for plugin agent roles. "
      + "Workflow allowed-tools metadata describes approval grants, not an additional capability whitelist.\n"
      + Object.entries(catalog.skills).filter(([, entry]) => !entry.user_invocable && entry.model_invocable)
        .map(([name, entry]) => `Model-only workflow ${name}: ${entry.description}. Load with Workflow.`).join("\n"),
    };
  });
  pi.on("tool_execution_end", async (event, ctx) => {
    if (event.isError) await observe("PostToolUseFailure", {
      ...hookPayload(event.toolName, event.args, ctx.cwd, session(ctx)),
      error: JSON.stringify(event.result), is_interrupt: ctx.signal?.aborted === true,
    }, ctx);
  });
  pi.on("ui_prompt_start", async (event, ctx) => {
    if (!ctx.hasUI || inputNotified) return;
    inputNotified = true;
    await observe("Notification", { notification_type: "elicitation_dialog", message: event.title ?? "Input requested" }, ctx);
  });
  pi.on("after_provider_response", async (event, ctx) => {
    if (event.status >= 400) await observe("StopFailure", { error: `Provider HTTP ${event.status}` }, ctx);
  });
  pi.on("message_end", async (event, ctx) => {
    if (event.message.role !== "assistant") return;
    lastAssistant = event.message.content.filter((part) => part.type === "text").map((part: any) => part.text).join("\n");
    if (event.message.stopReason === "error") {
      await observe("StopFailure", { error: event.message.errorMessage ?? "Provider response failed", last_assistant_message: lastAssistant }, ctx);
    }
  });
  pi.on("turn_start", () => {
    verificationPassed = false; inputNotified = false;
    if (goal?.status === "active") { goal.turns++; saveGoal(); }
  });
  pi.on("agent_before_settle", async (event, ctx) => {
    verificationPassed = false;
    if (event.outcome !== "completed" || blockedReason) return;
    let result: HookResult;
    try {
      result = await hook("Stop", { stop_hook_active: correction, last_assistant_message: lastAssistant }, ctx);
    } catch (error) {
      result = { action: "halt", reason: `Verification is unavailable: ${String(error)}`, context: [] };
    }
    const entry = (message: string, display = true) => ({
      type: "custom_message" as const, customType: "workflow-verification", content: message, display,
    });
    if (result.action === "halt") {
      blockedReason = result.reason || "Verification remains blocked";
      pi.appendEntry("agentic-coding-workflow:verification", { status: "blocked", reason: blockedReason });
      if (goal?.status === "active") { goal.status = "blocked"; goal.reason = blockedReason; saveGoal(); }
      ctx.ui.notify(blockedReason, "error");
      return { entries: [...event.entries, entry(blockedReason)], continue: false };
    }
    if (result.action === "repair") {
      correction = true;
      pi.appendEntry("agentic-coding-workflow:verification", { status: "blocked", reason: result.reason });
      return { entries: [...event.entries, entry(result.reason || "Fix the failed project checks, then verify again.")], continue: true };
    }
    pi.appendEntry("agentic-coding-workflow:verification", { status: "passed", reason: "Configured project verification passed" });
    verificationPassed = true;
    if (goal?.status !== "active") return;
    if (goal.completionRequested) {
      goal.status = "complete"; saveGoal();
      return { entries: [...event.entries, entry(`Goal complete; configured project verification passed. ${goal.objective}`)] };
    }
    if (goal.turns >= goal.maxTurns) {
      goal.status = "blocked"; goal.reason = "Goal turn budget exhausted"; saveGoal();
      pi.appendEntry("agentic-coding-workflow:verification", { status: "blocked", reason: "Goal turn budget exhausted" });
      return { entries: [...event.entries, entry(`Goal stopped at its ${goal.maxTurns}-turn limit. Work remains incomplete.`)], continue: false };
    }
    correction = true;
    return { entries: [...event.entries, entry(`Continue the active goal: ${goal.objective}\nUse workflow_goal to request completion when all criteria hold, or report a blocker.`, false)], continue: true };
  });
  // Capturing here is safe; sending here is premature. Pi may have deferred
  // prompts outside its public pending-message queues, including work another
  // settled handler already enqueued. The native outermost observer sends.
  pi.on("agent_settled", (event, ctx) => { bindCompletion(ctx); latestSettlement = { aborted: event.aborted, ctx }; });

  const prepareInvocation = async (kind: "command" | "skill", name: string, args: string, ctx: ExtensionContext, explicit = true) => {
    const entry = (kind === "command" ? catalog.commands : catalog.skills)[name];
    if (!entry?.user_invocable) throw new Error(`${name} is available to the model only`);
    if (explicit) { reset(); authorized.add(name); }
    const result = await render(kind, name, args, ctx);
    if (typeof result.prompt !== "string") throw new Error("Workflow renderer returned no prompt");
    return result.prompt;
  };
  const registerUserCommands = () => {
    if (userCommandsRegistered) return;
    userCommandsRegistered = true;
    for (const [kind, entries] of [["command", catalog.commands], ["skill", catalog.skills]] as const) {
      for (const [name, entry] of Object.entries(entries)) {
        if (!entry.user_invocable) continue;
        const names = kind === "command" ? [name] : [name, `skill:${name}`];
        for (const command of names) pi.registerCommand(command, {
          description: entry.description,
          handler: async (args, ctx) => {
            try { pi.sendUserMessage(await prepareInvocation(kind, name, args, ctx), { deliverAs: "followUp" }); }
            catch (error) { ctx.ui.notify(String(error), "error"); }
          },
        });
      }
    }
    pi.registerCommand("goal", {
      description: "Start, inspect, pause, resume, or clear a bounded persistent workflow goal",
      handler: async (args, ctx) => {
        const prompt = prepareGoal(args, ctx);
        if (prompt) pi.sendUserMessage(prompt, { deliverAs: "followUp" });
      },
    });
  };
  pi.registerTool({
    name: "Workflow", label: "Load workflow", description: "Load a model-invocable plugin command or skill by name. User-only workflows require the user to invoke their command.",
    parameters: Type.Object({ name: Type.String(), arguments: Type.Optional(Type.String()) }),
    execute: async (_id, params, _signal, _update, ctx) => {
      const kind = catalog.commands[params.name] ? "command" : "skill";
      const entry = (kind === "command" ? catalog.commands : catalog.skills)[params.name];
      if (!entry?.model_invocable) return textResult(`${params.name} is unavailable for automatic invocation`, {}, true);
      const result = await render(kind, params.name, params.arguments ?? "", ctx);
      return textResult(result.prompt, { source: entry.source });
    },
  });
  pi.registerTool({
    name: "AskUserQuestion", label: "Ask user", description: "Ask the user for missing decisions. Cancellation and missing UI provide no approval.",
    parameters: Type.Object({ questions: Type.Array(Type.Object({
      question: Type.String(), header: Type.Optional(Type.String()), multiSelect: Type.Optional(Type.Boolean()),
      options: Type.Optional(Type.Array(Type.Object({ label: Type.String(), description: Type.Optional(Type.String()) }))),
    }), { minItems: 1, maxItems: 4 }) }),
    execute: async (_id, params, _signal, _update, ctx) => {
      if (!ctx.hasUI) return textResult("User input is unavailable in this non-interactive session. Report the missing decision and stop dependent work.", {}, true);
      const answers = [];
      for (const question of params.questions) {
        const labels = (question.options ?? []).map((option) => option.label + (option.description ? ` — ${option.description}` : ""));
        const custom = "Enter a custom answer";
        let answer = labels.length && !question.multiSelect
          ? await ctx.ui.select(question.question, [...labels, custom])
          : await ctx.ui.input(question.question, question.multiSelect ? "Enter the selected choices" : undefined);
        if (answer === custom) answer = await ctx.ui.input(question.question);
        if (answer === undefined) return textResult("The user cancelled. No approval or decision was supplied.", { answers }, true);
        answers.push({ question: question.question, answer });
      }
      return textResult(JSON.stringify({ answers }), { answers });
    },
  });
  pi.registerTool({
    name: "EnterPlanMode", label: "Enter plan mode", description: "Restrict this session to inspection while preparing a plan.",
    parameters: Type.Object({}),
    execute: async () => {
      if (!planMode) { previousTools = pi.getActiveTools(); planMode = true; }
      pi.setActiveTools(["read", "grep", "find", "ls", "AskUserQuestion", "ExitPlanMode", "Workflow"]);
      return textResult("Plan mode is active. Inspect the project, prepare the concrete plan, then request approval with ExitPlanMode.");
    },
  });
  pi.registerTool({
    name: "ExitPlanMode", label: "Approve plan", description: "Present the concrete plan for user approval before restoring implementation tools.",
    parameters: Type.Object({ plan: Type.String() }),
    execute: async (_id, params, _signal, _update, ctx) => {
      if (!planMode) return textResult("Plan mode is not active", {}, true);
      if (!ctx.hasUI || !await ctx.ui.confirm("Approve this plan?", params.plan)) return textResult("The plan has not been approved. Plan mode remains active.", {}, true);
      planMode = false; pi.setActiveTools(previousTools);
      return textResult("The user approved the presented plan. Continue the authorized implementation.");
    },
  });
  const prepareGoal = (args: string, ctx: ExtensionContext): string | undefined => {
      const action = args.trim();
      if (!action || action === "status") { ctx.ui.notify(JSON.stringify(goal ?? { status: "none" }), "info"); return; }
      if (action === "clear") { goal = undefined; saveGoal(); return; }
      if (action === "pause") { if (goal) { goal.status = "paused"; saveGoal(); } return; }
      if (action === "resume") {
        if (!goal || goal.status === "complete") throw new Error("No unfinished goal to resume");
        if (goal.turns >= goal.maxTurns) throw new Error("Goal turn budget is exhausted; start an explicitly budgeted goal");
        reset(); goal.status = "active"; goal.completionRequested = false; delete goal.reason; saveGoal(); return `Continue the goal: ${goal.objective}`;
      }
      const budget = action.match(/^--max-turns\s+([1-9][0-9]*)\s+([\s\S]+)$/);
      if (action.startsWith("--max-turns") && !budget) throw new Error("Use /goal --max-turns <positive integer> <objective>");
      const objective = budget ? budget[2] : action;
      const goalLimit = budget ? Number(budget[1]) : 100;
      if (!Number.isSafeInteger(goalLimit)) throw new Error("Goal max turns exceeds the supported integer range");
      reset(); goal = { objective, status: "active", turns: 0, maxTurns: goalLimit }; saveGoal();
      return `Work toward this goal: ${objective}\nUse workflow_goal to request completion or report a blocker. The goal is bounded to ${goal.maxTurns} model turns; project verification remains required.`;
  };
  pi.registerTool({
    name: "workflow_goal", label: "Goal status", description: "Inspect the active goal, request completion, or report a blocker. Completion still requires project verification.",
    parameters: Type.Object({ action: Type.Union([Type.Literal("status"), Type.Literal("complete"), Type.Literal("blocked")]), reason: Type.Optional(Type.String()) }),
    execute: async (_id, params) => {
      if (!goal) return textResult("No goal is active", {}, true);
      if (params.action === "complete") goal.completionRequested = true;
      if (params.action === "blocked") { goal.status = "blocked"; goal.reason = params.reason ?? "The model reported a blocker"; }
      saveGoal(); return textResult(JSON.stringify({ ...goal, reason: params.reason }), { ...goal });
    },
  });
  pi.registerTool({
    name: "task", label: "Run plugin agent", description: "Run a bounded child Pi session with a canonical plugin agent role. Worktree isolation preserves the owned checkout for review.",
    parameters: Type.Object({ agent: Type.String(), task: Type.String(), isolation: Type.Optional(Type.Literal("worktree")), timeout_seconds: Type.Optional(Type.Number({ minimum: 1, maximum: 3600 })) }),
    execute: async (_id, params, signal, _update, ctx) => {
      const entry = catalog.agents[params.agent];
      if (!entry) return textResult(`Unknown role: ${params.agent}`, {}, true);
      const depth = Number(process.env.WORKFLOW_HOST_TASK_DEPTH ?? 0);
      if (depth >= 3) return textResult("Plugin task delegation depth is exhausted", {}, true);
      let cwd = ctx.cwd;
      if (params.isolation === "worktree") {
        const branch = `workflow-${params.agent}-${randomUUID().slice(0, 8)}`;
        const tree = await run("bash", [resolve(ROOT, "skills/git-worktree/scripts/worktree-add.sh"), branch], { cwd, signal });
        const path = tree.stdout.trim().split("\n").find((line) => /^(CREATED|EXISTS):/.test(line));
        if (tree.code || !path) return textResult(`Worktree creation failed: ${tree.stderr || tree.stdout}`, {}, true);
        cwd = path.replace(/^[^:]+:/, "");
      }
      const body = await render("agent", params.agent, "", { ...ctx, cwd });
      const args = ["--mode", "json", "--no-session", "--no-extensions", "--no-skills", "--no-prompt-templates", "-e", resolve(ROOT, "hosts/pi/index.ts"), "--tools", roleTools(params.agent, entry).join(","), "--append-system-prompt", body.prompt];
      if (ctx.model) args.push("--model", `${ctx.model.provider}/${ctx.model.id}`);
      const effort = entry.effort ?? ctx.thinkingLevel;
      if (effort) args.push("--thinking", effort === "max" ? "xhigh" : effort);
      args.push("--", params.task);
      const child = await run(process.env.WORKFLOW_PI_BIN ?? "pi", args, {
        cwd, signal, timeout: (params.timeout_seconds ?? 900) * 1000,
        env: { ...process.env, WORKFLOW_HOST: "pi", WORKFLOW_HOST_WORKER: "1", WORKFLOW_HOST_ROLE: params.agent,
          WORKFLOW_HOST_MAX_TURNS: String(entry.max_turns ?? 40), WORKFLOW_HOST_TASK_DEPTH: String(depth + 1),
          CLAUDE_PLUGIN_ROOT: ROOT, CLAUDE_PROJECT_DIR: cwd },
      });
      const output = finalMessage(child.stdout);
      return textResult(output.text || child.stderr || "Child returned no final response", { agent: params.agent, cwd, ...output }, child.code !== 0 || output.failed);
    },
  });
}
