<div align="center">

<img src="assets/banner.png" alt="Modern IA Agent — local planner and file agent powered by Ollama" width="100%" />

# Modern IA Agent

**Your goals. Your files. Your GPU.**  
A **local-first** AI agent that **plans**, **acts** on your filesystem, and **remembers**—powered by [Ollama](https://ollama.com/), with **no cloud LLM required**.

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-3776AB?style=flat&logo=python&logoColor=white)](https://www.python.org/)
[![Ollama](https://img.shields.io/badge/Ollama-local%20LLM-111111?style=flat)](https://ollama.com/)
[![License](https://img.shields.io/badge/license-add%20LICENSE-8A8A8A?style=flat)](#license)

[Features](#-what-you-get) · [Architecture](#-architecture-at-a-glance) · [Quick start](#-quick-start) · [CLI](#-command-line)

</div>

---

## Why this exists

| | |
|--|--|
| **Privacy** | The model runs on **your machine** via Ollama. Your codebase and goals are not sent to a third-party API for inference. |
| **Clarity** | The agent **writes a visible plan** (ordered tasks) before executing—so you see *what* it will do, not just a black box. |
| **Control** | Tools are **filesystem-only** (read, write, list, summarize). No surprise shell commands or GUI automation. |
| **Continuity** | **JSON memory** under `memory/` keeps conversation, tasks, and tool context—useful for longer runs and debugging. |

---

## What you get

- **Planner** — Breaks your high-level goal into **3–12 concrete tasks** (JSON), constrained to real file capabilities.
- **Executor loop** — Works **one task at a time**, calling Ollama with **function tools** until the model signals completion (`TASK_COMPLETE`).
- **Four tools** — `read_file`, `write_file`, `list_files`, `summarize_file` on a workspace you choose.
- **Safety rails** — `--max-steps`, `--num-predict`, and optional `--fresh` to limit runaway generations and stale chat.

---

## How it flows (end to end)

From a single sentence to finished file work—**plan first**, then **execute with tools**.

```mermaid
flowchart LR
    subgraph You["You"]
        G[/"Goal in plain English"/]
    end

    subgraph Agent["Modern IA Agent"]
        P["Planner\n(JSON tasks)"]
        L["Executor loop\n(chat + tools)"]
        R["Tool registry"]
    end

    subgraph Machine["Your machine"]
        O[("Ollama\n/api/chat")]
        W[("Workspace\n(files)")]
        M[("memory/\n(JSON state)")]
    end

    G --> P
    P --> L
    L <--> O
    L --> R
    R --> W
    P & L --> M
```

---

## Architecture at a glance

The **planner** and **executor** share the same Ollama server but different prompts: one outputs **only a task list**, the other **uses tools** and finishes steps with **`TASK_COMPLETE`**.

```mermaid
flowchart TB
    subgraph CLI["Entry: python -m agent"]
        MAIN["main.py\nworkspace · model · flags"]
    end

    subgraph Plan["Phase 1 — Plan"]
        PL["planner.py"]
        PL -->|"POST /api/chat\n(no tools)"| OM1[Ollama]
        OM1 --> TM["tasks.json\ntask list + status"]
    end

    subgraph Exec["Phase 2 — Execute"]
        AL["agent_loop.py"]
        PB["prompt_builder.py\n(goal + task + memory + tools)"]
        AL --> PB
        PB -->|"POST /api/chat\n+ tool definitions"| OM2[Ollama]
        OM2 -->|"tool_calls"| TR["tools/*.py"]
        TR --> FS["Filesystem\n(workspace)"]
        AL --> CM["conversation.json"]
        AL --> LT["notes.json"]
        AL --> TRM["tool_results.json"]
    end

    MAIN --> PL
    MAIN --> AL
    TM --> AL
```

---

## Inside the executor loop

Each **step** is one model turn: either **tool calls** (batched), **text + completion**, or **deterministic helpers** (e.g. listing a folder when appropriate). Tasks advance when the reply ends with an accepted **completion line**.

```mermaid
flowchart TD
    A["Next task → IN_PROGRESS"] --> B["Build messages\n(system + goal + task list +\ncurrent task + notes + tool results)"]
    B --> C["Ollama chat + tools"]
    C --> D{"Model returns\ntool_calls?"}

    D -->|"Yes"| E["Run each tool\n(read/write/list/summarize)"]
    E --> F["Append assistant + tool messages\nRecord tool_results"]
    F --> G{"max_steps?"}
    G -->|"OK"| C
    G -->|"Exceeded"| Z["Stop"]

    D -->|"No"| H["Append assistant text"]
    H --> I{"Last line =\nTASK_COMPLETE?"}
    I -->|"Yes"| J["Mark task done,\nadd note, next task"]
    I -->|"No"| K["Optional reminder\n(summarize / file work)"]
    J --> L{"All tasks\ndone?"}
    L -->|"Yes"| M["Return final output"]
    L -->|"No"| A
    K --> C
```

---

## Memory model (what gets saved)

All persistent state lives under **`memory/`** (you can `.gitignore` these for a clean repo).

```mermaid
flowchart LR
    subgraph files["memory/*.json"]
        T["tasks.json\nplan + progress"]
        C["conversation.json\nchat turns"]
        N["notes.json\nlong-term snippets"]
        R["tool_results.json\nrecent outputs"]
    end

    subgraph used["Used for"]
        T --> u1["Planner output & task status"]
        C --> u2["Executor context"]
        N --> u3["Cross-task recall"]
        R --> u4["Tool grounding"]
    end
```

---

## Quick start

**Prerequisites:** Python **3.10+**, [Ollama](https://ollama.com/) installed and running, model pulled (e.g. `ollama pull mistral`).

```bash
git clone https://github.com/<your-username>/ModernIAAgent.git
cd ModernIAAgent
python -m venv .venv
# Windows: .venv\Scripts\Activate.ps1   |   Unix: source .venv/bin/activate
pip install -r requirements.txt
ollama serve   # if not already running
python -m agent "Summarize the README files in this folder" --fresh
```

Run from the **repository root** so `python -m agent` resolves. Use **`--workspace` / `-w`** to point file tools at your project directory.

---

## Command line

| Option | Description |
|--------|-------------|
| `goal` or `--goal` / `-g` | What you want done (required). |
| `--model` / `-m` | Ollama tag (default: `mistral:latest`). |
| `--ollama` | Base URL (default: `http://127.0.0.1:11434`). |
| `--workspace` / `-w` | Directory for file tools (default: cwd). |
| `--max-steps` | Max LLM steps (default: `200`). |
| `--timeout` | HTTP read timeout seconds (default: `600`). |
| `--num-predict` | Max tokens per reply (default: `4096`). |
| `--fresh` | Clear `conversation.json` and `tool_results.json` before run. |
| `--verbose` / `-v` | Debug logging. |

**Exit codes:** `0` success, `1` if Ollama is unreachable or planning fails.

---

## Project layout

```text
ModernIAAgent/
├── agent/           # CLI, loop, Ollama client, planner, prompts, memory helpers
├── tools/           # read_file, write_file, list_files, summarize_file
├── memory/          # runtime JSON (gitignored by default for session data)
├── requirements.txt
└── README.md
```

---

## Limitations (honest scope)

- **No shell** — Cannot run terminal commands; only the four file tools.
- **Paths** — Give explicit paths in your goal; the planner avoids inventing user-specific directories.
- **Model-dependent** — Tool use and `TASK_COMPLETE` behavior depend on your Ollama model.

---

## Contributing

Issues and PRs are welcome. Keep changes focused and consistent with existing patterns (typing, logging, small modules).

---

## License

Add a `LICENSE` file (e.g. MIT or Apache-2.0) when you publish. Until then, rights remain with the author unless stated otherwise.
