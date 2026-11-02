import socket
import ssl
import urllib.error

import pytest
from ragsystem.domain.errors import EngineError
from ragsystem.models.network_provider import NetworkProvider


def provider():
    return NetworkProvider({'id':'test', 'name':'test', 'kind':'api', 'revision':1,
                            'base_url':'https://api.deepseek.com/v1', 'model':'deepseek-flash'}, 'fixture-not-a-key')


@pytest.mark.parametrize('reason,code', [
    (ssl.SSLCertVerificationError('fixture'), 'PROVIDER_TLS_FAILED'),
    (socket.gaierror('fixture'), 'PROVIDER_DNS_FAILED'),
    (TimeoutError(), 'PROVIDER_TIMEOUT'),
    (ConnectionRefusedError(), 'PROVIDER_UNAVAILABLE'),
])
def test_transport_errors_are_actionable_and_do_not_reveal_remote_data(reason, code):
    p=provider()
    def fail(*args, **kwargs):
        raise urllib.error.URLError(reason)
    p._opener.open=fail
    with pytest.raises(EngineError, match=code):
        p.models()


def test_deepseek_bounded_json_disables_implicit_reasoning_and_detects_truncation():
    p=provider()
    def respond(path, body):
        assert body['thinking'] == {'type':'disabled'}
        assert body['max_tokens'] == 900
        return {'choices':[{'finish_reason':'length','message':{'content':'{"claims":['}}]}
    p.request=respond
    with pytest.raises(EngineError, match='MODEL_OUTPUT_TRUNCATED'):
        p.generate('answer', {'question':'test', 'chunks':[]})
