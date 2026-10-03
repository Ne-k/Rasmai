from unittest.mock import patch


def stub_get(module, handler):
    """Context manager: ``module.requests.get`` is ``handler`` inside the block and whatever it was after."""
    return patch.object(module.requests, "get", handler)
