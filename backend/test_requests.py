import httpx
import json

url = 'http://127.0.0.1:8000'
client = httpx.Client(timeout=10.0)
req = {"query": "What is the refund policy?", "context": "This is a long context. " * 50, "token_budget": 150}

def pretty(resp):
    try:
        return json.dumps(resp.json(), indent=2)
    except Exception:
        return resp.text

print('POST /analyze')
resp = client.post(url + '/analyze', json=req)
print(resp.status_code)
print(pretty(resp))

print('\nPOST /optimize')
resp = client.post(url + '/optimize', json={**req, 'simulate_tier2_failure': False})
print(resp.status_code)
print(pretty(resp)[:2000])

print('\nPOST /optimize-and-answer')
resp = client.post(url + '/optimize-and-answer', json={**req, 'simulate_tier2_failure': False})
print(resp.status_code)
print(pretty(resp)[:2000])
