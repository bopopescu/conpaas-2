import json
import os

from conpaas.core.manager import BaseManager

from conpaas.core.expose import expose

from conpaas.core.https.server import HttpJsonResponse, HttpErrorResponse

from conpaas.core.log import create_logger
import conpaas.core.file
import app
from edge import NetworkSnapshot

class ContentDeliveryManager(BaseManager):

    def __init__(self,
                 config_parser, # config file
                 **kwargs):     # anything you can't send in config_parser
                                # (hopefully the new service won't need anything extra)
        self.logger = create_logger(__name__)
        self.nm_logfile = '/var/log/network_monitor.log'
        self.apps_dir = '/usr/local/cds/apps'
        self.state = self.S_RUNNING

    @expose('GET')
    def list_nodes(self, params):
        # get the edge locations from memcached
        if self.state != self.S_RUNNING:
            return HttpErrorResponse('ERROR: Wrong state to list_nodes')
        return HttpJsonResponse({'edge': []})

    @expose('GET')
    def get_service_info(self, params):
        return HttpJsonResponse({'state': self.state, 'type': 'cds'})

    @expose('GET')
    def get_log(self, params):
        try:
            lines = params.get('lines', 20)
            log_lines = conpaas.core.file.unix_tail(self.nm_logfile, lines)
            return HttpJsonResponse(log_lines)
        except Exception as e:
            return HttpErrorResponse('Failed to read log: %s' %(str(e)))

    @expose('GET')
    def get_snapshot(self, params):
        try:
            snapshot = NetworkSnapshot()
            json_snapshot = snapshot.memcache_get_json()
            return HttpJsonResponse(json.loads(json_snapshot))
        except Exception:
            return HttpErrorResponse('Failed to fetch snapshot')

    @expose('GET')
    def get_subscribers(self, params):
        try:
            apps = app.read_apps(self.apps_dir)
            return HttpJsonResponse(apps)
        except Exception as e:
            return HttpErrorResponse('Error fetching subscribers: %s'
                                     %(str(e)))

    @expose('POST')
    def subscribe(self, params):
        for param in ('origin', 'country'):
            if not param in params:
                return HttpErrorResponse('Missing parameter "%s"' %(param))
        origin = params['origin']
        country = params['country']
        try:
            filename = os.path.join(self.apps_dir, origin)
            if os.access(filename, os.R_OK):
                return HttpErrorResponse('"%s" already subscribed' %(origin))
            with open(filename, 'w') as f:
                f.write('origin=%s country=%s' %(origin, country))
            return HttpJsonResponse({'subscribe': True})
        except Exception as e:
            return HttpErrorResponse('Error subscribing "%s": %s'
                                     %(origin, str(e)))

    @expose('POST')
    def unsubscribe(self, params):
        if not 'origin' in params:
            return HttpErrorResponse('Missing parameter: "origin"')
        origin = params['origin']
        try:
            filename = os.path.join(self.apps_dir, origin)
            if not os.access(filename, os.R_OK):
                return HttpErrorResponse('"%s" is not subscribed' %(origin))
            os.remove(filename)
            return HttpJsonResponse({'unsubscribe': True})
        except Exception as e:
            return HttpErrorResponse('Error unsubscribing "%s": %s'
                                     %(origin, str(e)))

