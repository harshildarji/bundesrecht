import pytest


def pytest_addoption(parser):
    parser.addoption("--jsonl", action="store", default="data/gesetze.jsonl")
