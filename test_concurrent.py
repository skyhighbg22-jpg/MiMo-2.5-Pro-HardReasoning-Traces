import json, ssl, urllib.request, time, threading

API_URL = "https://token-plan-sgp.xiaomimimo.com/v1/chat/completions"
API_KEY = "tp-sou9oupysvtbeqkup8w4gmofoes888teci3waykpy1cqc8un"
ssl_context = ssl._create_unverified_context()

def make_req(i, timeout=90):
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    data = {
        "model": "mimo-v2.5-pro",
        "messages": [{"role": "user", "content": f"What is {i}+{i}? Answer briefly."}],
        "temperature": 0.7,
        "max_tokens": 100
    }
    req_body = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(API_URL, data=req_body, headers=headers, method="POST")
    start = time.time()
    try:
        with urllib.request.urlopen(req, context=ssl_context, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            result = json.loads(body)
            print(f"  #{i} SUCCESS in {time.time()-start:.1f}s: {result['choices'][0]['message']['content'][:50]}")
    except Exception as e:
        print(f"  #{i} FAILED in {time.time()-start:.1f}s: {e}")

print("Testing 5 concurrent requests (2s stagger)...")
threads = []
for i in range(5):
    t = threading.Thread(target=make_req, args=(i,))
    threads.append(t)
    t.start()
    time.sleep(2)

for t in threads:
    t.join(timeout=120)

print("Done.")
