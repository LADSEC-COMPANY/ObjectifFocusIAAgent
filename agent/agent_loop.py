from __future__ import annotations
import json
import logging
import re
import uuid
from dataclasses import dataclass
from typing import Any
from .llm_client import OllamaClient
from .memory import ConversationMemory, LongTermMemory, ToolResultMemory
from .path_utils import format_list_result_for_user, pick_listing_directory, should_auto_complete_list_task, should_try_list_fallback
from .prompt_builder import build_messages, default_system_prompt
from .task_manager import TaskMemory, TaskStatus
from .tools import ToolRegistry, default_registry
logger = logging.getLogger(__name__)

@dataclass
class AgentConfig:
    model: str = 'mistral:latest'
    max_steps: int = 200
    system_prompt: str | None = None

def _assistant_message_dict(content: str | None, tool_calls: list[dict[str, Any]] | None) -> dict[str, Any]:
    m: dict[str, Any] = {'role': 'assistant', 'content': content}
    if tool_calls:
        m['tool_calls'] = tool_calls
    return m

def _is_completion_line(line: str) -> bool:
    """Matches TASK_COMPLETE, Task complete, TASK COMPLETE, TASKCOMPLETE (common model typos)."""
    s = line.strip()
    s = re.sub(r'^\*+|\*+$', '', s).strip()
    s = s.rstrip('.!?')
    if not s:
        return False
    return bool(re.match('^TASK[_\\s]*COMPLETE$', s, re.IGNORECASE))

def _strip_completion_suffix(text: str) -> str:
    lines = text.splitlines()
    while lines and not lines[-1].strip():
        lines.pop()
    while lines and _is_completion_line(lines[-1]):
        lines.pop()
    return '\n'.join(lines).rstrip()

def _task_completed(content: str | None) -> bool:
    if not content or not content.strip():
        return False
    text = content.strip()
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if lines and _is_completion_line(lines[-1]):
        return True
    if re.search(r'\bTASK[_\s]*COMPLETE\s*$', text, re.IGNORECASE):
        return True
    return False

def _task_is_summarize_only(description: str) -> bool:
    d = description.lower()
    if 'summar' not in d:
        return False
    if any((k in d for k in ('read each', 'read all', 'read every', 'verify by reading', 'open each'))):
        return False
    return True

def _task_looks_like_file_work(description: str) -> bool:
    if _task_is_summarize_only(description):
        return False
    d = description.lower()
    keys = ('write', 'create', 'file', 'read', 'list', 'save', 'folder', 'directory', 'path', '.txt', 'edit', 'text', 'empty')
    return any((k in d for k in keys))

def _append_synthetic_list_files(conversation: ConversationMemory, registry: ToolRegistry, tool_results: ToolResultMemory, directory: str) -> dict[str, Any]:
    call_id = f'fallback-{uuid.uuid4().hex[:12]}'
    args = {'directory': directory}
    result = registry.execute('list_files', args)
    tool_results.record('list_files', args, result, success=bool(result.get('success', True)))
    conversation.append({'role': 'assistant', 'content': '', 'tool_calls': [{'id': call_id, 'type': 'function', 'function': {'name': 'list_files', 'arguments': json.dumps(args)}}]})
    conversation.append({'role': 'tool', 'content': json.dumps(result, ensure_ascii=False, default=str), 'name': 'list_files', 'tool_call_id': call_id})
    logger.info('Deterministic list_files(%s) success=%s', directory, result.get('success'))
    return result

def run_agent_loop(goal: str, task_memory: TaskMemory, conversation: ConversationMemory, long_term: LongTermMemory, tool_results: ToolResultMemory, client: OllamaClient, registry: ToolRegistry | None=None, config: AgentConfig | None=None) -> str:
    cfg = config or AgentConfig()
    registry = registry or default_registry()
    tools = registry.definitions()
    system_prompt = cfg.system_prompt or default_system_prompt()
    last_text = ''
    steps = 0
    nudged_task_id: str | None = None
    while not task_memory.all_done():
        task_memory.start_next_if_needed()
        current = task_memory.current_task()
        if current is None:
            logger.info('No remaining tasks; exiting loop.')
            break
        if current.status == TaskStatus.TODO:
            current.status = TaskStatus.IN_PROGRESS
            task_memory.persist()
        logger.info('Step %d | Current task: %s', steps + 1, current.description[:120])
        messages = build_messages(system_prompt=system_prompt, goal=goal, task_memory=task_memory, current_task=current, long_term=long_term, tool_results=tool_results, conversation_messages=conversation.messages, tool_definitions=tools)
        resp = client.chat(messages, tools=tools, model=cfg.model)
        msg = resp.message
        steps += 1
        if msg.tool_calls:
            asst = _assistant_message_dict(msg.content, msg.tool_calls)
            conversation.append(asst)
            logger.info('LLM requested %d tool call(s)', len(msg.tool_calls))
            for tc in msg.tool_calls:
                fn = tc.get('function') or {}
                name = fn.get('name', '')
                tid = tc.get('id', '')
                args = OllamaClient.tool_call_arguments(tc)
                logger.info('Tool call: %s %s', name, json.dumps(args, default=str)[:500])
                result = registry.execute(name, args)
                tool_results.record(name, args, result, success=bool(result.get('success', True)))
                payload = json.dumps(result, ensure_ascii=False, default=str)
                tool_msg = {'role': 'tool', 'content': payload, 'name': name}
                if tid:
                    tool_msg['tool_call_id'] = tid
                conversation.append(tool_msg)
                logger.info('Tool result success=%s', result.get('success'))
            if steps >= cfg.max_steps:
                logger.warning('max_steps reached during tool batch')
                last_text = 'Stopped: max_steps reached.'
                break
            continue
        directory = pick_listing_directory(goal, current.description)
        if directory and should_try_list_fallback(goal, current.description):
            result = _append_synthetic_list_files(conversation, registry, tool_results, directory)
            if result.get('success') and should_auto_complete_list_task(goal, current.description):
                last_text = format_list_result_for_user(result)
                long_term.add_note(f'Completed task {current.id} (deterministic list_files): {current.description}\n{last_text[:2000]}', source='task_complete')
                task_memory.mark_done(current.id)
                logger.info('Marked task DONE after deterministic list_files: %s', current.id)
                nudged_task_id = None
            if steps >= cfg.max_steps:
                logger.warning('max_steps reached')
                last_text = 'Stopped: max_steps reached.'
                break
            continue
        content = msg.content or ''
        conversation.append({'role': 'assistant', 'content': content})
        logger.info('Assistant (no tools): %s', content[:300] + ('...' if len(content) > 300 else ''))
        if _task_completed(content):
            stripped = _strip_completion_suffix(content).strip()
            if stripped:
                last_text = stripped
            else:
                logger.info('Completion-only reply; keeping prior output as final result.')
            long_term.add_note(f'Completed task {current.id}: {current.description}\nClosing: {content[:800]}', source='task_complete')
            task_memory.mark_done(current.id)
            logger.info('Marked task DONE: %s', current.id)
        else:
            if content.strip():
                last_text = content
            logger.info('Task not marked complete (reply must end with TASK_COMPLETE).')
            if nudged_task_id != current.id:
                if _task_is_summarize_only(current.description):
                    conversation.append({'role': 'user', 'content': 'Summarize using the names already shown in Recent tool results above. Do not call summarize_file for every file unless the task asks to read contents. Do not print fake tool JSON in text. End the message with TASK_COMPLETE, TASK COMPLETE, or TASKCOMPLETE on its own last line.'})
                    logger.info('Inserted one-time summarize reminder for task %s', current.id)
                elif _task_looks_like_file_work(current.description):
                    conversation.append({'role': 'user', 'content': "Reminder: this step must use a file tool (write_file, read_file, or list_files) with real paths. Do not reply with only text, UUIDs, or 'next action'. Call the tool now."})
                    logger.info('Inserted one-time tool reminder for task %s', current.id)
                nudged_task_id = current.id
        if steps >= cfg.max_steps:
            logger.warning('max_steps reached')
            last_text = 'Stopped: max_steps reached.'
            break
    if task_memory.all_done():
        logger.info('All tasks completed.')
        return last_text or 'All tasks completed.'
    return last_text or 'Agent loop ended.'
