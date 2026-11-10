import json
for name in ['math','soc','info']:
    data = json.load(open(name+'.json',encoding='utf-8'))
    out = {
        'plan': data['plan'],
        'routine': data['routine'],
        'video': data['video']
    }
    js = 'const SUBJECT_DATA = ' + json.dumps(out, ensure_ascii=False) + ';'
    open(name+'.js', 'w', encoding='utf-8').write(js)
    print(name, 'weeks=', len(data['plan']), 'js_len=', len(js))