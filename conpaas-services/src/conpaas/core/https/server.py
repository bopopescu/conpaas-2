# -*- coding: utf-8 -*-

"""
    conpaas.core.https.server
    =========================
    ConPaaS core: HTTPS server-side support.

    This module is used by both agents and managers.

    Class ConpaasSecureServer is instantiated in the sbin/
    sripts:

        from conpaas.core import https
        d = https.server.ConpaasSecureServer(
                         (options.address, options.port),
                         config_parser,
                         role) # role='agent' or 'manager'
        d.serve_forever()

    It uses basic HTTP classes from the standard library
    and the pyopenssl library. The trick is to replace the
    normal socket used inside the HTTP classes from standard
    python libraries with a SSL.Connection object provided
    by the pyopenssl library.

    :copyright: (C) 2010-2013 by Contrail Consortium.
"""

import socket
import urlparse
import httplib
import json
import cgi
import os
import sys
import traceback

from SocketServer import BaseServer
from BaseHTTPServer import HTTPServer, BaseHTTPRequestHandler
from OpenSSL import SSL

from conpaas.core import log
from conpaas.core.expose import exposed_functions_http_methods
# from conpaas.core.expose import exposed_functions
# from conpaas.core.services import manager_services
from conpaas.core.services import agent_services


class HttpError(Exception): pass


class FileUploadField(object):
    def __init__(self, filename, file):
        self.filename = filename
        self.file = file


class HttpRequest(object): pass
class HttpResponse(object): pass


class HttpErrorResponse(HttpResponse):
    def __init__(self, error_message):
        self.message = error_message


class HttpJsonResponse(HttpResponse):
    def __init__(self, obj={}):
        self.obj = obj


class HttpFileDownloadResponse(HttpResponse):
    def __init__(self, filename, file):
        self.filename = filename
        self.file = file


class HTTPSServer(HTTPServer):
    def __init__(self, server_address, handler, ctx):
        BaseServer.__init__(self, server_address, handler)
        self.socket = SSL.Connection(ctx, socket.socket(self.address_family,
                                                        self.socket_type))
        self.server_bind()
        self.server_activate()

    def shutdown_request(self, request):
        request.shutdown()


class ConpaasRequestHandlerComponent(object):
    def __init__(self):
        self.exposed_functions = {}

    def get_exposed_methods(self):
        wrap_func_name = 'wrapped'
        for attr_name in dir(self):
            attr = object.__getattribute__(self, attr_name)
            if hasattr(attr, 'im_self'):
                if attr.im_func.__name__ == wrap_func_name:
                    if attr.func_closure and attr.func_closure[0] and attr.func_closure[0].cell_contents:
                        method_id = id( attr.func_closure[0].cell_contents)
                        http_method = exposed_functions_http_methods[method_id]
                        if http_method not in self.exposed_functions:
                            self.exposed_functions[http_method] = {}
                        self.exposed_functions[http_method][attr_name] = attr
        return self.exposed_functions

class ConpaasSecureServer(HTTPSServer):
    '''
    HTTPS server for ConPaaS.

    It maps HTTP requests to functions implemented in the manager or
    agent class through the _register_method function.

    '''

    def __init__(self, server_address, config_parser, role, **kwargs):
        log.init(config_parser.get(role, 'LOG_FILE'))
        self.instances = {}
        self.config_parser = config_parser
        self.callback_dict = {'GET': {}, 'POST': {}, 'UPLOAD': {}}

        if role == 'manager':
            from conpaas.core.manager import ApplicationManager
            service_instance = ApplicationManager(self, config_parser, **kwargs)
            # services = manager_services
        else:
            services = agent_services

            # Instantiate the requested service class
            service_type = config_parser.get(role, 'TYPE')
            try:
                module = __import__(services[service_type]['module'], globals(), locals(), ['*'])
            except ImportError:
                raise Exception('Could not import module containing service class "%(module)s"' %
                    services[service_type])

            # Get the appropriate class for this service
            service_class = services[service_type]['class']
            try:
                instance_class = getattr(module, service_class)
            except AttributeError:
                raise Exception('Could not get service class %s from module %s' % (service_class, module))

            # Create an instance of the service class
            service_instance = instance_class(config_parser, **kwargs)

        self.instances[0] = service_instance

        handler_exposed_functions = service_instance.get_exposed_methods()


        for http_method in handler_exposed_functions:
            for func_name in handler_exposed_functions[http_method]:
                self._register_method(http_method, 0, func_name, handler_exposed_functions[http_method][func_name])

        # Start the HTTPS server
        ctx = self._conpaas_init_ssl_ctx(role, config_parser.get(role, 'CERT_DIR'), SSL.SSLv23_METHOD)
        HTTPSServer.__init__(self, server_address, ConpaasRequestHandler, ctx)


    def _register_method(self, http_method, service_id, func_name, callback):
        if service_id not in self.callback_dict[http_method]:
            self.callback_dict[http_method][service_id] = {}
        self.callback_dict[http_method][service_id][func_name] = callback

    def _deregister_methods(self, service_id):
        for http_method in self.callback_dict:
            del self.callback_dict[http_method][service_id]

    # def _register_method(self, http_method, func_name, callback):
    #     self.callback_dict[http_method][func_name] = callback

    def _conpaas_callback_agent(self, connection, x509, errnum, errdepth, ok):
        '''
            The custom certificate verification function called on the
            agent's server side. The agent must accept requests comming
            only from a manager or agent pertaining to the same userid
            and sid.
        '''
        components = x509.get_subject().get_components()

        dict = {}

        '''
            Somehow this function gets called twice: once with the CA's
            certificate and once with the peer's certificate. So first
            we rule out the CA's certificate.
        '''

        for key,value in components:
            dict[key] = value
            if key == 'CN':
                if value == 'CA':
                    return ok

        # Check if request from frontend
        if dict['role'] == 'frontend':
            return ok

        if dict['role'] not in ('manager', 'agent'):
            return False


        uid = self.config_parser.get('agent', 'USER_ID')
        aid = self.config_parser.get('agent', 'APP_ID')


        if dict['UID'] != uid or dict['serviceLocator'] != aid:
            return False


        #print 'Received request from %s' % x509.get_subject()
        #sys.stdout.flush()
        return ok

    def _conpaas_callback_manager(self, connection, x509, errnum, errdepth,ok):
        '''
            The custom certificate verification function called on the
            manager's server side. The manager must accept requests comming
            only from the frontend or the user.

	    Note: Because of the GIT hook, the manager can also accept
	    requests from itself.
        '''
        components = x509.get_subject().get_components()
        dict = {}

        '''
            Somehow this function gets called twice: once with the CA's
            certificate and once with the peer's certificate. So first
            we rule out the CA's certificate.
        '''
        for key,value in components:
            dict[key] = value
            if key == 'CN':
                if value == 'CA':
                    return ok

        # Check if request from frontend
        if dict['role'] == 'frontend':
            return ok

        # Check if request from user or manager
        if dict['role'] != 'user' and dict['role'] != 'manager':
            return False

        uid = self.config_parser.get('manager', 'USER_ID')
        if dict['UID'] != uid:
            return False


        #print 'Received request from %s' % x509.get_subject()
        #sys.stdout.flush()

        return ok

    def _conpaas_init_ssl_ctx(self, role, cert_dir, protocol, verify_depth=9):
        '''
            Initializes a ssl context to be used by the HTTPS server
        '''

        cert_file = cert_dir + '/cert.pem'
        key_file = cert_dir + '/key.pem'
        ca_cert_file = cert_dir + '/ca_cert.pem'

        if role == 'agent':
            verify_callback = self._conpaas_callback_agent
        else:
            verify_callback = self._conpaas_callback_manager

        ctx = SSL.Context(protocol)
        ctx.use_privatekey_file (key_file)
        ctx.use_certificate_file(cert_file)
        ctx.load_verify_locations(ca_cert_file)
        ctx.set_verify(SSL.VERIFY_PEER|SSL.VERIFY_FAIL_IF_NO_PEER_CERT,
                       verify_callback)

        return ctx

class ConpaasRequestHandler(BaseHTTPRequestHandler):
    '''
    Minimal HTTP request handler that uses reflection to map requested URIs
    to URI handler methods.

    Mapping is as follows:
      GET  /foo -> self.foo_GET
      POST /foo -> self.foo_POST
      etc.

    URI handler methods should accept 1 parameter; a dict containing key/value
    pairs of GET parameters.

    '''

    JSON_CONTENT_TYPES = ['application/json-rpc',
                          'application/json',
                          'application/jsonrequest']
    MULTIPART_CONTENT_TYPE = 'multipart/form-data'

    def setup(self):
        """
        Overriding StreamRequestHandler.setup() in SocketServer.py

        We need to use socket._fileobject Because SSL.Connection
        doesn't have a 'dup'. Not exactly sure WHY this is, but
        this is backed up by comments in socket.py and SSL/connection.c
        """
        self.connection = self.request
        self.rfile = socket._fileobject(self.request, "rb", self.rbufsize)
        self.wfile = socket._fileobject(self.request, "wb", self.wbufsize)

    def handle_one_request(self):
        '''
        Handle a single HTTP request.

        You normally don't need to override this method; see the class
        __doc__ string for information on how to handle specific HTTP
        commands such as GET and POST.

        '''

        self.raw_requestline = self.rfile.readline()
        if not self.raw_requestline:
            self.close_connection = 1
            return
        if not self.parse_request(): # An error code has been sent, just exit
            return
        parsed_url = urlparse.urlparse(self.path)
        # we allow calls to / only
        if parsed_url.path != '/':
            self.send_error(httplib.NOT_FOUND)
            return

        # require content-type header
        if 'content-type' not in self.headers:
            self.send_error(httplib.UNSUPPORTED_MEDIA_TYPE)
            return

        if self.command == 'GET':
            self._handle_get(parsed_url)
        elif self.command == 'POST':
            self._handle_post()
        else:
            self.send_error(httplib.METHOD_NOT_ALLOWED)

    def _handle_get(self, parsed_url):
        if self.headers['content-type'] in self.JSON_CONTENT_TYPES:
            self._dispatch('GET', self._parse_jsonrpc_get_params(parsed_url))
        else:
            self.send_error(httplib.UNSUPPORTED_MEDIA_TYPE)

    def _handle_post(self):
        if self.headers['content-type'] in self.JSON_CONTENT_TYPES:
            self._dispatch('POST', self._parse_jsonrpc_post_params())
        elif self.headers['content-type'].startswith(self.MULTIPART_CONTENT_TYPE):
            self._dispatch('UPLOAD', self._parse_upload_params())
        else:
            self.send_error(httplib.UNSUPPORTED_MEDIA_TYPE)

    def _parse_jsonrpc_get_params(self, parsed_url):
        params = urlparse.parse_qs(parsed_url.query)
        # get rid of repeated params, pick the last one
        for k in params:
            if isinstance(params[k], list):
                params[k] = params[k][-1]
        if 'params' in params:
            params['params'] = json.loads(params['params'])
        return params

    def _parse_jsonrpc_post_params(self):
        if 'content-length' not in self.headers:
            self.send_error(httplib.LENGTH_REQUIRED)
        if not self.headers['content-length'].isdigit():
            self.send_error(httplib.BAD_REQUEST)
        tp = self.rfile.read(int(self.headers['content-length']))
        params =  json.loads(tp)
        return params

    def _parse_upload_params(self):
        post_data = cgi.FieldStorage(fp=self.rfile, headers=self.headers, environ={'REQUEST_METHOD': 'POST'})
        params = {}
        # get rid of repeated params, pick the last one
        if post_data.list:
            for k in post_data.keys():
                if isinstance(post_data[k], list): record = post_data[k][-1]
                else: record = post_data[k]
                if record.filename == None:
                    params[record.name] = record.value
                else:
                    params[record.name] = FileUploadField(record.filename, record.file)
        return params

    def _dispatch(self, callback_type, params):
        if 'service_id' not in params:
            self.send_service_missing(callback_type, params)
            return
        if int(params['service_id']) not in self.server.callback_dict[callback_type]:
            self.send_service_not_found(callback_type, params)
            return

        callback_service_id = int(params.pop('service_id'))

        if 'method' not in params:
            self.send_method_missing(callback_type, params)
            return
        if params['method'] not in self.server.callback_dict[callback_type][callback_service_id]:
            self.send_method_not_found(callback_type, params)
            return

        callback_name = params.pop('method')
        callback_params = {}
        if callback_type != 'UPLOAD':
            if 'params' in params:
                callback_params = params['params']
            request_id = params['id']
        else:
            callback_params = params
            request_id = 1
        try:
            # response = self._do_dispatch(callback_type, callback_name, callback_params)
            response = self._do_dispatch(callback_type, callback_service_id, callback_name, callback_params)
            if isinstance(response, HttpFileDownloadResponse):
                self.send_file_response(httplib.OK, response.file,{'Content-disposition': 'attachement; filename="%s"' % (response.filename)})
            elif isinstance(response, HttpErrorResponse):
                self.send_custom_response(httplib.OK,json.dumps({'error': response.message, 'id': request_id}))
            elif isinstance(response, HttpJsonResponse):
                self.send_custom_response(httplib.OK,json.dumps({'result': response.obj, 'error': None, 'id': request_id}))
        except:
            errmsg = 'Error when calling method %s on service %s with params %s: %s' \
                    % (callback_name, callback_service_id, callback_params, traceback.format_exc())
            self.send_custom_response(httplib.OK,
                                      json.dumps({'error': errmsg}))
            sys.stderr.write(errmsg + '\n')
            sys.stderr.flush()

    # def _do_dispatch(self, callback_type, callback_name, params):
        # return self.server.callback_dict[callback_type][callback_name](self.server.instance, params)

    def _do_dispatch(self, callback_type, callback_service_id, callback_name, params):
        return self.server.callback_dict[callback_type][callback_service_id][callback_name](params)

    def send_custom_response(self, code, body=None):
        '''Convenience method to send a custom HTTP response.
        code: HTTP Response code.
        body: Optional HTTP response content.
        '''
        self.send_response(code)
        self.end_headers()
        if body != None:
            print >>self.wfile, body,

    def send_file_response(self, code, filename, headers=None):
        fd = open(filename)
        stat = os.fstat(fd.fileno())
        self.send_response(code)
        for h in headers:
            self.send_header(h, headers[h])
        self.send_header('Content-length', stat.st_size)
        self.end_headers()
        while fd.tell() != stat.st_size:
            print >>self.wfile, fd.read(),
        fd.close()

    def send_method_missing(self, method, params):
        self.send_custom_response(httplib.BAD_REQUEST, 'Did not specify method')

    def send_method_not_found(self, method, params):
        self.send_custom_response(httplib.NOT_FOUND, 'Method not found')

    def send_service_missing(self, method, params):
        self.send_custom_response(httplib.BAD_REQUEST, 'Did not specify service')

    def send_service_not_found(self, method, params):
        self.send_custom_response(httplib.NOT_FOUND, 'Service not found')

    def log_message(self, format, *args):
        '''Override logging to disable it.'''
        pass

    def _render_arguments(self, method, params):
        ret = '<p>Arguments:<table>'
        ret += '<tr><th>Method</th><td>' + method + '</td></tr>'
        for param in params:
            if isinstance(params[param], dict):
                ret += '<tr><th>' + param + '</th><td>Contents of: '
                ret += params[param].filename + '</td></tr>'
            else:
                ret += '<tr><th>' + param + '</th><td>'
                ret += params[param] + '</td></tr>'
        ret += '</table></p>'
        return ret

