# -*- coding: utf-8 -*-

"""
    cpsdirector.service
    ===================

    ConPaaS director: services implementation

    :copyright: (C) 2013 by Contrail Consortium.
"""

from flask import Blueprint
from flask import jsonify, helpers, request, make_response, g

from sqlalchemy.exc import InvalidRequestError

import sys
import traceback

import simplejson
from datetime import datetime

from cpsdirector import db

from cpsdirector.common import log, log_error, build_response
from cpsdirector.common import error_response

from cpsdirector import cloud as manager_controller

from cpsdirector import common
from cpsdirector.application import Application

from conpaas.core.services import manager_services
from conpaas.core.https import client

service_page = Blueprint('service_page', __name__)

valid_services = manager_services.keys()

class Service(db.Model):
    #(genc): sid can not be unique as it can be the same for different applications
    # so i am using another key
    rec_id = db.Column(db.Integer, primary_key=True, autoincrement=True)

    sid = db.Column(db.Integer)
    name = db.Column(db.String(256))
    type = db.Column(db.String(32))
    state = db.Column(db.String(32))
    created = db.Column(db.DateTime)
    # manager = db.Column(db.String(512))
    # vmid = db.Column(db.String(256))
    cloud = db.Column(db.String(128))
    subnet = db.Column(db.String(18))

    # user_id = db.Column(db.Integer, db.ForeignKey('user.uid'))
    # user = db.relationship('User', backref=db.backref('services',
    #     lazy="dynamic"))

    application_id = db.Column(db.Integer, db.ForeignKey('application.aid'))
    application = db.relationship('Application', backref=db.backref('services',
                                  lazy="dynamic"))

    def __init__(self, **kwargs):
        # Default values
        self.state = "INIT"
        self.created = datetime.utcnow()

        for key, val in kwargs.items():
            setattr(self, key, val)

    def to_dict(self):
        serv = {}
        app = {}
        for c in self.__table__.columns:
            serv[c.name] = getattr(self, c.name)
            if type(serv[c.name]) is datetime:
                serv[c.name] = serv[c.name].isoformat()

        # for c in self.application.__table__.columns:
        #     app[c.name] = getattr(self.application, c.name)

        app = self.application.to_dict()

        return { 'service': serv, 'application': app }

    def remove(self):
        db.session.delete(self)
        db.session.commit()

def get_service(user_id, application_id, service_id):
    service = Service.query.filter_by(sid=service_id, application_id=application_id).first()
    if not service:
        log('Service %s from application %s does not exist'
            % (service_id, application_id))
        return

    if service.application.user_id != user_id:
        log('Service %s from application %s is not owned by user %s'
            % (service_id, application_id, user_id))
        return

    return service


def callmanager(app_id, service_id, method, post, data, files=[]):
    """Call the manager API.

    'service_id': an integer holding the service id of the manager.
    'method': a string representing the API method name.
    'post': boolean value. True for POST method, false for GET.
    'data': a dictionary representing the data to be sent to the director.
    'files': sequence of (name, filename, value) tuples for data to be uploaded as files.

    callmanager loads the manager JSON response and returns it as a Python
    object.
    """
    client.conpaas_init_ssl_ctx('/etc/cpsdirector/certs', 'director')

    application = get_app_by_id(g.user.uid, app_id)

    if application is None:
        msg = "Application %s not found." % app_id
        log_error(msg)
        return error_response(msg)
    elif application.to_dict()['manager'] is None:
        msg = "Application %s has not started. Try to start it first." % app_id
        log_error(msg)
        return error_response(msg)

    application = application.to_dict()
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


@service_page.route("/available_services", methods=['GET'])
def available_services():
    """GET /available_services"""
    return build_response(simplejson.dumps(valid_services))


from cpsdirector.application import get_default_app, get_app_by_id

from cpsdirector.user import cert_required

def _add(service_type, app_id):
    log("User '%s' is attempting to add a new %s service to application %s"
        % (g.user.username, service_type, app_id))

    # Use default application id if no appid was specified
    if not app_id:
        app = get_default_app(g.user.uid)
        if not app:
            msg = "No existing applications"
            log_error(msg)
            return error_response(msg)
        else:
            app_id = app.aid
    else:
        app = get_app_by_id(g.user.uid, app_id)

    # Check if we got a valid service type
    if service_type not in valid_services:
        msg = "Unknown service type '%s'" % service_type
        log_error(msg)
        return error_response(msg)

    data = { 'service_type': service_type }
    res  = callmanager(app_id, 0, "add_service", True, data)

    if 'service_id' in res:
        sid = res['service_id']
        s = Service(sid=sid, name="New %s service" % service_type, type=service_type,
            user=g.user, application=app, manager=app.to_dict()['manager'])
        db.session.add(s)
        db.session.commit()

        log('Service created successfully')
        return s.to_dict()

    return res


@service_page.route("/add/<servicetype>", methods=['POST'])
@cert_required(role='user')
def add(servicetype):
    """eg: POST /start/php

    POSTed values might contain 'appid' to specify that the service to be
    created has to belong to a specific application. If 'appid' is omitted, the
    service will belong to the default application.

    Returns a dictionary with service data (manager's vmid and IP address,
    service name and ID) in case of successful authentication and correct
    service creation. False is returned otherwise.
    """
    appid = request.values.get('appid')

    return build_response(jsonify(_add(servicetype, appid)))


def _rename(app_id, serviceid, newname):
    log("User '%s' is attempting to rename service %s from application %s"
        % (g.user.username, serviceid, app_id))

    try:
        app_id = int(app_id)
        serviceid = int(serviceid)
    except:
        msg = 'Bad specification of application or service IDs'
        log_error(msg)
        return error_response(msg)

    if not newname:
        msg = '"name" is a required argument'
        log_error(msg)
        return error_response(msg)

    service = get_service(g.user.uid, app_id, serviceid)
    if not service:
        msg = 'Invalid service_id'
        log_error(msg)
        return error_response(msg)

    service.name = newname
    db.session.commit()

    log('Service renamed successfully')
    return {}

@service_page.route("/rename", methods=['POST'])
@cert_required(role='user')
def rename():
    app_id = request.values.get('app_id')
    service_id = request.values.get('service_id')
    newname = request.values.get('name')

    return build_response(jsonify(_rename(app_id, service_id, newname)))


def _remove(app_id, service_id):
    log("User '%s' is attempting to remove service %s from application %s"
        % (g.user.username, service_id, app_id))

    try:
        app_id = int(app_id)
        service_id = int(service_id)
    except:
        msg = 'Bad specification of application or service IDs'
        log_error(msg)
        return error_response(msg)

    data = { 'service_id': service_id }
    res  = callmanager(app_id, 0, "remove_service", True, data)

    if 'error' in res:
        return res

    service = get_service(g.user.uid, app_id, service_id)
    service.remove()

    log('Service removed successfully')
    return {}

@service_page.route("/remove", methods=['POST'])
@cert_required(role='user')
def remove():
    """Terminate the service whose id matches the one provided in the manager
    certificate."""
    app_id = request.values.get('app_id')
    service_id = request.values.get('service_id')

    return build_response(jsonify(_remove(app_id, service_id)))


@service_page.route("/list", methods=['POST', 'GET'])
@cert_required(role='user')
def list_all_services():
    """POST /list

    List running ConPaaS services under all applications if the user is
    authenticated. Return False otherwise.
    """
    return build_response(simplejson.dumps([
        ser.to_dict() for ser in Service.query.join(Application).filter_by(user_id=g.user.uid)
    ]))


@service_page.route("/list/<int:appid>", methods=['POST', 'GET'])
@cert_required(role='user')
def list_services(appid):
    """POST /list/2

    List running ConPaaS services under a specific application if the user is
    authenticated. Return False otherwise.
    """
    return build_response(simplejson.dumps([
        ser.to_dict() for ser in Service.query.filter_by(application_id=appid)
    ]))


@service_page.route("/download/ConPaaS.tar.gz", methods=['GET'])
def download():
    """GET /download/ConPaaS.tar.gz

    Returns ConPaaS tarball.
    """
    log('ConPaaS tarball downloaded')

    return helpers.send_from_directory(common.config_parser.get('conpaas', 'CONF_DIR'),
        "ConPaaS.tar.gz")
