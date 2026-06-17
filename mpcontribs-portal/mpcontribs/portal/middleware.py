class MyMiddleware:

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        response['X-Consumer-Id'] = request.META.get("HTTP_X_CONSUMER_ID")
        return response
