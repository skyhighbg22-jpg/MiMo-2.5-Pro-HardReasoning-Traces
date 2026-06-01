import json, ssl, urllib.request, time

API_URL = "https://token-plan-sgp.xiaomimimo.com/v1/chat/completions"
API_KEY = "tp-sou9oupysvtbeqkup8w4gmofoes888teci3waykpy1cqc8un"
ssl_context = ssl._create_unverified_context()

headers = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}
data = {
    "model": "mimo-v2.5-pro",
    "messages": [{"role": "user", "content": "What is 2+2? Answer briefly."}],
    "temperature": 0.7,
    "max_tokens": 100
}

req_body = json.dumps(data).encode("utf-8")
req = urllib.request.Request(API_URL, data=req_body, headers=headers, method="POST")

print("Testing API connectivity...")
start = time.time()
try:
    with urllib.request.urlopen(req, context=ssl_context, timeout=30) as resp:
        body = resp.read().decode("utf-8")
        result = json.loads(body)
        print(f"SUCCESS in {time.time()-start:.1f}s")
        print(f"Answer: {result['choices'][0]['message']['content'][:100]}")
except Exception as e:
    print(f"FAILED in {time.time()-start:.1f}s: {e}")
