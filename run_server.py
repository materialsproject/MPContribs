import sys
from test_site.wsgi import application as portal_app
from hendrix.deploy.base import HendrixDeploy
from twisted.logger import globalLogPublisher, eventAsText, FileLogObserver
from hendrix.logger import hendrixObserver
from hendrix.experience import hey_joe

globalLogPublisher.addObserver(FileLogObserver(sys.stdout, lambda e: eventAsText(e) + "\n"))
deployer = HendrixDeploy(options={'wsgi': portal_app, 'http_port': 8080, 'global-cache': True})
ws_service = hey_joe.WebSocketService('localhost', 9000)
deployer.add_non_tls_websocket_service(ws_service)
deployer.run()
