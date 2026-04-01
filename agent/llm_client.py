from __future__ import annotations
import json
import logging
from dataclasses import dataclass, field
from typing import Any
import httpx
logger = logging.getLogger(__name__)

#prends le body de la réponse httpx.response et le retourne sous forme de string(seulement les 400 premiers caractères)
def _http_error_detail(response: httpx.Response) -> str:
    text = (response.text or '').strip()
    if len(text) > 400:
        text = text[:400] + '...'
    return text or '(empty body)'

#prends le body sous forme de json et retourne le champ error si il existe
def _ollama_error_field(response: httpx.Response) -> str | None:
    try:
        data = response.json()
        err = data.get('error')
        if isinstance(err, str) and err.strip():
            return err.strip()
    except (json.JSONDecodeError, ValueError, TypeError):
        pass
    return None

#liste les models installés sur l'url donnée,récupére le champ models et retourne la liste des noms des models
def list_installed_models(base_url: str, timeout: float=10.0) -> list[str]:
    base = base_url.rstrip('/')
    url = f'{base}/api/tags'
    with httpx.Client(timeout=timeout) as client:
        r = client.get(url)
    r.raise_for_status()
    data = r.json()
    models = data.get('models') or []
    names: list[str] = []
    for m in models:
        if isinstance(m, dict) and isinstance(m.get('name'), str):
            names.append(m['name'])
    return names

#vérifie si l'url donnée est un server ollama, si non, renvoie une erreur
def check_ollama_server(base_url: str, timeout: float=10.0) -> None:
    base = base_url.rstrip('/')
    tags_url = f'{base}/api/tags'
    try:
        with httpx.Client(timeout=timeout) as client:
            r = client.get(tags_url)
    except httpx.ConnectError as e:
        raise RuntimeError(f'Cannot connect to Ollama at {base}. Start the Ollama application (or run `ollama serve` in a terminal), then retry. Original error: {e}') from e
    except httpx.TimeoutException as e:
        raise RuntimeError(f'Timeout reaching Ollama at {tags_url}: {e}') from e
    if r.status_code == 200:
        return
    detail = _http_error_detail(r)
    if r.status_code == 404:
        raise RuntimeError(f'No Ollama API at {tags_url} (404). Something on this port is not Ollama, or the base URL is wrong. Fix: install/start Ollama from https://ollama.com and ensure it listens on the same host/port you pass with --ollama (default http://127.0.0.1:11434). In PowerShell try: Invoke-WebRequest {tags_url} -UseBasicParsing\nResponse: {detail}') from None
    raise RuntimeError(f'Could not reach Ollama at {tags_url}: HTTP {r.status_code}. {detail}') from None
 
@dataclass
 #this is the message from the agent loop to the ollama api, it used to send the message to the ollama api
class ChatMessage:
    role: str
    content: str | None = None
    tool_calls: list[dict[str, Any]] | None = None
    name: str | None = None

    def to_api_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {'role': self.role}
        if self.content is not None:
            d['content'] = self.content
        if self.tool_calls is not None:
            d['tool_calls'] = self.tool_calls
        if self.name is not None:
            d['name'] = self.name
        return d

@dataclass
#this is the response from the ollama api to the agent loop, it used to get the message from the ollama api
class LLMResponse:
    message: ChatMessage
    model: str
    done: bool = True
    raw: dict[str, Any] = field(default_factory=dict)


def _normalize_message_for_ollama(msg: dict[str, Any]) -> dict[str, Any]:
    """Ollama rejects history when tool_calls.function.arguments are JSON strings; it expects an object."""
    m = dict(msg)
    if m.get('role') != 'assistant' or not m.get('tool_calls'):
        return m
    tcs: list[dict[str, Any]] = []
    for tc in m['tool_calls']:
        tc = dict(tc)
        fn = tc.get('function')
        if isinstance(fn, dict):
            fn = dict(fn)
            raw = fn.get('arguments')
            if isinstance(raw, str):
                try:
                    fn['arguments'] = json.loads(raw) if raw.strip() else {}
                except json.JSONDecodeError:
                    logger.warning('Could not parse tool arguments for Ollama; using {}. Snippet: %s', raw[:200])
                    fn['arguments'] = {}
            elif raw is None:
                fn['arguments'] = {}
            tc['function'] = fn
        tcs.append(tc)
    m['tool_calls'] = tcs
    if m.get('content') == '':
        m.pop('content', None)
    return m


def _ollama_http_timeout(read_seconds: float) -> httpx.Timeout:
    """Long read for LLM generation; bounded connect/pool so dead servers fail fast."""
    rs = max(1.0, float(read_seconds))
    return httpx.Timeout(connect=30.0, read=rs, write=max(60.0, rs), pool=30.0)


#this is the client that will be used to send the message to the ollama api
class OllamaClient:
 #this is the constructor of the OllamaClient, it will be used to create the client
    def __init__(self, base_url: str='http://127.0.0.1:11434', model: str='mistral:latest', timeout: float=600.0, num_predict: int=4096) -> None:
        self.base_url = base_url.rstrip('/')
        self.model = model
        self.timeout = timeout
        self.num_predict = max(256, int(num_predict))
 #this is the function that will be used to send the message to the ollama api
    def chat(self, messages: list[dict[str, Any] | ChatMessage], tools: list[dict[str, Any]] | None=None, model: str | None=None, options: dict[str, Any] | None=None) -> LLMResponse:
        use_model = model or self.model
        payload: dict[str, Any] = {'model': use_model, 'messages': self._serialize_messages(messages), 'stream': False}
        o: dict[str, Any] = {'num_predict': self.num_predict}
        if options:
            o.update(options)
        payload['options'] = o
        if tools:
            payload['tools'] = tools
        url = f'{self.base_url}/api/chat'
        logger.info(
            'Ollama request: POST %s model=%s messages=%d tools=%s — blocking until the model responds (slow on CPU or first load)',
            url,
            use_model,
            len(messages),
            bool(tools),
        )
        try:
            with httpx.Client(timeout=_ollama_http_timeout(self.timeout)) as client:
                r = client.post(url, json=payload)
                try:
                    r.raise_for_status()
                except httpx.HTTPStatusError as e:
                    detail = _http_error_detail(e.response)
                    ollama_err = _ollama_error_field(e.response)
                    if ollama_err and 'model' in ollama_err.lower() and ('not found' in ollama_err.lower()):
                        try:
                            installed = list_installed_models(self.base_url, timeout=min(self.timeout, 30.0))
                            avail = ', '.join(installed[:12]) if installed else '(none returned)'
                        except Exception:
                            avail = 'run: ollama list'
                        raise RuntimeError(f'{ollama_err} Use a model you have installed, e.g. python -m agent "..." --model mistral:latest or pull this one: ollama pull {use_model!r}. Currently installed (from /api/tags): {avail}') from e
                    if e.response.status_code == 404:
                        raise RuntimeError(f"POST {url} returned 404. If the body is not a 'model not found' error, the chat API may be missing (wrong server or very old Ollama). Wrong --ollama base URL? Use the root only, e.g. http://127.0.0.1:11434. Response: {detail}") from e
                    raise RuntimeError(f'POST {url} failed: HTTP {e.response.status_code}. {detail}') from e
                data = r.json()
        except httpx.TimeoutException as e:
            raise RuntimeError(
                f'Ollama did not respond in time (read timeout {self.timeout:g}s while waiting for /api/chat). '
                f'Cold starts often load the model for several minutes. Retry, or raise the limit: '
                f'python -m agent "..." --timeout 1200'
            ) from e
        msg_raw = data.get('message') or {}
        tool_calls = msg_raw.get('tool_calls')
        content = msg_raw.get('content')
        message = ChatMessage(role=msg_raw.get('role', 'assistant'), content=content if content else None, tool_calls=tool_calls if tool_calls else None)
        return LLMResponse(message=message, model=data.get('model', use_model), done=data.get('done', True), raw=data)

    @staticmethod
    def _serialize_messages(messages: list[dict[str, Any] | ChatMessage]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for m in messages:
            if isinstance(m, ChatMessage):
                d = m.to_api_dict()
            else:
                d = dict(m)
            if d.get('role') == 'assistant' and d.get('tool_calls'):
                d = _normalize_message_for_ollama(d)
            out.append(d)
        return out

    @staticmethod
    def tool_call_arguments(tool_call: dict[str, Any]) -> dict[str, Any]:
        fn = tool_call.get('function') or {}
        raw_args = fn.get('arguments')
        if raw_args is None:
            return {}
        if isinstance(raw_args, dict):
            return raw_args
        if isinstance(raw_args, str):
            try:
                return json.loads(raw_args) if raw_args.strip() else {}
            except json.JSONDecodeError:
                logger.warning('Invalid JSON in tool arguments: %s', raw_args[:200])
                return {}
        return {}
