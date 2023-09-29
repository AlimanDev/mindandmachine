from rest_framework import status
from requests.exceptions import HTTPError

class MockResponse:
    """`requests` library `Response` mock"""
    def __init__(self, status_code: int, json_data: dict = {}):
        self.status_code = status_code
        self.json_data = json_data

    def json(self) -> dict:
        return self.json_data

    def raise_for_status(self):
        if not status.is_success(self.status_code):
            raise HTTPError('Some errror', response=self)

def mock_request(status_code: int, json_data: dict = {}):
    """
    Returns a 'mock' function, not the actual response.
    Example: `@mock.patch.object(requests, 'request', mock_request(status_code=200, json_data={'message': 'ok'}))`
    """
    return lambda *_, **__: MockResponse(status_code, json_data)
