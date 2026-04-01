from __future__ import annotations
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any
from tools.list_files import list_files as list_files_fn
from tools.read_file import read_file as read_file_fn
from tools.summarize_file import summarize_file as summarize_file_fn
from tools.write_file import write_file as write_file_fn
logger = logging.getLogger(__name__)
 
ToolFunc = Callable[..., dict[str, Any]]
#this is the function that will be used to create the tool

def _ollama_tool(name: str, description: str, parameters: dict[str, Any]) -> dict[str, Any]:
    return {'type': 'function', 'function': {'name': name, 'description': description, 'parameters': parameters}}

READ_FILE_TOOL = _ollama_tool('read_file', 'Read the full or partial text content of a file.', {'type': 'object', 'properties': {'path': {'type': 'string', 'description': 'Path to the file'}, 'encoding': {'type': 'string', 'description': 'Text encoding', 'default': 'utf-8'}, 'max_chars': {'type': 'integer', 'description': 'Optional max characters to read (truncates large files)'}}, 'required': ['path']})
WRITE_FILE_TOOL = _ollama_tool('write_file', 'Write text content to a file (creates parent directories by default). Use path+content, OR directory+file+content if splitting folder and filename is easier.', {'type': 'object', 'properties': {'path': {'type': 'string', 'description': 'Full destination path (preferred)'}, 'directory': {'type': 'string', 'description': 'Folder only; combine with file if path is not used'}, 'file': {'type': 'string', 'description': 'Filename only; combine with directory if path is not used'}, 'content': {'type': 'string', 'description': 'Full text to write'}, 'encoding': {'type': 'string', 'default': 'utf-8'}, 'create_parents': {'type': 'boolean', 'default': True}}, 'required': ['content']})
LIST_FILES_TOOL = _ollama_tool('list_files', 'List files in a directory matching an optional glob pattern.', {'type': 'object', 'properties': {'directory': {'type': 'string', 'description': 'Directory to list', 'default': '.'}, 'pattern': {'type': 'string', 'default': '*'}, 'recursive': {'type': 'boolean', 'default': False}, 'include_hidden': {'type': 'boolean', 'default': False}}, 'required': []})
SUMMARIZE_FILE_TOOL = _ollama_tool('summarize_file', 'Get a compact summary of a text file: size, counts, and preview.', {'type': 'object', 'properties': {'path': {'type': 'string', 'description': 'Path to the file'}, 'encoding': {'type': 'string', 'default': 'utf-8'}, 'preview_chars': {'type': 'integer', 'default': 2000}}, 'required': ['path']})

def _normalize_write_file_args(arguments: dict[str, Any]) -> dict[str, Any]:
    path = arguments.get('path')
    if not path:
        d = arguments.get('directory') or arguments.get('folder') or arguments.get('dir')
        f = arguments.get('file') or arguments.get('filename') or arguments.get('basename')
        if d is not None and f is not None and str(f).strip():
            path = str(Path(str(d)) / str(f))
    if not path:
        path = arguments.get('filepath') or arguments.get('destination')
    content = arguments.get('content')
    if content is None:
        content = ''
    elif not isinstance(content, str):
        content = str(content)
    return {'path': path or '', 'content': content, 'encoding': arguments.get('encoding', 'utf-8'), 'create_parents': arguments.get('create_parents', True)}

def _resolve_path_argument(arguments: dict[str, Any]) -> str:
    path = arguments.get('path')
    if path:
        return str(path).strip()
    for k in ('filepath', 'file', 'filename', 'directory'):
        v = arguments.get(k)
        if v:
            return str(v).strip()
    return ''

class ToolRegistry:

    def __init__(self) -> None:
        self._defs: list[dict[str, Any]] = []
        self._impl: dict[str, ToolFunc] = {}

    def register(self, definition: dict[str, Any], fn: ToolFunc) -> None:
        name = definition['function']['name']
        self._defs.append(definition)
        self._impl[name] = fn
        logger.debug('Registered tool: %s', name)

    def definitions(self) -> list[dict[str, Any]]:
        return list(self._defs)

    def execute(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if name not in self._impl:
            return {'success': False, 'error': f'Unknown tool: {name}'}
        fn = self._impl[name]
        if name == 'write_file':
            arguments = _normalize_write_file_args(arguments)
            if not arguments['path']:
                return {'success': False, 'error': 'write_file needs path, or directory+file, to know where to write.'}
        if name == 'read_file':
            path = _resolve_path_argument(arguments)
            if not path:
                return {'success': False, 'error': 'read_file needs path (models sometimes send filepath, file, or directory as the key).'}
            arguments = {'path': path, 'encoding': arguments.get('encoding', 'utf-8'), 'max_chars': arguments.get('max_chars')}
        if name == 'summarize_file':
            path = _resolve_path_argument(arguments)
            if not path:
                return {'success': False, 'error': 'summarize_file needs path.'}
            arguments = {'path': path, 'encoding': arguments.get('encoding', 'utf-8'), 'preview_chars': arguments.get('preview_chars', 2000)}
        try:
            return fn(**arguments)
        except TypeError as e:
            logger.exception('Bad arguments for %s: %s', name, arguments)
            return {'success': False, 'error': f'Invalid arguments for {name}: {e}'}
        except Exception as e:
            logger.exception('Tool %s failed', name)
            return {'success': False, 'error': str(e)}

def default_registry() -> ToolRegistry:
    reg = ToolRegistry()
    reg.register(READ_FILE_TOOL, read_file_fn)
    reg.register(WRITE_FILE_TOOL, write_file_fn)
    reg.register(LIST_FILES_TOOL, list_files_fn)
    reg.register(SUMMARIZE_FILE_TOOL, summarize_file_fn)
    return reg
