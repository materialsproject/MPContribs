import sys
from wsgi import application as portal_app
from django.conf import settings
from hendrix.deploy.base import HendrixDeploy
from twisted.logger import globalLogPublisher, eventAsText, FileLogObserver

globalLogPublisher.addObserver(FileLogObserver(sys.stdout, lambda e: eventAsText(e) + "\n"))
globalLogPublisher.addObserver(FileLogObserver(sys.stderr, lambda e: eventAsText(e) + "\n"))
deployer = HendrixDeploy(options={
    'wsgi': portal_app, 'http_port': 8765, 'cache_port': 8080,
    'global_cache': True, 'loud': settings.DEBUG, 'cache': True
})
kwargs = {} if settings.DEBUG else {'externalPort': 80}
deployer.run()
