import yaml, pymongo, os, six
from abc import ABCMeta
from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist

class Connections(object):
    """Cache of all DB connections."""
    COUNTS_TIMEOUT = 60 * 60  # refresh counts occasionally
    MAX_POOL = 512            # Max. conn. pool

    def __init__(self):
        self._dbs = {}      # cached DB connections
        self._conns = {}    # cached connections
        self._configs = {}  # cached parsed configs
        self._counts = {}   # cached DB counts

    def from_config(self, config):
        """
        :param config: Unparsed YAML configuration string
        :return: pymongo.Database obj
        """
        db, host, user, password, port, coll = self.split_config(config)
        return self.connection(host, port, db, user, password)

    def connection(self, host, port, db, user, password):
        """MongoDB connection."""
        key = self._get_key(host, port, db)
        if key not in self._dbs:
            c = self._get_connection(host, port)
            if c is None: return None
            # get particular db
            conndb = c[db]
            auth_ok = conndb.authenticate(user, password) if user else True
            if not auth_ok: return None
            self._dbs[key] = conndb
        return self._dbs[key]

    def _get_connection(self, host, port):
        ckey = "{}:{}".format(host, port)
        conn = self._conns.get(ckey, None)
        if conn is None:
            mps = ('max_pool_size' if pymongo.version_tuple[0] == 2
                   else 'maxPoolSize')
            conn = pymongo.MongoClient(host, port, **{mps: self.MAX_POOL})
            self._conns[ckey] = conn
        return conn

    @staticmethod
    def _get_key(host, port, db):
        return "{}:{}/{}".format(host, port, db)

    @staticmethod
    def split_config(config):
        """Split the 'config' object into a set of fields.

        :param config: Configuration
        :type param: dict or str
        :raises: yaml.error.YAMLError if config is a str that doesn't parse
        """
        if not isinstance(config, dict):
            config = yaml.load(config)
        db = config.get("db", None)
        host = config.get("host", "0.0.0.0")
        user_name = config.get("user_name", None)
        password = config.get("password", None)
        port = int(config.get("port", 27017))
        coll = config.get("collection", None)
        return db, host, user_name, password, port, coll

g_connections = Connections()

class ConnectorBase(six.with_metaclass(ABCMeta, object)):
    """database access (overwrite self.connect)"""
    def __init__(self, user=None, **kwargs):
        """
        :param user: Django User object
        """
        PRODUCTION = True if os.environ.get('PRODUCTION') == '1' else False
        self.release = 'dev' if settings.DEBUG else 'prod'
        # replace Django User object with RegisteredUser
        anon_user = False
        try:
            self.user = self.get_registered_user(user)
        except Exception:
            self.user = None
        # Try to access user info. If this fails, set anonymous user.
        try:
            self.username = user.get_username()
        except AttributeError:
            self.user = get_anon_user()
            self.username = 'anonymous'
        # Connect to DBs
        self.connect(**kwargs)

    def get_registered_user(self, user):
        try:
            query = {'username': user.username}
            try:
                from home.models import RegisteredUser
            except ImportError:
                from webtzite.models import RegisteredUser
            ru = RegisteredUser.objects.get(**query)
        except ObjectDoesNotExist:
            raise Exception(
                "Cannot find registered user corresponding "
                "to request user '{}'".format(user.username)
            )
        return ru

    def _get_config(self, db_type):
        """Fetch database configuration.

        :param db_type: Search for this type of database, e.g. 'app'.
        :return: Configuration data, which was stored as a blob in DB
        :rtype: str
        """
        try:
            from home.models import DBConfig
        except ImportError:
            from webtzite.models import DBConfig
        return DBConfig.objects.get(
            release=self.release, db_type=db_type
        ).config

    def get_database(self, name):
        config = self._get_config(name)
        return g_connections.from_config(config)

    def connect(self, **kwargs):
        """Connect to standard set of databases. Optionally override in
        derived class named "Connector" to connect to own databases (mostly
        useful for custom REST interfaces). Define or import "Connector" class
        in app's `views.py` (where @mapi_func is used)."""
        try:
            self.default_db = self.get_database('mpcontribs_read')
        except ObjectDoesNotExist:
            try:
                from home.models import DBConfig
            except ImportError:
                from webtzite.models import DBConfig
            from webtzite import in_docker
            host = 'mongo' if in_docker() else '0.0.0.0'
            dbconf = DBConfig(
                release=self.release, db_type='mpcontribs_read',
                config="host: {}\ndb: mpcontribs\nport: 27017".format(host)
            )
            dbconf.save()
            self.default_db = self.get_database('mpcontribs_read')
