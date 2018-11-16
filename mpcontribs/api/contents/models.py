from flask_restplus import SchemaModel

#### PROJECT-SPECIFIC CONTENT ####

schema_models = [
    SchemaModel('DtuBandgaps', {
        'properties': {
            "direct": {'type': 'string'},
            "indirect": {'type': 'string'},
        }
    }),
    SchemaModel('DtuData', {
        'properties': {
            "C": {'type': 'string'},
            "ΔE-KS": {'$ref': '#/definitions/DtuBandgaps'},
            "ΔE-QP": {'$ref': '#/definitions/DtuBandgaps'},
        }
    })
    #"contributor": {'type': 'string'},
    #"formula": {'type': 'string'},
    #"input_url": {'type': 'string', 'format': 'uri'},
    #"ICSD": {'type': 'string'},
    #"data": {'$ref': '#/definitions/DtuData'},
]
