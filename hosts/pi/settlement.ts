/** Pi 1.4's public pending-message count excludes deferred settled actions. */
export type Completion = { token: symbol; callback: (session: any) => void | Promise<void> };
export type ObserverState = {
  version: 1;
  callbacks: Map<string, Completion>;
  depth: WeakMap<object, number>;
};
const OBSERVER = Symbol.for("agentic-coding-workflow.pi.settlement-observer.v1");

/** Observe after native settlement AND all recursively deferred work drains.
 *
 * The exported host AgentSession is the same class used by the CLI and SDK.
 * Install once per native prototype; reload replaces only the owning callback.
 * An unsupported native version disables optional completion notices quietly.
 */
export function observeSettlement(Session: any) {
  const prototype = Session?.prototype;
  if (!prototype || typeof prototype._emitAgentSettled !== "function") return undefined;
  let state = prototype[OBSERVER] as ObserverState | undefined;
  if (state && state.version !== 1) return undefined;
  if (!state) {
    const original = prototype._emitAgentSettled;
    state = { version: 1, callbacks: new Map(), depth: new WeakMap() };
    const installed = state;
    try {
      Object.defineProperty(prototype, OBSERVER, { value: installed });
      prototype._emitAgentSettled = async function (...args: any[]) {
        const previous = installed.depth.get(this) ?? 0;
        installed.depth.set(this, previous + 1);
        let completed = false;
        try {
          const value = await original.apply(this, args);
          completed = true;
          return value;
        } finally {
          const remaining = (installed.depth.get(this) ?? 1) - 1;
          if (remaining) installed.depth.set(this, remaining);
          else installed.depth.delete(this);
          if (completed && remaining === 0) {
            try {
              const identifier = this.sessionManager.getSessionId();
              await installed.callbacks.get(identifier)?.callback(this);
            } catch { /* Optional notices never change native completion. */ }
          }
        }
      };
    } catch { return undefined; }
  }
  return {
    register(identifier: string, token: symbol, callback: Completion["callback"]) {
      state.callbacks.set(identifier, { token, callback });
    },
    unregister(identifier: string, token: symbol) {
      if (state.callbacks.get(identifier)?.token === token) state.callbacks.delete(identifier);
    },
  };
}
