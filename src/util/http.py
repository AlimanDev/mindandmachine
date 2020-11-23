from requests import Session
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry


def make_retry_session(total_retires=5, backoff_factor=0.1, status_forcelist=None):
    if status_forcelist is None:
        status_forcelist = (502, 503, 504)

    session = Session()
    retry = Retry(
        total=total_retires,
        backoff_factor=backoff_factor,  # sleep time = [0.0; 0.2; 0.4; 0.8; 1.6;] (for 0.1)
        status_forcelist=status_forcelist,
        method_whitelist=['GET', 'POST']
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount('http://', adapter)
    session.mount('https://', adapter)

    return session
