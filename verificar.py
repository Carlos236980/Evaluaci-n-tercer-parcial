import json, urllib.request, urllib.error, http.cookiejar
def client():
    jar=http.cookiejar.CookieJar()
    session=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    def call(path, data=None, status=200):
        request=urllib.request.Request('http://127.0.0.1:8000/api/'+path,data=None if data is None else json.dumps(data).encode(),headers={'Content-Type':'application/json'})
        try:
            response=session.open(request)
        except urllib.error.HTTPError as e:
            response=e
        assert response.code==status,(path,response.code,response.read())
        return json.load(response) if path!='report' else response.read().decode('utf-8-sig')
    return call
a,t,g=client(),client(),client()
for c,n in zip((a,t,g),('admin','tecnico','gerente')):
    c('login',dict(name=n,password='Demo2026!'))
stock=lambda: next(p['qty'] for p in g('state')['parts'] if p['code']=='P001')
assert len(a('state')['parts'])==24 and stock()==12
a('part',dict(code='P025',name='Prueba',category='Control',location='B-06',minimum=1,qty=3))
a('part',dict(code='P025',name='Pieza editada',category='Control',location='B-07',minimum=1,editing=True))
assert any(p['name']=='Pieza editada' for p in a('state')['parts'])
a('archive',dict(code='P025'))
assert len(a('state')['parts'])==24
a('user',dict(name='auxiliar',password='Prueba2026!',role='Técnico',active=1))
a('user',dict(name='auxiliar',password='',role='Técnico',active=0))
client()('login',dict(name='auxiliar',password='Prueba2026!'),401)
t('stock',dict(code='P001',qty=2,reason='Compra'),403)
a('stock',dict(code='P001',qty=2,reason='Compra'))
for qty in (6,1,10):
    t('request',dict(code='P001',qty=qty,reason='Mantenimiento'))
assert stock()==14
g('review',dict(id=1,status='Aprobada'))
g('review',dict(id=2,status='Rechazada'))
g('review',dict(id=3,status='Aprobada'),400)
g('review',dict(id=1,status='Aprobada'),400)
assert stock()==8
assert [r['status'] for r in t('state')['requests']]==['Pendiente','Rechazada','Aprobada']
assert [m['delta'] for m in g('state')['moves'] if m['code']=='P001']==[-6,2,12]
assert 'P001,Rodamiento 6205,Transmisión,8' in g('report')
print('Pruebas HTTP completadas')
