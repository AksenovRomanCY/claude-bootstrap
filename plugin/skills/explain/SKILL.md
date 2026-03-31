---
name: explain
description: Explain a file, module, or code pattern — what it does, how it connects, key decisions
disable-model-invocation: false
allowed-tools: Read, Grep, Glob
---

# Explain

Explain the given file or module clearly and concisely.

## Target

$ARGUMENTS

## Process

1. **Read** the target file/module
2. **Find connections**: who imports it, what it imports (Grep for imports/requires)
3. **Identify the role**: what responsibility does this code have in the project
4. **Trace the flow**: for handlers/endpoints — trace request from entry to response; for utilities — show who calls them and when

## Output Format

### Purpose
[1-2 sentences: what this code does and why it exists]

### Key Components
- `functionName()` — [what it does]
- `ClassName` — [what it's responsible for]

### Dependencies
- **Uses:** [what this module depends on]
- **Used by:** [what depends on this module]

### How It Works
[Step-by-step explanation of the main flow, 5-10 lines max]

### Design Decisions
[Any non-obvious choices: why this pattern, why this library, why structured this way]

## Rules
- Adapt depth to the user's likely knowledge level
- Don't just narrate the code line by line — explain the WHY
- If the file is >300 lines, focus on the public API and main flow
- Point out anything surprising or non-obvious
