"""Fictional evaluator oracles; no human gold or quality acceptance."""
import importlib.util
from pathlib import Path

from ragsystem.retrieval.evaluation import ranking_metrics


def evaluator():
    spec = importlib.util.spec_from_file_location('audit_evaluator', Path(__file__).resolve().parents[2]/'tools/evaluate_scientific_quality.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_precision_requires_returned_judgments_and_does_not_credit_duplicates():
    value = ranking_metrics({'a': 1, 'b': 0}, ['a', 'a', 'b'])
    assert value['precision_at_5'] == 0.2
    assert value['precision_at_10'] == 0.1
    assert ranking_metrics({'a': 1}, ['a', 'unknown'])['precision_at_5'] is None


def test_all_call_cost_accounting_and_no_fake_zero_for_missing_usage():
    module = evaluator()
    calls = [{'role': role, 'input_tokens': 10, 'output_tokens': 3, 'cost': 0.02, 'currency': 'USD'} for role in ['answer', 'support', 'relevance']]
    result = module.call_accounting({'calls_complete': True, 'model_calls': calls})
    assert result['calls'] == 3 and result['input_tokens'] == 30 and result['output_tokens'] == 9
    assert result['cost_by_currency'] == {'USD': 0.06}
    assert module.call_accounting({}) is None
    assert module.call_accounting({'calls_complete': True, 'model_calls': []})['calls'] == 0
    calls[1]['input_tokens'] = None
    assert module.call_accounting({'calls_complete': True, 'model_calls': calls}) is None
