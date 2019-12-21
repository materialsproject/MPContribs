import sys
from test_site.wsgi import application as portal_app
from hendrix.deploy.base import HendrixDeploy
from twisted.logger import globalLogPublisher, LogLevel
from hendrix.logger import hendrixObserver
from hendrix.experience import hey_joe

globalLogPublisher.addObserver(hendrixObserver(path='/app/hendrix.log', log_level=LogLevel.info))
deployer = HendrixDeploy(options={'wsgi': portal_app, 'http_port': 8080})# TODO 'workers': 2
ws_service = hey_joe.WebSocketService('localhost', 9000)
deployer.add_non_tls_websocket_service(ws_service)
deployer.run()
