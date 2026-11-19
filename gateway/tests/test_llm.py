import json

import httpx
import pytest

from app.llm import OllamaTranslator, TranslatorError

DEV = ["pump-01"]


def translator_returning(content, status=200):
    def handler(request: httpx.Request):
        body = json.loads(request.content)
        assert body["format"]["properties"]["intent"]["enum"]   # ส่ง JSON schema ไปด้วย
        assert body["options"]["temperature"] == 0
        return httpx.Response(status, json={"message": {"content": content}})
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return OllamaTranslator("http://ollama", "gemma3:1b", 5, client=client)


def test_valid_ai_answer():
    t = translator_returning('{"intent":"maintenance","device_id":"pump-01","minutes":60,"level":null}')
    c = t.translate("ซ่อม 1 ชม", DEV)
    assert (c.intent, c.device_id, c.minutes) == ("maintenance", "pump-01", 60)


def test_unknown_device_from_ai_is_dropped():
    t = translator_returning('{"intent":"status","device_id":"boiler-9","minutes":null,"level":null}')
    assert t.translate("boiler", DEV).device_id is None


@pytest.mark.parametrize("content", [
    '{"intent":"shutdown_factory","device_id":null,"minutes":null,"level":null}',
    '{"intent":"maintenance","device_id":null,"minutes":9999,"level":null}',
    '{"intent":"status","device_id":null,"minutes":null,"level":null,"run_shell":"rm -rf /"}',
    "not json",
    "[]",
])
def test_bad_ai_answers_raise(content):
    with pytest.raises(TranslatorError):
        translator_returning(content).translate("x", DEV)


def test_http_error_raises():
    with pytest.raises(TranslatorError):
        translator_returning("{}", status=500).translate("x", DEV)
