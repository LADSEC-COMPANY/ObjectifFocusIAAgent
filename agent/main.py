from __future__ import annotations
import argparse
import logging
import os
import sys
from pathlib import Path
from .agent_loop import AgentConfig, run_agent_loop
from .llm_client import OllamaClient, check_ollama_server
from .memory import ConversationMemory, LongTermMemory, ToolResultMemory
from .planner import plan_tasks
from .task_manager import TaskMemory
from .tools import default_registry

def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent

def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format='%(asctime)s | %(levelname)-8s | %(name)s | %(message)s', datefmt='%Y-%m-%d %H:%M:%S')

def main() -> int:
    root = _project_root()
    memory_dir = root / 'memory'
    parser = argparse.ArgumentParser(description='Local Ollama agent with tools and task memory.')
    parser.add_argument('goal', nargs='?', help='High-level goal (or use --goal)')
    parser.add_argument('--goal', '-g', dest='goal_flag', help='Goal as a flag instead of positional')
    parser.add_argument('--model', '-m', default='mistral:latest', help='Ollama model tag (must be pulled locally: ollama pull <name>)')
    parser.add_argument('--ollama', default='http://127.0.0.1:11434', help='Ollama base URL')
    parser.add_argument('--timeout', type=float, default=600.0, help='HTTP read timeout for Ollama /api/chat in seconds (raise if local model is slow or cold-starting)')
    parser.add_argument('--num-predict', type=int, default=4096, metavar='N', help='Ollama options.num_predict: max tokens per reply (caps runaway generations)')
    parser.add_argument('--workspace', '-w', type=Path, default=Path.cwd(), help='Working directory for file tools')
    parser.add_argument('--max-steps', type=int, default=200, help='Safety cap on LLM steps')
    parser.add_argument('--fresh', action='store_true', help='Clear conversation.json and tool_results.json before this run (avoids stale chat confusing the model)')
    parser.add_argument('--verbose', '-v', action='store_true', help='Debug logging')
    args = parser.parse_args()
    goal = args.goal or args.goal_flag
    if not goal or not str(goal).strip():
        parser.error('Provide a goal as a positional argument or via --goal.')
    _setup_logging(args.verbose)
    log = logging.getLogger('agent.main')
    os.chdir(args.workspace)
    log.info('Workspace: %s', args.workspace.resolve())
    memory_dir.mkdir(parents=True, exist_ok=True)
    conv_path = memory_dir / 'conversation.json'
    tasks_path = memory_dir / 'tasks.json'
    notes_path = memory_dir / 'notes.json'
    tool_res_path = memory_dir / 'tool_results.json'
    conversation = ConversationMemory.load(conv_path)
    task_memory = TaskMemory.load(tasks_path)
    long_term = LongTermMemory.load(notes_path)
    tool_results = ToolResultMemory.load(tool_res_path)
    if args.fresh:
        conversation.clear()
        tool_results.clear()
        log.info('Cleared conversation + tool_results (--fresh).')
    client = OllamaClient(base_url=args.ollama, model=args.model, timeout=args.timeout, num_predict=args.num_predict)
    try:
        check_ollama_server(args.ollama)
    except RuntimeError as e:
        log.error('%s', e)
        return 1
    log.info('--- Goal ---\n%s', goal.strip())
    try:
        plan_tasks(client, goal, task_memory, model=args.model)
    except RuntimeError as e:
        log.error('%s', e)
        return 1
    log.info('--- Plan (tasks.json) ---\n%s', task_memory.to_dict())
    registry = default_registry()
    cfg = AgentConfig(model=args.model, max_steps=args.max_steps)
    final = run_agent_loop(goal=goal, task_memory=task_memory, conversation=conversation, long_term=long_term, tool_results=tool_results, client=client, registry=registry, config=cfg)
    log.info('--- Final output ---\n%s', final)
    return 0
if __name__ == '__main__':
    sys.exit(main())
