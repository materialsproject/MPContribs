"""
@api {post} /query?API_KEY=:api_key Query contributions
@apiVersion 0.0.0
@apiName PostQueryContributions
@apiGroup Contribution

@apiDescription Query the contributions, materials, or compositions
collections given specific criteria and projection

@apiParam {String} api_key User's unique API_KEY
@apiParam {String} collection Collection to run query against
('contributions', 'materials', or 'compositions')

@apiParamExample {json} Request-Example:
    { "collection": "materials" }

@apiSuccess {String} created_at Response timestamp
@apiSuccess {Bool} valid_response Response is valid
@apiSuccess {Object[]} response List of shortened contribution docs (defined
as follows) if collection == 'contributions' else list of materials or
compositions docs (limited to one doc)
@apiSuccess {String} response._id Contribution identifier
@apiSuccess {String[]} response.collaborators List of collaborators
@apiSuccess {String} response.mp_cat_id MP category identifier (mp-id or
composition)

@apiSuccessExample Success-Response:
    HTTP/1.1 200 OK
    {
        "created_at": "2016-05-20T16:15:26.909038",
        "valid_response": true,
        "response": [
            {
                "_id": "57336b0137202d12f6d50b37",
                "collaborators": ["Patrick Huck"],
                "mp_cat_id": "mp-134"
            }, {
                "_id": "5733704637202d12f448fc59",
                "collaborators": ["Patrick Huck"],
                "mp_cat_id": "mp-30"
            }
        ]
    }
"""

