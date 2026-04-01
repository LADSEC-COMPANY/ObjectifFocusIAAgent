from __future__ import annotations
import json
import logging
import re
from typing import Any
from .llm_client import OllamaClient
from .task_manager import TaskMemory
logger = logging.getLogger(__name__)
PLANNER_SYSTEM = 'You are a planning assistant. Given a user goal, break it into a small ordered list of concrete tasks.\nRespond with ONLY valid JSON (no markdown fences, no commentary) in this exact shape:\n{"tasks": [{"description": "string"}, ...]}\nUse 3 to 12 tasks unless the goal is trivial (then 1-2). Each description must be actionable.\n\nCritical constraint: the executor has ONLY these capabilities: read/write/list text files and summarize files on disk.\nIt cannot run shell commands: never mention `dir`, `ls`, `cmd`, or `powershell` in a task — those will not run.\nTo list a folder, say "List files in <path> using list_files" only.\nIt cannot open File Explorer, click the mouse, drive the GUI, or run other shell commands. Do NOT plan tasks that require\nthe Windows/macOS desktop UI (e.g. "Open File Explorer", "right-click", "press Enter in a dialog"). Instead plan\nfilesystem steps only: e.g. list a folder, create or edit a file at a path, read back to verify.\n\nWhen the user only wants to see what is in a folder (list files, show directory contents, "what files are in X"):\nuse at most 2 tasks: (1) list that directory with the list_files tool (describe it as "List files in <path> using list_files"),\n(2) optionally summarize the listing. Do NOT plan "read all files into memory" or "load every file" for a simple listing goal —\nthat is slower and unnecessary; listing the directory is enough unless the user explicitly asked to read file contents.\n\nPrefer one task per real file operation. Do NOT split into "create empty file", "open in editor", "save" — those are\nnot separate tool steps. Use a single task like "Write the resume text to D:/Test/Resume.txt using the file tools"\n(or list then write).\n\nPaths: ONLY use directories and files explicitly mentioned in the user\'s goal. Do NOT invent paths such as\nC:\\Users\\User\\Desktop, generic "Desktop", or placeholder usernames — the agent runs as the real user and those\npaths are often wrong. If the goal says D:\\Test, stay under D:\\Test. To "copy" a file, plan as read source then\nwrite destination (or one task: write template content to the target path). Do not add unrelated steps (e.g. listing\nDesktop) unless the goal asks for it.\n\nJSON rules: double quotes for strings only. Do not use backslash before apostrophes (write Doesn\'t not Doesn\\\'t).\nWindows paths inside strings must use doubled backslashes (e.g. D:\\\\folder) or forward slashes (D:/folder).'
#this is the system prompt for the planner, it is used to plan the tasks

#this is the function that will be used to repair the json from the text
def _repair_llm_json(text: str) -> str:
    text = text.replace("\\'", "'")
    return text
#this is the function that will be used to extract the json from the text
def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    fence = re.match('^```(?:json)?\\s*([\\s\\S]*?)\\s*```$', text, re.IGNORECASE)
    if fence:
        text = fence.group(1).strip()
    text = _repair_llm_json(text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find('{')
        end = text.rfind('}')
        if start >= 0 and end > start:
            return json.loads(text[start:end + 1])
        raise
#this is the function that will be used to plan the tasks
def plan_tasks(client: OllamaClient, goal: str, task_memory: TaskMemory, model: str | None=None) -> list[str]:
    user_msg = f'Goal:\n{goal.strip()}\n\nProduce the JSON plan.'
    messages = [{'role': 'system', 'content': PLANNER_SYSTEM}, {'role': 'user', 'content': user_msg}]
    logger.info('Planning for goal: %s', goal[:200] + ('...' if len(goal) > 200 else ''))
    resp = client.chat(messages, tools=None, model=model)
    content = resp.message.content or ''
    try:
        data = _extract_json(content)
    except (json.JSONDecodeError, TypeError) as e:
        logger.error('Planner returned non-JSON: %s', content[:500])
        raise ValueError(f'Planner did not return valid JSON: {e}') from e
    raw_tasks = data.get('tasks')
    if not isinstance(raw_tasks, list) or not raw_tasks:
        raise ValueError("Planner JSON must contain a non-empty 'tasks' array")
    descriptions: list[str] = []
    task_memory.clear_tasks()
    task_memory.set_goal(goal)
    for item in raw_tasks:
        if isinstance(item, str):
            desc = item.strip()
        elif isinstance(item, dict) and 'description' in item:
            desc = str(item['description']).strip()
        else:
            continue
        if desc:
            task_memory.add_task(desc)
            descriptions.append(desc)
    if not descriptions:
        raise ValueError('No valid task descriptions in planner output')
    task_memory.persist()
    logger.info('Plan created with %d tasks', len(descriptions))
    return descriptions
