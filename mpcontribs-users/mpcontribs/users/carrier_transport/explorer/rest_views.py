def index(request, cid=None, db_type=None, mdb=None):
    try:
        response = None
        if request.method == 'GET':
            axes, dopings = ['<S>', '<σ>', '<S²σ>'], ['n', 'p']
            projection = dict(('content.data.{}'.format(k[1:-1]), 1) for k in axes)
            projection.update({'identifier': 1})
            docs = mdb.contrib_ad.query_contributions(
                {'project': 'carrier_transport'}, projection=projection
            )
            response = {'text': []}
            response.update(dict((k, []) for k in axes))
            for doc in docs:
                d = doc['content']['data']
                for doping in dopings:
                    for idx, k in enumerate(axes):
                        kk = k[1:-1]
                        if kk in d and doping in d[kk]:
                            value = d[kk][doping]['<ε>']
                            value = float(value.split()[0])
                            if idx == 2:
                                value = math.log10(value)
                            response['text'].append(doc['identifier'])
                            response[k].append(value)

        elif request.method == 'POST':
            name = json.loads(request.body)['name']
            names = name.split('##')
            key, subkey = names[0][1:-1], names[1][0]
            table_name = '{}({})'.format(key, subkey)
            doc = mdb.contrib_ad.query_contributions(
                {'_id': cid}, projection={
                    '_id': 0, 'content.{}'.format(table_name): 1,
                    'content.data.{}.{}'.format(key, subkey): 1
                }
            )[0]
            table = doc['content'].get(table_name)
            if table:
                table = Table.from_dict(table)
                x = [col.split()[0] for col in table.columns[1:]]
                y = list(table[table.columns[0]])
                z = table[table.columns[1:]].values.tolist()
                if not table_name.startswith('S'):
                    z = [[math.log10(float(c)) for c in r] for r in z]
                title = ' '.join([table_name, names[1].split()[-1]])
                response = {'x': x, 'y': y, 'z': z, 'type': 'heatmap', 'colorbar': {'title': title}}
    except Exception as ex:
        raise ValueError('"REST Error: "{}"'.format(str(ex)))
    return {"valid_response": True, 'response': response}

def eigenvalues(request, cid, db_type=None, mdb=None):
    doc = mdb.contrib_ad.query_contributions(
        {'_id': cid}, projection={'_id': 0, 'content.data': 1}
    )[0]
    response = {}
    for key, value in doc['content']['data'].iteritems():
        if key != 'S²σ':
            response[key] = {}
            if isinstance(value, dict):
                for doping, dct in value.iteritems():
                    response[key][doping] = {}
                    for eig_key, eig in dct.iteritems():
                        if eig_key != '<ε>':
                            response[key][doping][eig_key] = eig
            else:
                response[key] = value
    return response
