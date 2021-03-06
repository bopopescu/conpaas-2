import os
import ssl
import sys
import time
import socket
import zipfile
import urllib
import urllib2
import httplib
import getpass
import urlparse
import StringIO
import simplejson

from conpaas.core.https import client
from conpaas.core.misc import rlinput

class BaseClient(object):
    # Set this to the service type. eg: php, java, mysql...
    service_type = None

    def __init__(self):
        self.confdir = os.path.join(os.environ['HOME'], ".conpaas")

        if not os.path.isdir(self.confdir):
            os.mkdir(self.confdir, 0700)

        try:
            client.conpaas_init_ssl_ctx(self.confdir, 'user')
        except IOError:
            # We do not have the certificates yet. But we will get them soon: 
            # see getcerts()
            pass

    def write_conf_to_file(self, key, value):
        oldmask = os.umask(077)
        targetfile = open(os.path.join(self.confdir, key), 'w')
        targetfile.write(value)
        targetfile.close()
        os.umask(oldmask)

    def read_conf_value(self, key):
        return open(os.path.join(self.confdir, key)).read()

    def __callapi_creds(self, method, post, data, endpoint, username='', password='', use_certs=True):
        url = "%s/%s" % (endpoint, method)
        data['username'] = username
        data['password'] = password
        data = urllib.urlencode(data)

        if use_certs:
            opener = urllib2.build_opener(HTTPSClientAuthHandler(
                os.path.join(self.confdir, 'key.pem'),
                os.path.join(self.confdir, 'cert.pem')))
        else:
            opener = urllib2.build_opener(urllib2.HTTPSHandler())

        if post:
            res = opener.open(url, data)
        else:
            url += "?" + data
            res = opener.open(url)

        rawdata = res.read()

        try:
            res = simplejson.loads(rawdata)
            if type(res) is dict and res.get('error') is True:
                # raise Exception(res['msg'] + " while calling %s" % method)
                raise Exception(res['msg'])


            return res
        except simplejson.decoder.JSONDecodeError:
            return rawdata

    def callapi(self, method, post, data, use_certs=True):
        """Call the director API.

        'method': a string representing the API method name.
        'post': boolean value. True for POST method, false for GET.
        'data': a dictionary representing the data to be sent to the director.

        callapi loads the director JSON response and returns it as a Python
        object. If the returned data can not be decoded it is returned as it is.
        """
        try:
            endpoint = self.read_conf_value("target")
            username = self.read_conf_value("username")
            password = self.read_conf_value("password")
        except IOError:
            self.credentials()
            return self.callapi(method, post, data, use_certs)

        try:
            return self.__callapi_creds(method, post, data, endpoint, username, password, use_certs)
        except (ssl.SSLError, urllib2.URLError):
            print "E: Cannot perform the requested action.\nTry updating your client certificates with %s credentials" % sys.argv[0]
            sys.exit(1)
        except Exception as e:
            print "E: %s" % e
            sys.exit(1)

    def callmanager(self, app_id, service_id, method, post, data, files=[]):
        """Call the manager API.

        'service_id': an integer holding the service id of the manager.
        'method': a string representing the API method name.
        'post': boolean value. True for POST method, false for GET.
        'data': a dictionary representing the data to be sent to the director.
        'files': sequence of (name, filename, value) tuples for data to be uploaded as files.

        callmanager loads the manager JSON response and returns it as a Python
        object.
        """
        application = self.application_dict(app_id)
        if application is None:
            print "E: Application %s not found" % app_id
            sys.exit(1)
        elif application['manager'] is None:
            print 'E: Application %s has not started. Try to start it first.' % app_id
            sys.exit(1)


        # File upload
        if files:
            data['service_id'] = service_id
            res = client.https_post(application['manager'], 443, '/', data, files)
        # POST
        elif post:
            res = client.jsonrpc_post(application['manager'], 443, '/', method, service_id, data)
        # GET
        else:
            res = client.jsonrpc_get(application['manager'], 443, '/', method, service_id, data)

        if res[0] == 200:
            try:
                data = simplejson.loads(res[1])
            except simplejson.decoder.JSONDecodeError:
                # Not JSON, simply return what we got
                return res[1]

            return data.get('result', data)

        raise Exception, "Call to method %s on %s failed: %s.\nParams = %s" % (method, application['manager'], res[1], data)

    # def callmanager(self, service_id, method, post, data, files=[]):
    #     """Call the manager API.

    #     'service_id': an integer holding the service id of the manager.
    #     'method': a string representing the API method name.
    #     'post': boolean value. True for POST method, false for GET.
    #     'data': a dictionary representing the data to be sent to the director.
    #     'files': sequence of (name, filename, value) tuples for data to be uploaded as files.

    #     callmanager loads the manager JSON response and returns it as a Python
    #     object.
    #     """
    #     service = self.service_dict(service_id)

    #     # File upload
    #     if files:
    #         res = client.https_post(service['manager'], 443, '/', data, files)
    #     # POST
    #     elif post:
    #         res = client.jsonrpc_post(service['manager'], 443, '/', method, data)
    #     # GET
    #     else:
    #         res = client.jsonrpc_get(service['manager'], 443, '/', method, data)

    #     if res[0] == 200:
    #         try:
    #             data = simplejson.loads(res[1])
    #         except simplejson.decoder.JSONDecodeError:
    #             # Not JSON, simply return what we got
    #             return res[1]

    #         return data.get('result', data)

    #     raise Exception, "Call to method %s on %s failed: %s.\nParams = %s" % (
    #         method, service['manager'], res[1], data)

    def wait_for_state(self, aid, sid, state):
        """Poll the state of service 'sid' till it matches 'state'."""
        res = { 'state': None }

        while res['state'] != state:
            try:
                res = self.callmanager(aid, sid, "get_service_info", False, {})
            except (socket.error, urllib2.URLError):
                time.sleep(2)

    def add(self, service_type, cloud = None, application_id=None, initial_state='INIT'):
        print "Adding a %s service in application %s ..." % (service_type, application_id)
        sys.stdout.flush()

        data = {}
        
        if application_id is not None:
            data['appid'] = application_id
        if cloud is None:
            res = self.callapi("add/" + service_type, True, data)
        else:
            res = self.callapi("add/" + service_type + '/' + cloud, True, data)
        if 'error' in res:
            print res['error']
        else:
            print "done."

        # self.wait_for_state(sid, initial_state)

        sys.stdout.flush()

    def start(self, app_id, service_id, cloud = "default"):
        data = {'cloud': cloud}
        res = self.callmanager(app_id, service_id, "startup", True, data)
        if 'error' in res:
            print res['error']
        else:
            print "Your service is starting up."

    def stop(self, app_id, service_id):
        print "Stopping service... "
        sys.stdout.flush()

        res = self.callmanager(app_id, service_id, "get_service_info", False, {})
        if res['state'] == "RUNNING":
            print "Service is in '%(state)s' state. Shutting it down." % res
            res = self.callmanager(app_id, service_id, "stop", True, {})
        else:
            print "Service is in '%(state)s' state. We can not stop it." % res

    def remove(self, app_id, service_id):
        print "Removing service... "
        sys.stdout.flush()

        res = self.callmanager(app_id, service_id, "get_service_info", False, {})
        if res['state'] not in ( "STOPPED", "INIT" ):
            print "Service is in '%s' state. We can not remove it." % res['state']
            return

        res = self.callapi("remove", True, {'app_id': app_id,'service_id':service_id})
        if res:
            print "done."
        else:
            print "failed."

    def rename(self, app_id, service_id, newname):
        print "Renaming service... "

        if self.callapi("rename", True, { 'app_id': app_id,'service_id':service_id, 'name': newname }):
            print "done."
        else:
            print "failed."

    def service_dict(self, app_id, service_id):
        """Return service's data as a dictionary"""
        services = self.callapi("list", True, {})

        for service in services:
            if str(service['sid']) == str(service_id) and str(service['application_id']) == str(app_id):
                service.pop('state')
                return service
        return []

    def application_dict(self, app_id):
        """Return application's data as a dictionary"""
        applications = self.callapi("listapp", True, {})

        for application in applications:
            if str(application['aid']) == str(app_id):
                return application
        return None 

    def info(self, app_id, service_id):
        """Print service info. Clients should extend this method and print any
        additional information needed. Returns service_dict"""
        service = self.service_dict(app_id, service_id)
        for key, value in service.items():
            print "%s: %s" % (key, value)

        res = self.callmanager(app_id, service['sid'], "get_service_info", False, {})
        print "state:", res['state']

        for key, value in res.items():
            service[key] = value

        return service

    def list_nodes(self, app_id, service_id):
        """List the nodes of a service"""
        nodes = self.callmanager(app_id, service_id, "list_nodes", False, {})
        if 'error' in nodes:
            print "E: Cannot get list of nodes: %s" % nodes['error']
            sys.exit(1)

        for role, role_nodes in nodes.items():
            for node in role_nodes:
                params = {'serviceNodeId': node}
                details = self.callmanager(app_id, service_id, "get_node_info",
                         False, params)
                if 'error' in details:
                    print "Warning: got node identifier from list_nodes but " \
                            "failed on get_node_info: %s" % details['error']
                else:
                    node = details['serviceNode']
                    if 'vmid' in node and 'cloud' in node:
                        print "%s: node %s from cloud %s with IP address %s" \
                              % (role, node['vmid'], node['cloud'], node['ip'])
                    else:
                        print "%s: node %s with IP address %s" \
                              % (role, node['id'], node['ip'])

    def logs(self, app_id, service_id):
        res = self.callmanager(app_id, service_id, "getLog", False, {})
        print res['log']

    def getcerts(self):
        res = self.callapi("getcerts", True, {}, use_certs=False)

        oldmask = os.umask(077)
        zipdata = zipfile.ZipFile(StringIO.StringIO(res))
        zipdata.extractall(path=self.confdir)
        client.conpaas_init_ssl_ctx(self.confdir, 'user')
        os.umask(oldmask)

        #for name in zipdata.namelist():
        #    print os.path.join(self.confdir, name)

    def credentials(self):
        wrong_url = "E: Invalid target URL. Try with something like https://conpaas.example.com:5555\n"

        # Loop till  we get a valid URL
        while True:
            try:
                # Previously saved target_url, if any
                target = self.read_conf_value("target")
            except IOError:
                target = ''

            target = rlinput('Enter the director URL: ', target)
            try:
                url = urlparse.urlparse(target)
            except IndexError:
                print wrong_url
                continue

            if url.scheme != "https":
                print wrong_url
                continue

            # Check if a ConPaaS director is listening at the provided URL
            try:
                available_services = self.__callapi_creds(
                    method='available_services', 
                    post=False, 
                    data={}, 
                    endpoint=target, 
                    use_certs=False)

                # If this yields True we can be reasonably sure that the
                # provided URL is correct
                assert type(available_services) is list 
            except Exception, e:
                print "E: No ConPaaS Director at the provided URL: %s\n" % e
                continue

            # Valid URL
            self.write_conf_to_file('target', target)
            break

        while True:
            try:
                # Previously saved username, if any
                username = self.read_conf_value("username")
            except IOError:
                username = ''

            # Get the username
            username = rlinput('Enter your username: ', username)
            self.write_conf_to_file('username', username)

            # Get the password
            password = getpass.getpass('Enter your password: ')
            self.write_conf_to_file('password', password)

            if self.callapi('login', True, {}, use_certs=False):
                print "Authentication succeeded\n"
                self.getcerts()
                return

            print "Authentication failure\n"

    def available_services(self):
        return self.callapi('available_services', False, {})

    def available_clouds(self):
        return self.callapi('available_clouds', False, {})

    def available(self, types='services'):
        if types == 'clouds':
            for cloud in self.available_clouds():
                print cloud
        else:
            for service in self.available_services():
                print service

    def upload_startup_script(self, aid, sid, filename):
        contents = open(filename).read()

        files = [ ( 'script', filename, contents ) ]

        res = self.callmanager(aid, sid, "/", True, 
            { 'method': 'upload_startup_script', }, files)

        if 'error' in res:
            print res['error']
        else:
            print "Startup script uploaded correctly."

    def check_service_id(self, aid, sid):
        # get requested service data
        for service in self.callapi("list", True, {}):
            if service['service']['sid'] == sid and service['service']['application_id'] == aid:
                # return service type
                return service['service']['type'].lower()

        print "E: cannot find service %s for application %s" % (sid, aid)
        sys.exit(1)

    def prettytable(self, print_order, rows):
        maxlens = {}

        fields = rows[0].keys()

        for field in fields:
            maxlens[field] = len(field)
            for row in rows:
                curlen = len(str(row[field]))
                if curlen > maxlens[field]:
                    maxlens[field] = curlen 

        # Header
        headerstr = [ "{%d:%d}" % (idx, maxlens[key]) 
            for idx, key in enumerate(print_order) ]

        output = " ".join(headerstr).format(*print_order)
        output += "\n" + "-" * (sum([ maxlens[el] for el in print_order ]) 
            + len(print_order) - 1)

        # Rows
        rowstr = [ "{%s:%d}" % (key, maxlens[key]) 
            for idx, key in enumerate(print_order) ]

        for row in rows:
            output += "\n" + " ".join(rowstr).format(**row)

        return output

    def createapp(self, app_name):
        print "Creating new application... "

        if self.callapi("createapp", True, { 'name': app_name }):
            print "done."
        else:
            print "failed."

        sys.stdout.flush()

    def startapp(self, app_id):
        print "Starting application... "
        sys.stdout.flush()

        res = self.callapi("startapp/%s" % app_id, True, {})
        if res:
            print "done."
        else:
            print "failed."

    def stopapp(self, app_id):
        print "Stopping application... "
        sys.stdout.flush()

        res = self.callapi("stopapp/%s" % app_id, True, {})
        if res:
            print "done."
        else:
            print "failed."


    def deleteapp(self, app_id):
        print "Deleting application... "
        sys.stdout.flush()

        res = self.callapi("deleteapp/%s" % app_id, True, {})
        if res:
            print "done."
        else:
            print "failed."

    def renameapp(self, appid, name):
        print "Renaming application... "
        sys.stdout.flush()

        res = self.callapi("renameapp/%s" % appid, True, { 'name' : name })
        if res:
            print "done."
        else:
            print "failed."

    def infoapp(self, app_id):
        res = self.callmanager(app_id, 0, "infoapp", False, {})
        print "Info for application %s" % app_id
        sys.stdout.flush()
        print res

    def manifest(self, manifestfile):
        print "Uploading the manifest... "
        sys.stdout.flush()

        f = open(manifestfile, 'r')
        json = f.read()
        f.close()

        res = self.callapi("upload_manifest", True, { 'manifest': json })
        if res:
            print "done."
        else:
            print "failed."

    def download_manifest(self, appid):
        services = self.callapi("list/%s" % appid, True, {})
        for service in services:
            if service['type'] == 'xtreemfs':
                warning = """WARNING: this application contains an XtreemFS service
After downloading the manifest, the application will be deleted
Do you want to continue? (y/N): """

                sys.stderr.write(warning)
                sys.stderr.flush()

                confirm = ''
                confirm = rlinput('', confirm)
                if confirm != 'y':
                    sys.exit(1)

        res = self.callapi("download_manifest/%s" % appid, True, {})
        if res:
            print simplejson.dumps(res)
        else:
            print "E: Failed downloading manifest file"

    def listapp(self, doPrint=True):
        """Call the 'listapp' method on the director and print the results
        nicely"""
        apps = self.callapi("listapp", True, {})
        if apps:
            if doPrint:
                print self.prettytable(( 'aid', 'name', 'manager' ), apps)
            return [app['aid'] for app in apps]
        else:
            if doPrint:
                print "No existing applications"

    def list(self, appid):
        """Call the 'list' method on the director and print the results
        nicely"""
        if appid == 0:
            services = self.callapi("list", True, {})
        else:
            services = self.callapi("list/%s" % appid, True, {})

        if services:
            servs = []
            for row in services:
                servs.append(row['service'])
            print self.prettytable(( 'sid', 'type', 'application_id', 'name'), servs)
        else:
            print "No running services"

    def version(self):
        version = self.callapi("version", False, {})
        print "ConPaaS director version %s" % version

    def usage(self, application_id, service_id):
        """Print client usage. Extend it with your client commands"""
        print "Usage: %s COMMAND [params]" % sys.argv[0]
        print "COMMAND is one of the following"
        print
        print "    credentials                                       # set your ConPaaS credentials"
        print "    version                                           # show director's version"
        print "    listapp                                           # list all applications"
        print "    available                                         # list supported services"
        print "    clouds                                            # list available clouds"
        print "    list              [appid]                         # list running services under an application"
        print "    deleteapp         appid                           # delete an application"
        print "    createapp         appname                         # create a new application"
        print "    startapp          appid       [cloud]             # start an application"
        print "    stopapp           appid                           # stop an application"
        print "    infoapp           appid                           # information about an application"
        print "    renameapp         appid       newname             # rename an application"
        print "    manifest          filename                        # upload a new manifest"
        print "    download_manifest appid                           # download an existing manifest"
        print "    add               servicetype [appid]             # adds a new service [inside a specific application]"
        print "    start             appid       serviceid [cloud]   # startup the given service [on a specific cloud]"
        print "    info              appid       serviceid           # get service details"
        print "    logs              appid       serviceid           # get service logs"
        print "    stop              appid       serviceid           # stop the specified service"
        print "    remove            appid       serviceid           # removes the specified service"
        print "    rename            appid       serviceid newname   # rename the specified service"
        print "    startup_script    appid       serviceid filename  # upload a startup script"
        print "    usage             appid       serviceid           # show service-specific options"
        print "    list_nodes        appid       serviceid           # list the nodes of a service"

    def main(self, argv):
        """What to do when invoked from the command line. Clients should extend
        this and add any client-specific argument. argv is sys.argv"""

        # We need at least one argument
        try:
            command = argv[1]
        except IndexError:
            self.usage(0,0)
            sys.exit(0)

        if command == "version":
            return getattr(self, command)()

        # Service and application generic commands
        if command in ( "listapp", "createapp", "manifest",
                        "download_manifest", "list", "credentials", 
                        "available", "clouds", "add", "st_usage",
                        "startapp","deleteapp", "renameapp", "infoapp", "stopapp",
                        "getcerts" ):

            if command == "st_usage":
                try:
                    # St_usage wants a service type. Check if we got one, and if
                    # it is acceptable.
                    service_type = argv[2]
                    if service_type not in self.available_services():
                        raise IndexError
                    # normal service usage
                    module = getattr(__import__('cps.' + service_type), service_type)
                    client = module.Client()
                    return getattr(client, 'usage')(0,0)
                except IndexError:
                    self.usage(0,0)
                    sys.exit(0)

            if command == "add":
                try:
                    # Add wants a service type. Check if we got one, and if
                    # it is acceptable.
                    service_type = argv[2]
                    if service_type not in self.available_services():
                        print 'E: Service type "%s" is not supported' % service_type
                        sys.exit(1)

                    applist = self.listapp(False)
                    if not applist:
                        print "E: No existing applications"
                        sys.exit(1)

                    try:
                        appid = int(argv[3])
                        if appid not in applist:
                            print "E: Unknown application id: %s" % appid
                            sys.exit(1)
                    except IndexError:
                        appid = None

                    cloud = None
                    if appid:
                        try:
                            cloud = argv[4]
                            if cloud not in self.available_clouds():
                                print "E: Unknown cloud: %s" % cloud
                                sys.exit(1)
                        except IndexError:
                            pass

                    # taskfarm-specific service creation
                    if service_type == 'taskfarm':
                        from cps.taskfarm import Client
                        return Client().add(service_type, cloud, appid)

                    # normal service creation
                    return getattr(self, command)(service_type, cloud, appid)
                except IndexError:
                    self.usage(0,0)
                    sys.exit(0)

            if command == "createapp":
                appname = argv[2]
                return getattr(self, command)(appname)

            if command in ( 'startapp', 'deleteapp', 'infoapp', 'stopapp'):
                appid = argv[2]
                return getattr(self, command)(appid)

            if command == "renameapp":
                appid = argv[2]
                name  = argv[3]
                return getattr(self, command)(appid, name)

            if command == "manifest":
                try:
                    # 'manifest' wants a filename type. Check if we got one,
                    # and if it is acceptable.
                    open(argv[2])
                    return getattr(self, command)(argv[2])
                except (IndexError, IOError):
                    self.usage(0,0)
                    sys.exit(0)

            if command == "download_manifest":
                appid = argv[2]
                return getattr(self, command)(appid)

            if command == "list":
                if len(sys.argv) == 2:
                    appid = 0
                else:
                    appid = argv[2]
                return getattr(self, command)(appid)

            if command == "available":
                return getattr(self, command)('services')

            if command == "clouds":
                return getattr(self, 'available')('clouds')

            # We need no params, just call the method and leave
            return getattr(self, command)()

        # Service-specific commands
        # Commands requiring a service id. We want it to be an integer.
        try:
            aid = int(argv[2])
            sid = int(argv[3])
        except (ValueError):
            if command == "usage":
                self.main([ argv[0], 'st_usage', argv[2] ])
            else:
                self.usage(0,0)
            sys.exit(0)
        except (IndexError):
            self.usage(0,0)
            sys.exit(0)

        service_type = self.check_service_id(aid, sid)

        if command == "startup_script":
            try:
                # startup_script wants a filename type. Check if we got
                # one, and if it is acceptable.
                open(argv[4])
                return self.upload_startup_script(aid, sid, argv[4])
            except (IndexError, IOError):
                self.usage(0,0)
                sys.exit(0)

        if command == "rename":
            try:
                return self.rename(aid, sid, argv[4])
            except IndexError:
                self.usage(0,0)
                sys.exit(0)

        module = getattr(__import__('cps.' + service_type), service_type)
        client = module.Client()

        if command == "help":
            # We have all been there
            command = "usage"

        if command in ( 'start', 'stop', 'remove', 'info', 'logs', 'usage',
                        'list_nodes' ):
            # Call the method 
            if command == "start":
                if len(sys.argv) == 4:
                    cloud = 'default'
                else:
                    cloud = argv[4]
                return getattr(client, command)(aid, sid, cloud)

            return getattr(client, command)(aid, sid)

        if command == "st_usage":
            return getattr(client, command)()

        client.main(sys.argv)

class HTTPSClientAuthHandler(urllib2.HTTPSHandler):
    def __init__(self, key, cert):
        urllib2.HTTPSHandler.__init__(self)
        self.key = key
        self.cert = cert

    def https_open(self, req):
        return self.do_open(self.getConnection, req)

    def getConnection(self, host, timeout=300):
        return httplib.HTTPSConnection(host, key_file=self.key, cert_file=self.cert)
