from __future__ import annotations
from typing import TYPE_CHECKING, Any
if TYPE_CHECKING:
    from .memory import LongTermMemory, ToolResultMemory
    from .task_manager import Task, TaskMemory
DEFAULT_SYSTEM = 'You are a local agent with file tools only (read/write/list/summarize files). You cannot control\nthe OS GUI, File Explorer, mouse, or keyboard shortcuts.\n\nWhen the current task involves creating, writing, reading, or listing files or folders, you MUST use the corresponding\ntool in the same turn (e.g. write_file to create or overwrite a file). Do not answer with only prose, UUIDs, or\n"please provide the next action" — call the tool with concrete paths and arguments.\n\nTo list folder contents, call list_files with directory set to that folder (use the path the user gave). Do not describe\na directory listing from memory — always call the tool when the task asks to list or enumerate files.\n\nAfter tools return, you may briefly interpret the results. When the current task needs no further tools, finish with\nTASK_COMPLETE — best on its own line; if you add it after a sentence, end the message with exactly TASK_COMPLETE\n(e.g. "... done. TASK_COMPLETE" is OK). "Task COMPLETE", "TASK COMPLETE", or "TASKCOMPLETE" on the last line also count.\n\nDo not type JSON or dicts that look like tool calls in plain text — only use real tool calls from the API.\n\nDo not invent or rewrite the task list. Do not output fake "Task list updated" blocks. Do not copy sections from the\nsystem message (no "##" or "---" banners, no echoed "Recent tool results"). Never paste only a task id.\n\nRules:\n- Use absolute paths when the user specified a full path (e.g. D:/Test/...).\n- After a successful write/read that finishes the current task, one short sentence then TASK_COMPLETE on the last line.\n- If a task is impossible with file tools only, one sentence of explanation, then TASK_COMPLETE.'

def _format_task_list(task_memory: TaskMemory) -> str:
    lines = []
    for t in task_memory.tasks:
        lines.append(f'- [{t.status.value}] ({t.id}) {t.description}')
    return '\n'.join(lines) if lines else '(no tasks)'

def _format_current_task(task: Task | None) -> str:
    if task is None:
        return '(none — all tasks may be done)'
    return f'({task.id}) {task.description}\nStatus: {task.status.value}'

def _format_tool_list(tool_definitions: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for t in tool_definitions:
        fn = t.get('function') or {}
        name = fn.get('name', '?')
        desc = (fn.get('description') or '').strip()
        lines.append(f'- **{name}**: {desc}')
    return '\n'.join(lines) if lines else '(none)'

def build_messages(*, system_prompt: str, goal: str, task_memory: TaskMemory, current_task: Task | None, long_term: LongTermMemory, tool_results: ToolResultMemory, conversation_messages: list[dict[str, Any]], tool_definitions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    tools_block = 'Tools are invoked by the model using function calls. Use exact tool names and valid JSON arguments.'
    user_context = f'--- User goal ---\n{goal}\n\n--- Task list ---\n{_format_task_list(task_memory)}\n\n--- Current task (do this now) ---\n{_format_current_task(current_task)}\n\n--- Saved notes (memory) ---\n{long_term.format_for_prompt()}\n\n--- Recent tool results ---\n{tool_results.format_for_prompt()}\n\n--- Tools you can call ---\n{_format_tool_list(tool_definitions)}\n\n--- Reminder ---\n{tools_block}\n'
    system_full = f'{system_prompt.strip()}\n\n{user_context.strip()}'
    messages: list[dict[str, Any]] = [{'role': 'system', 'content': system_full}]
    messages.extend(conversation_messages)
    return messages

def default_system_prompt() -> str:
    return DEFAULT_SYSTEM
