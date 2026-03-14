## Summary

<!--
Describe what this PR does and why. Be specific. One paragraph is usually enough.
Link the related issue below.
-->

Closes #

---

## What changed

<!--
List the files and logical areas modified. Group related changes.
-->

- 
- 

---

## Testing

<!--
Describe how you tested the changes.
- Did you run the test suite? (`python -m pytest test/`)
- Did you add new tests? Where?
- Did you test manually? What did you verify?
-->

- [ ] Existing tests pass
- [ ] New tests added for new behaviour (if applicable)
- [ ] Manually verified against a running local instance (if applicable)

---

## Checklist

### Code quality
- [ ] All new and modified Python functions have fully typed signatures (parameters + return types)
- [ ] Typed domain models used for structured data (`dataclass`, `TypedDict`, or Pydantic)
- [ ] No business logic in Flask route handlers
- [ ] No agent logic in graph files — graph files only wire nodes

### Documentation
- [ ] `docs/architecture.md` updated (if architecture changed)
- [ ] `docs/data_model.md` updated (if schema or data flow changed)
- [ ] `docs/development.md` updated (if setup or conventions changed)
- [ ] `docs/operations.md` updated (if workflow or CLI changed)
- [ ] `README.md` updated (if setup or entrypoints changed)

### Environment
- [ ] `environment.yml` updated (if dependencies added or removed)
- [ ] No secrets or API keys committed
- [ ] `.env.example` updated (if new environment variables added)

### Scope and design
- [ ] PR scope is narrow — one logical change
- [ ] Business logic is in `src/agents/` or `src/agent_tools/`, not in `api/`
- [ ] Code is modular and follows existing layer boundaries

---

## Notes for reviewers

<!--
Anything the reviewer should know: edge cases, known limitations, follow-up work planned.
-->
