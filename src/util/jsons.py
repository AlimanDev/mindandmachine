import json

def process_single_quote_json(s: str) -> dict:
    s = s.replace("\'", "\"")
    return json.loads(s)