import requests, time
url = 'http://127.0.0.1:8000/api/hotspots?category=ai'
# check initial state
r = requests.get('http://127.0.0.1:8000/api/health', timeout=5)
d = r.json()
print('initial list cache:', d['components']['cache']['list'])
print()

# Now do 5 sequential requests
for i in range(5):
    t0 = time.time()
    r = requests.get(url, timeout=10)
    dt = (time.time() - t0) * 1000
    d = requests.get('http://127.0.0.1:8000/api/health', timeout=5).json()
    lc = d['components']['cache']['list']
    print('req', i, ':', round(dt,0), 'ms | cache: hits=', lc['hits'], 'misses=', lc['misses'], 'invalidations=', lc['invalidations'])
