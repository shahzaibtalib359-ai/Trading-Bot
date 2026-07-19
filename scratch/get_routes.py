import json
data = json.load(open('openapi_dump.json'))
for path in data['paths']:
    methods = list(data['paths'][path].keys())
    print(f"{','.join(methods).upper():10} {path}")
