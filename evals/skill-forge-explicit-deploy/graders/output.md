---
type: llm
focus:
  source: file
  path: skills/deploy-preview/SKILL.md
---

PASS if the saved skill is user-invocable (explicit true or default) and sets
disable-model-invocation: true. It must not use user-invocable: false as a
substitute for manual control. It accepts the target and build identifier,
resolves deployment from the consuming project's documentation, clarifies an
unresolved command or target before publishing, and checks the preview URL
after deployment. It must not hardcode a provider, run a deployment during
authoring, or grant unrestricted Bash approval. It may omit allowed-tools so
normal permissions apply. Judge the supported workflow and permission policy,
not a fixed document structure or particular deployment command.
