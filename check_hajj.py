import sys
sys.stdout.reconfigure(encoding='utf-8')
import json

data = json.load(open('data/fatwas.json', encoding='utf-8'))

hajj_urls = ['136222', '136278', '136215', '39350', '55629']

for d in data:
    url = d.get('url', '')
    if any(h in url for h in hajj_urls):
        content = d.get('content', '')
        print(f"URL: {url}")
        print(f"Title: {d.get('title', '')}")
        print(f"Content length: {len(content)}")
        # Look for the key word شروط
        if 'شروط' in content:
            idx = content.index('شروط')
            print(f"Found 'شروط' at index {idx}")
            print(f"Context: ...{content[max(0,idx-50):idx+300]}...")
        else:
            print("WARNING: 'شروط' NOT FOUND in content!")
        print(f"First 200 chars: {content[:200]}")
        print("---")
