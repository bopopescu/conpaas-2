
import argcomplete
import logging
import sys
import time

from .base import BaseClient
from .config import config
from .application import check_appl_name


class ServiceCmd(object):

    def __init__(self, serv_parser, client, service_type=None, roles=None,
                 cmd_help="service sub-commands help"):
        self.client = client
        self.services = None  # cache for service list
        self.type = service_type
        if roles is None:
            self.roles = ['node']
        else:
            self.roles = roles
        self.initial_expected_state = 'INIT'

        self.subparsers = serv_parser.add_subparsers(help=None, title=None,
                                                     description=None,
                                                     metavar="<sub-command>")
        if service_type is not None:
            serv_parser.set_defaults(service_type=service_type)
        self._add_get_types()
        self._add_add()
        self._add_list()
        self._add_start()
        # self._add_start_test()
        self._add_stop()
        self._add_get_config()
        self._add_get_state()
        self._add_get_log()
        self._add_get_history()
        self._add_rename()
        self._add_remove()
        self._add_add_nodes()
        self._add_list_nodes()
        self._add_remove_nodes()
        self._add_help(serv_parser)


    def add_parser(self, *args, **kwargs):
        return self.subparsers.add_parser(*args, **kwargs)

    def get_service_id(self, app_name_or_id, service_name_or_id):
        app_id, _app_name = check_appl_name(self.client, app_name_or_id)
        services = self.client.get_services(app_id, self.type)
        
        try:
            # string may be a service identifier
            service_id = int(service_name_or_id)
        except ValueError:
            # then, string may be a service name
            service_names = [service for service in services
                             if service['service']['name'] == service_name_or_id]
            if service_names == []:
                err_msg = "%s is not a known service" % service_name_or_id
                if self.type is not None:
                    err_msg = err_msg + (" of type %s." % self.type)
                raise Exception(err_msg)
            else:
                service_id = service_names[0]['service']['sid']
        else:
            service_ids = [service for service in services
                           if service['service']['sid'] == service_id]
            if service_ids == []:
                err_msg = "Unknown service id %s" % service_id
                if self.type is not None:
                    err_msg = err_msg + (" of type %s." % self.type)
                raise Exception(err_msg)
        return app_id, service_id

    # ========== help
    def _add_help(self, serv_parser):
        help_parser = self.add_parser('help', help="show help")
        help_parser.set_defaults(run_cmd=self.user_help, parser=serv_parser)

    def user_help(self, args):
        args.parser.print_help()

    # ========== create
    def _add_add(self):
        subparser = self.add_parser('add', help="add a new service")
        subparser.set_defaults(run_cmd=self.add_serv, parser=subparser)
        if self.type is None:
            subparser.add_argument('service_type',
                                   help="Type of the new service")
        subparser.add_argument('--cloud', metavar='NAME', default=None,
                               help="Cloud name where the service manager will be created.")
        subparser.add_argument('--application', metavar='ID_OR_NAME',
                               default=None, help="Application for which the service is created.")

    def add_serv(self, args):
        data = {}
        app_id, _app_name = check_appl_name(self.client, args.application)
        if app_id is not None:
            data['appid'] = app_id
        if self.type is not None:
            stype = self.type
        else:
            stype = args.service_type

        if args.cloud is None:
            res = self.client.call_director_post("add/" + stype, data)
        else:
            res = self.client.call_director_post("add/" + stype
                                                 + '/' + args.cloud, data)
        if 'error' in res:
            self.client.error("failed to add %s service" % stype)
        else:
            print("done.")
        # sid = res['service']['sid']

        # print "Creating new manager on " + res['application']['manager'] + "... ",
        # sys.stdout.flush()

        # state = self.client.wait_for_state(sid, [self.initial_expected_state,
        #                                          'ERROR'])

        # if state == 'INIT':
        #     print("done.")
        # else:
        #     self.client.error("failed to state %s" % state)
        sys.stdout.flush()

    # ========== list
    def _add_list(self):
        subparser = self.add_parser('list', help="list services")
        subparser.set_defaults(run_cmd=self.list_serv, parser=subparser)

    def list_serv(self, args):
        services = self.client.get_services(self.type)
        sorted_serv = []
        for row in services:
            sorted_serv.append(row['service'])
        
        # tertiary sort per service id
        sorted_serv = sorted(sorted_serv, key=lambda k: k['sid'])
        # secondary sort per service types
        sorted_serv = sorted(sorted_serv, key=lambda k: k['type'])
        # primary sort per application
        sorted_serv = sorted(sorted_serv, key=lambda k: k['application_id'])
        table = self.client.prettytable(('application_id', 'type', 'sid', 'name'),
                                        sorted_serv)
        if table:
            print "%s" % table
        else:
            print "No existing services"

    # # ========== start
    # def _add_start(self):
    #     subparser = self.add_parser('start', help="start a service")
    #     subparser.set_defaults(run_cmd=self.start_serv, parser=subparser)
    #     subparser.add_argument('--cloud', metavar='NAME', default=None,
    #                            help="Cloud name where the service will be started.")
    #     subparser.add_argument('app_name_or_id',
    #                            help="Name or identifier of an application")
    #     subparser.add_argument('serv_name_or_id',
    #                            help="Name or identifier of a service")

    # def start_serv(self, args):
    #     if args.cloud is None:
    #         cloud = 'default'
    #     else:
    #         cloud = args.cloud
    #     data = {'cloud': cloud}

    #     app_id, service_id = self.get_service_id(args.app_name_or_id, args.serv_name_or_id)

    #     res = self.client.call_manager_post(app_id, service_id, "startup", data)
    #     if 'error' in res:
    #         self.client.error(res['error'])
    #     else:
    #         print("Service %s is starting..." % service_id)
    #         state = self.client.wait_for_state(app_id, service_id, ['RUNNING', 'STOPPED', 'ERROR'])
    #         if state in ['STOPPED', 'ERROR']:
    #             self.client.error("Failed to start service %s." % service_id)

    # ========== start
    def _add_start(self):
        subparser = self.add_parser('start', help="start a service from the app_manager")
        subparser.set_defaults(run_cmd=self.start_serv, parser=subparser)
        subparser.add_argument('--cloud', metavar='NAME', default=None,
                               help="Cloud name where the service will be started.")
        subparser.add_argument('app_name_or_id',
                               help="Name or identifier of an application")
        subparser.add_argument('serv_name_or_id',
                               help="Name or identifier of a service")

    def start_serv(self, args):
        if args.cloud is None:
            cloud = 'default'
        else:
            cloud = args.cloud
        app_id, service_id = self.get_service_id(args.app_name_or_id, args.serv_name_or_id)
        
        data = {'cloud': cloud, 'service_id':service_id}
        
        res = self.client.call_manager_post(app_id, 0, "start_service", data)
        if 'error' in res:
            self.client.error(res['error'])
        else:
            print("Service %s is starting..." % service_id)
            

    # ========== stop
    def _add_stop(self):
        subparser = self.add_parser('stop', help="stop a service")
        subparser.set_defaults(run_cmd=self.stop_serv, parser=subparser)
        subparser.add_argument('app_name_or_id',
                               help="Name or identifier of an application")
        subparser.add_argument('serv_name_or_id',
                               help="Name or identifier of a service")

    def stop_serv(self, args):
        app_id, service_id = self.get_service_id(args.app_name_or_id, args.serv_name_or_id)

        print("Stopping service %s..." % service_id)
        # res = self.client.call_manager_post(app_id, service_id, "stop")
        data = {'service_id':service_id}
        res = self.client.call_manager_post(app_id, 0, "stop_service", data)
        if 'error' in res:
            self.client.error("Error when stopping service %s: %s"
                              % (service_id, res['error']))
        else:
            print("Service %s is stopping." % service_id)

    # ========== get_config
    def _add_get_config(self):
        subparser = self.add_parser('get_config', help='get configuration of a service')
        subparser.set_defaults(run_cmd=self.get_config, parser=subparser)
        subparser.add_argument('app_name_or_id',
                               help="Name or identifier of an application")
        subparser.add_argument('serv_name_or_id',
                               help="Name or identifier of a service")

    def get_config(self, args):
        app_id, service_id = self.get_service_id(args.app_name_or_id, args.serv_name_or_id)
        service = self.client.service_dict(app_id, service_id)
        print "Director info:"
        for key, value in service.items():
            print "%s: %s" % (key, value)

    # ========== get_state
    def _add_get_state(self):
        subparser = self.add_parser('get_state', help="display a service's state")
        subparser.set_defaults(run_cmd=self.get_state, parser=subparser)
        subparser.add_argument('app_name_or_id',
                               help="Name or identifier of an application")
        subparser.add_argument('serv_name_or_id',
                               help="Name or identifier of a service")

    def get_state(self, args):
        app_id, service_id = self.get_service_id(args.app_name_or_id, args.serv_name_or_id)
        res = self.client.call_manager_get(app_id, service_id, "get_service_info")

        for key, value in res.items():
            print "%s: %s" % (key, value)

    # ========== get_log
    def _add_get_log(self):
        subparser = self.add_parser('get_log', help="get service log")
        subparser.set_defaults(run_cmd=self.get_log, parser=subparser)
        subparser.add_argument('app_name_or_id',
                               help="Name or identifier of an application")
        subparser.add_argument('serv_name_or_id',
                               help="Name or identifier of a service")

    def get_log(self, args):
        app_id, service_id = self.get_service_id(args.app_name_or_id, args.serv_name_or_id)
        res = self.client.call_manager_get(app_id, service_id, "getLog")
        if res:
            print("%s" % res['log'])
        else:
            self.client.error("Failed to retrieve log for service %s: %s"
                              % (service_id, res['error']))

    # ========== get_history
    def _add_get_history(self):
        subparser = self.add_parser('get_history', help="display the service's history")
        subparser.set_defaults(run_cmd=self.get_history, parser=subparser)
        subparser.add_argument('app_name_or_id',
                               help="Name or identifier of an application")
        subparser.add_argument('serv_name_or_id',
                               help="Name or identifier of a service")

    def get_history(self, args):
        app_id, service_id = self.get_service_id(args.app_name_or_id, args.serv_name_or_id)
        res = self.client.call_manager_get(app_id, service_id, "get_service_history")

        if res:
            for entry in res['state_log']:
                time_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(int(entry['time'])))
                print "%s %s %s" % (time_str, entry['state'], entry['reason'])
        else:
            self.client.error("Failed to obtain the history for service %s." % service_id)

    # ========== rename
    def _add_rename(self):
        subparser = self.add_parser('rename', help="rename a service")
        subparser.set_defaults(run_cmd=self.rename_serv, parser=subparser)
        subparser.add_argument('app_name_or_id',
                               help="Name or identifier of an application")
        subparser.add_argument('serv_name_or_id',
                               help="Name or identifier of a service")
        subparser.add_argument('new_name',
                               help="New name for the service")

    def rename_serv(self, args):

        app_id, service_id = self.get_service_id(args.app_name_or_id, args.serv_name_or_id)
        print "Renaming service... "
        
        res = self.client.call_director_post("rename",
                                             { 'app_id': app_id,'service_id':service_id, 'name': args.new_name })
        if res:
            print("Service %s of application %s has been renamed to \"%s\"."
                  % (service_id, app_id, args.new_name))
        else:
            self.client.error("Failed to rename service %s: %s"
                              % (service_id, res['error']))

    # ========== delete
    def _add_remove(self):
        subparser = self.add_parser('remove', help="remove a service")
        subparser.set_defaults(run_cmd=self.remove_serv, parser=subparser)
        subparser.add_argument('app_name_or_id',
                               help="Name or identifier of an application")
        subparser.add_argument('serv_name_or_id',
                               help="Name or identifier of a service")

    def remove_serv(self, args):
        app_id, service_id = self.get_service_id(args.app_name_or_id, args.serv_name_or_id)
        print "Removing service... "
        res = self.client.call_director_post("remove", {'app_id': app_id,'service_id':service_id})
        if res:
            print("Service %s has of application %s been removed." % (service_id, app_id))
        else:
            self.client.error("Failed to remove service %s of applitation %s: %s"
                              % (service_id, app_id, res['error']))


    # ========== get_types
    def _add_get_types(self):
        subparser = self.add_parser('get_types',
                                    help="get available service types")
        subparser.set_defaults(run_cmd=self.get_types, parser=subparser)

    def get_types(self, args):
        res = self.client.call_director_get("available_services")
        for serv_type in res:
            print("%s" % serv_type)

    # ========== list_nodes
    def _add_list_nodes(self):
        subparser = self.add_parser('list_nodes',
                                    help="list nodes of a service")
        subparser.set_defaults(run_cmd=self.list_nodes, parser=subparser)
        subparser.add_argument('app_name_or_id',
                               help="Name or identifier of an application")
        subparser.add_argument('serv_name_or_id',
                               help="Name or identifier of a service")

    def list_nodes(self, args):
        app_id, service_id = self.get_service_id(args.app_name_or_id, args.serv_name_or_id)
        nodes = self.client.call_manager_get(app_id, service_id, "list_nodes")
        if 'error' in nodes:
            self.client.error("Cannot get list of nodes: %s" % nodes['error'])

        for role, role_nodes in nodes.items():
            for node in role_nodes:
                params = {'serviceNodeId': node}
                details = self.client.call_manager_get(app_id, service_id, "get_node_info", params)
                if 'error' in details:
                    print "Warning: got node identifier from list_nodes but failed on get_node_info: %s" % details['error']
                else:
                    node = details['serviceNode']
                    if 'vmid' in node and 'cloud' in node:
                        print "%s: node %s from cloud %s with IP address %s" \
                              % (role, node['vmid'], node['cloud'], node['ip'])
                    else:
                        print "%s: node %s with IP address %s" \
                              % (role, node['id'], node['ip'])

    def _get_roles_nb(self, args):
        total_nodes = 0
        data = {}
        for role in self.roles:
            node_nb = getattr(args, role)
            total_nodes += node_nb
            data[role] = node_nb
        return total_nodes, data

    # ========== add_nodes
    def _add_add_nodes(self):
        subparser = self.add_parser('add_nodes', help="add nodes to a service")
        subparser.set_defaults(run_cmd=self.add_nodes, parser=subparser)
        subparser.add_argument('app_name_or_id', help="Name or identifier of an application")
        subparser.add_argument('serv_name_or_id', help="Name or identifier of a service")
        for role in self.roles:
            subparser.add_argument('--%s' % role, type=int, default=0,
                                   help="Number of %s to add" % role)
        subparser.add_argument('--cloud', '-c', metavar='CLOUD_NAME',
                               default='iaas',
                               help="Name of the cloud where to add nodes")

    def add_nodes(self, args):
        total_nodes, nodes = self._get_roles_nb(args)
        if total_nodes <= 0:
            self.client.error("Cannot add %s nodes." % total_nodes)
        
        app_id, service_id = self.get_service_id(args.app_name_or_id, args.serv_name_or_id)
        # res = self.client.call_manager_post(app_id, service_id, "add_nodes", data)
        
        data={}
        data['nodes'] = nodes
        data['service_id'] = service_id
        data['cloud'] = args.cloud
        res = self.client.call_manager_post(app_id, 0, "add_nodes", data)
        if 'error' in res:
            self.client.error("Could not add nodes to service %s of application %s: %s"
                              % (service_id, app_id, res['error']))
        else:
            # TODO: display the following message only in verbose mode  ===> use logger.info() ?
            print("Starting %s new nodes for service %s of application %s..."
                  % (total_nodes, service_id, app_id))
            state = self.client.wait_for_state(app_id, service_id, ['RUNNING', 'ERROR'])
            if state in ['ERROR']:
                self.client.error("Failed to add nodes to service %s of application %s." % (service_id, app_id))

    # ========== remove_nodes
    def _add_remove_nodes(self):
        subparser = self.add_parser('remove_nodes',
                                    help="remove nodes from a service")
        subparser.set_defaults(run_cmd=self.remove_nodes, parser=subparser)
        subparser.add_argument('app_name_or_id',
                               help="Name or identifier of an application")
        subparser.add_argument('serv_name_or_id',
                               help="Name or identifier of a service")
        for role in self.roles:
            subparser.add_argument('--%s' % role, type=int, default=0,
                                   help="Number of %s nodes to remove" % role)

    def remove_nodes(self, args):
        app_id, service_id = self.get_service_id(args.app_name_or_id, args.serv_name_or_id)
        total_nodes, nodes = self._get_roles_nb(args)
        if total_nodes <= 0:
            self.client.error("Cannot remove %s nodes." % total_nodes)
        data={}
        data['nodes'] = nodes
        data['service_id'] = service_id
        res = self.client.call_manager_post(app_id, 0, "remove_nodes", data)
        if 'error' in res:
            self.client.error("Could not remove nodes from service %s of application %s: %s"
                              % (service_id, app_id, res['error']))
        else:
            print("%s nodes have been successfully removed from service %s of application %s."
                  % (total_nodes, service_id, app_id))
            # state = self.client.wait_for_state(app_id, service_id, ['RUNNING', 'ERROR'])
            # if state in ['ERROR']:
            #     self.client.error("Failed to remove nodes from service %s of application %s." % (service_id, app_id))


def main():
    logger = logging.getLogger(__name__)
    console = logging.StreamHandler()
    formatter = logging.Formatter('%(levelname)s - %(message)s')
    console.setFormatter(formatter)
    logger.addHandler(console)

    cmd_client = BaseClient(logger)

    parser, argv = config('Manage ConPaaS services.', logger)

    _serv_cmd = ServiceCmd(parser, cmd_client)

    argcomplete.autocomplete(parser)
    args = parser.parse_args(argv)
    cmd_client.set_config(args.director_url, args.username, args.password,
                          args.debug)
    try:
        args.run_cmd(args)
    except:
        e = sys.exc_info()[1]
        sys.stderr.write("ERROR: %s\n" % e)
        sys.exit(1)

if __name__ == '__main__':
    main()
