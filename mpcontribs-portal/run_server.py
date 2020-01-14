import sys
from wsgi import application as portal_app
from django.conf import settings
from hendrix.deploy.base import HendrixDeploy
from twisted.logger import globalLogPublisher, eventAsText, FileLogObserver
from hendrix.logger import hendrixObserver
from hendrix.experience import hey_joe

globalLogPublisher.addObserver(FileLogObserver(sys.stdout, lambda e: eventAsText(e) + "\n"))
globalLogPublisher.addObserver(FileLogObserver(sys.stderr, lambda e: eventAsText(e) + "\n"))
deployer = HendrixDeploy(options={'wsgi': portal_app, 'http_port': 8080, 'global-cache': True, 'loud': settings.DEBUG})
kwargs = {} if settings.DEBUG else {'externalPort': 80}
ws_service = hey_joe.WebSocketService('localhost', 9000, **kwargs)
deployer.add_non_tls_websocket_service(ws_service)
deployer.run()
