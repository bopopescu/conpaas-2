# -*- coding: utf-8 -*-

"""
    :copyright: (C) 2010-2013 by Contrail Consortium.
"""

from threading import Thread, Timer
import os
import tempfile
import string
from random import choice
import collections

from conpaas.core.manager import BaseManager
from conpaas.core.manager import ManagerException
from conpaas.core.manager import WrongNrNodesException

from conpaas.core.https.server import HttpJsonResponse, HttpErrorResponse, FileUploadField
from conpaas.core.expose import expose
from conpaas.core.misc import check_arguments, is_in_list, is_not_in_list,\
    is_list, is_non_empty_list, is_list_dict, is_list_dict2, is_string,\
    is_int, is_pos_nul_int, is_pos_int, is_dict, is_dict2, is_bool,\
    is_uploaded_file
from conpaas.core.misc import run_cmd_code

import conpaas.services.mysql.agent.client as agent
from conpaas.services.mysql.agent.client import AgentException
from conpaas.services.mysql.manager.config import Configuration

import logging
import commands
import MySQLdb

class MySQLManager(BaseManager):

    # MySQL Galera node types
    ROLE_MYSQL = 'mysql'  # regular node running a mysqld daemon
    ROLE_GLB   = 'glb'    # load balancer running a glbd daemon

    def __init__(self, conf, **kwargs):
        BaseManager.__init__(self, conf)

        self.logger.debug("Entering MySQLServerManager initialization")

        # default value for mysql volume size
        self.mysql_volume_size = 1024

        #(genc): this is ignored at the moment
        # self.controller.config_clouds({"mem": "512", "cpu": "1"})
        self.root_pass = None
        self.config = Configuration(conf, self.logger)
        self.logger.debug("Leaving MySQLServer initialization")

    def get_service_type(self):
        return 'mysql'

    def get_node_roles(self):
        return [ self.ROLE_MYSQL, self.ROLE_GLB ]

    def get_default_role(self):
        return self.ROLE_MYSQL

    def get_role_sninfo(self, role, cloud):
        if role == self.ROLE_MYSQL:
            return self.get_standard_sninfo_with_volume(
                        role, cloud, 'mysql-%(vm_id)s',
                        self.mysql_volume_size)
        else:
            return BaseManager.get_role_sninfo(self, role, cloud)

    def get_role_logs(self, role):
        logs = BaseManager.get_role_logs(self, role)

        if role == self.ROLE_MYSQL:
            logs.extend([{'filename': 'mysql.log',
                          'description': 'MySQL log',
                          'path': '/var/cache/cpsagent/mysql.log'}]);

        return logs

    def get_context_replacement(self):
        if not self.root_pass:
            # self.root_pass='password'
            self.root_pass = ''.join([choice(string.letters + string.digits) for i in range(10)])
        # self.logger.debug('setting context to %s' % dict(mysql_username='mysqldb', mysql_password=self.root_pass))
        return dict(mysql_username='mysqldb', mysql_password=str(self.root_pass))

    def on_start(self, nodes):
        succ = self._start_mysqld(nodes)
        self.config.addMySQLServiceNodes(nodes)
        return succ

    def _start_mysqld(self, nodes):
        dev_name = None
        existing_nodes = self.config.get_nodes_addr()
        for serviceNode in nodes:
            try:
                agent.start_mysqld(serviceNode.ip, self.config.AGENT_PORT, existing_nodes, serviceNode.volumes[0].dev_name)
            except AgentException, ex:
                self.logger.exception('Failed to start MySQL node %s: %s' % (str(serviceNode), ex))
                raise
        try:
            glb_nodes = self.config.get_glb_nodes()
            self.logger.debug('MySQL nodes already active: %s' % glb_nodes)
            nodesIp=[]
            nodesIp = ["%s:%s" % (node.ip, self.config.MYSQL_PORT)  # FIXME: find real mysql port instead of default 3306
                         for node in nodes]
            for glb in glb_nodes:
                agent.add_glbd_nodes(glb.ip, self.config.AGENT_PORT, nodesIp)
            return True
        except Exception as ex:
            self.logger.exception('Failed to configure new GLB node: %s' % ex)
            raise

    def _start_glbd(self, new_glb_nodes):
        for new_glb in new_glb_nodes:
            try:
                nodes = ["%s:%s" % (node.ip, self.config.MYSQL_PORT)  # FIXME: find real mysql port instead of default 3306
                         for node in self.config.get_nodes()]
                self.logger.debug('create_glb_node all mysql nodes = %s' % nodes)
                self.logger.debug('create_glb_node for new_glb.ip  = %s' % new_glb.ip)
                agent.start_glbd(new_glb.ip, self.config.AGENT_PORT, nodes)
            except AgentException:
                self.logger.exception('Failed to start GLB at node %s' % new_glb.ip)
                raise

    @expose('GET')
    def list_nodes(self, kwargs):
        """
        List this MySQL Galera current agents.

        No parameters.

        Returns a dict with keys:
        nodes : list of regular node identifiers
        glb_nodes : lits of load balancing node identifiers
        """
        try:
            exp_params = []
            check_arguments(exp_params, kwargs)
        except Exception as ex:
            return HttpErrorResponse("%s" % ex)

        try:
            self.check_state([self.S_RUNNING, self.S_ADAPTING])
        except:
            return HttpJsonResponse({})

        return HttpJsonResponse({ self.ROLE_MYSQL:
                                    [ node.id for node in self.config.get_nodes() ],
                                  self.ROLE_GLB:
                                    [ node.id for node in self.config.get_glb_nodes() ]
                                })

    @expose('GET')
    def get_node_info(self, kwargs):
        """
        Gets info of a specific node.

        Parameters
        ----------
        serviceNodeId : string
            identifier of node to query

        Returns a dict with keys:
        serviceNode : dict with keys:
            id : string
                node identifier
            ip : string
                node public IP address
            vmid : string
                unique identifier of the VM inside the cloud provider
            cloud :string
                name of cloud provider
        """
        try:
            node_ids = self.config.serviceNodes.keys() + self.config.glb_service_nodes.keys()
            exp_params = [('serviceNodeId', is_in_list(node_ids))]
            serviceNodeId = check_arguments(exp_params, kwargs)
        except Exception as ex:
            return HttpErrorResponse("%s" % ex)

        serviceNode = self.config.getMySQLNode(serviceNodeId)
        return HttpJsonResponse({'serviceNode': {'id': serviceNode.id,
                                                 'ip': serviceNode.ip,
                                                 'vmid': serviceNode.vmid,
                                                 'cloud': serviceNode.cloud_name,
                                                 'isNode': serviceNode.isNode,
                                                 'isGlb_node': serviceNode.isGlb_node,
                                                 'role': serviceNode.role,
                                                 'logs': self.get_role_logs(serviceNode.role)
                                                 }
                                 })

    def on_add_nodes(self, nodes):
        for node in nodes:
            self.logger.info('add node role: %s' % node.role)

        reg_nodes = filter(lambda n: n.role == self.ROLE_MYSQL, nodes)
        if len(reg_nodes):
            self._start_mysqld(reg_nodes)
            self.config.addMySQLServiceNodes(reg_nodes)

        gal_nodes = filter(lambda n: n.role == self.ROLE_GLB, nodes)
        if len(gal_nodes):
            self._start_glbd(gal_nodes)
            self.config.addGLBServiceNodes(gal_nodes)

        # _strat_mysql raises an exception
        return True

    @expose('GET')
    def getMeanLoad(self, kwargs):
        """
        TODO: placeholder for obtaining performance metrics.

        No parameters.

        Returns a dict with keys:
            'loads': float array, wsrep_local_recv_queue_avg of each node
            'meanLoad':float, average load of wsrep_local_recv_queue_avg galera variable across the nodes
            'updates': float, array within the  number of update queries across the nodes
            'meanUpdate' : average number of update queries across the nodes
            'selects': int array, array within the  number of select queries across the nodes
            'meanSelect': float, average number of select queries across the nodes
            'deletes' : int array,array within the  number of delete queries across the nodes
            'meanDelete' : float, average number of delete queries across the nodes
            'inserts': int array, array within the  number of insert queries across the nodes
            'meanInsert': float average number of insert  queries across the nodes
        """
        nodes = self.config.get_nodes()
        loads=[]
        load=0.0
        updates=[]
        update=0.0
        selects=[]
        select=0
        deletes=[]
        delete=0
        inserts=[]
        insert=0
        for node in nodes:
            # self.logger.debug('connecting to: %s, using username: %s and pwd: %s' % (node.ip, 'root', self.root_pass))
            db = MySQLdb.connect(node.ip, 'root', self.root_pass)
            exc = db.cursor()
            exc.execute("SHOW STATUS LIKE 'wsrep_local_recv_queue_avg';")
            localLoad=exc.fetchone()[1]
            loads.append(localLoad)
            load=load+float(localLoad)
            #select
            exc.execute("SHOW GLOBAL STATUS LIKE 'Com_select';")
            localSelect=exc.fetchone()[1]
            selects.append(localSelect)
            select=select+float(localSelect)
            #insert
            exc.execute("SHOW GLOBAL STATUS LIKE 'Com_insert';")
            localInsert=exc.fetchone()[1]
            inserts.append(localInsert)
            insert=insert+float(localInsert)
            #delete
            exc.execute("SHOW GLOBAL STATUS LIKE 'Com_delete';")
            localDelete=exc.fetchone()[1]
            deletes.append(localDelete)
            delete=delete+float(localDelete)
            #update
            exc.execute("SHOW GLOBAL STATUS LIKE 'Com_update';")
            localUpdate=exc.fetchone()[1]
            updates.append(localUpdate)
            update=update+float(localUpdate)

        if len(nodes)!=0 :
            l=len(nodes)
        else:
            l=1
        meanLoad=load/l
        meanSelect=select/l
        meanUpdate=update/l
        meanDelete=delete/l
        meanInsert=insert/l
        return HttpJsonResponse({
                     'loads': loads,
                     'meanLoad': meanLoad,
                     'updates': updates,
                     'meanUpdate' : meanUpdate,
                     'selects': selects,
                     'meanSelect': meanSelect,
                     'deletes' : deletes,
                     'meanDelete' : meanDelete,
                     'inserts': inserts,
                     'meanInsert': meanInsert
                                     })

    @expose('GET')
    def getGangliaParams(self, kwargs):
        """
        TODO: it allows to obtain Monitoring info from Ganglia.

        No parameters.

        Returns a dict with keys:
            Ganglia : xml
        """

        try:
            exp_params = []
            check_arguments(exp_params, kwargs)
            import commands
            xml=commands.getstatusoutput("curl -s telnet://localhost:8651/")
        except Exception as ex:
            return HttpErrorResponse("%s" % ex)

        return HttpJsonResponse({'Ganglia': xml})

    @expose('GET')
    def get_service_performance(self, kwargs):
        """
        TODO: placeholder for obtaining performance metrics.

        No parameters.

        Returns a dict with keys:
            request_rate : int
            error_rate : int
            throughput : int
            response_time : int
        """

        try:
            exp_params = []
            check_arguments(exp_params, kwargs)
        except Exception as ex:
            return HttpErrorResponse("%s" % ex)

        return HttpJsonResponse({
                 'request_rate': 0,
                                 'error_rate': 0,
                                 'throughput': 0,
                                 'response_time': 0,
                                 })

    def check_remove_nodes(self, node_roles):
        nodes = node_roles.get(self.ROLE_MYSQL, 0)
        total_nodes = len(self.config.get_nodes())
        if nodes >= total_nodes: # at least one mysql node should remain
            raise WrongNrNodesException(nodes, total_nodes - 1, self.ROLE_MYSQL)

        glb_nodes = node_roles.get(self.ROLE_GLB, 0)
        total_glb_nodes = len(self.config.get_glb_nodes())
        if glb_nodes > total_glb_nodes:
            raise WrongNrNodesException(glb_nodes, total_glb_nodes, self.ROLE_GLB)

    def on_remove_nodes(self, node_roles):
        # We assume arguments are checked here!
        nodes = node_roles.get(self.ROLE_MYSQL, 0)
        glb_nodes = node_roles.get(self.ROLE_GLB, 0)
        rm_reg_nodes = self.config.get_nodes()[:nodes]
        rm_glb_nodes = self.config.get_glb_nodes()[:glb_nodes]
        return self._do_remove_nodes(rm_reg_nodes,rm_glb_nodes)

    def _do_remove_nodes(self, rm_reg_nodes, rm_glb_nodes):
        glb_nodes = self.config.get_glb_nodes()
        nodesIp = ["%s:%s" % (node.ip, self.config.MYSQL_PORT)  # FIXME: find real mysql port instead of default 3306
                         for node in rm_reg_nodes]
        for glb in glb_nodes:
                agent.remove_glbd_nodes(glb.ip, self.config.AGENT_PORT, nodesIp)
        nodes = rm_reg_nodes + rm_glb_nodes
        for node in nodes:
            agent.stop(node.ip, self.config.AGENT_PORT)
        self.config.remove_nodes(nodes)
        if (len(self.config.get_nodes()) +len(self.config.get_glb_nodes())==0 ):
            self.state_set(self.S_STOPPED)
        else:
            self.state_set(self.S_RUNNING)
        return nodes

    @expose('POST')
    def migrate_nodes(self, kwargs):
        """
        Migrate nodes from one cloud to another.

        Parameters
        ----------
        nodes : list of dict with keys
            from_cloud : string
                name of origin cloud
            vmid : string
                identifier of the node to migrate inside the origin cloud
            to_cloud : string
                name of destination cloud

         delay : int
             (optional with default value to 0) time in seconds to delay
             the removal of the old node. 0 means "remove old node as
             soon as the new node is up", 60 means "remove old node
             after 60 seconds after the new node is up". Useful to keep
             the old node active while the DNS and its caches that
             still have the IP address of the old node are updated
             to the IP address of the new node.
        """
        try:
            exp_keys = ['from_cloud', 'vmid', 'to_cloud']
            exp_params = [('nodes', is_list_dict2(exp_keys)),
                          ('delay', is_pos_nul_int, 0)]
            nodes, delay = check_arguments(exp_params, kwargs)
            self.check_state([self.S_RUNNING])
        except Exception, ex:
            return HttpErrorResponse('%s' % ex)

        service_nodes = self.config.get_nodes()
        self.logger.debug("While migrate_nodes, service_nodes = %s." % service_nodes)
        migration_plan = []
        for migr in nodes:
            from_cloud_name = migr['from_cloud']
            node_id = migr['vmid']
            dest_cloud_name = migr['to_cloud']
            if from_cloud_name == '' or dest_cloud_name == '':
                return HttpErrorResponse('Missing cloud name in parameter "nodes": from_cloud="%s" to_cloud="%s"'
                                         % (from_cloud_name, dest_cloud_name))
            try:
                candidate_nodes = [node for node in service_nodes
                                   if node.cloud_name == from_cloud_name
                                   and node.vmid == node_id]
                if candidate_nodes == []:
                    avail_nodes = ', '.join([node.cloud_name + ':' + node.vmid
                                             for node in service_nodes])
                    raise Exception("Node %s in cloud %s is not a valid node"
                                    " of this service. It should be one of %s"
                                    % (node_id, from_cloud_name, avail_nodes))
                node = candidate_nodes[0]
                dest_cloud = self.controller.get_cloud_by_name(dest_cloud_name)
            except Exception, ex:
                return HttpErrorResponse("%s" % ex)
            migration_plan.append((node, dest_cloud))

        if migration_plan == []:
            return HttpErrorResponse('ERROR: argument is missing the nodes to migrate.')

        self.state_set(self.S_ADAPTING)
        Thread(target=self._do_migrate_nodes, args=[migration_plan, delay]).start()
        return HttpJsonResponse()

    def _do_migrate_nodes(self, migration_plan, delay):
        self.logger.info("Migration: starting with plan %s and delay %s."
                         % (migration_plan, delay))
        # TODO: use instead collections.Counter with Python 2.7
        clouds = [dest_cloud for (_node, dest_cloud) in migration_plan]
        new_vm_nb = collections.defaultdict(int)
        for cloud in clouds:
            new_vm_nb[cloud] += 1
        try:
            new_nodes = []
            # TODO: make it parallel
            for cloud, count in new_vm_nb.iteritems():
                self.controller.add_context_replacement(dict(mysql_username='root',
                                                             mysql_password=self.root_pass),
                                                        cloud=cloud)

                new_nodes.extend(self.controller.create_nodes(count,
                                                              agent.check_agent_process,
                                                              self.config.AGENT_PORT,
                                                              cloud))
                self._start_mysqld(new_nodes, cloud)
                self.config.addMySQLServiceNodes(new_nodes)
        except Exception, ex:
            # error happened: rolling back...
            for node in new_nodes:
                agent.stop(node.ip, self.config.AGENT_PORT)
            self.controller.delete_nodes(new_nodes)
            self.config.remove_nodes(new_nodes)
            self.logger.exception('_do_migrate_nodes: Could not'
                                  ' start nodes: %s' % ex)
            self.state_set(self.S_RUNNING)
            raise ex

        self.logger.debug("Migration: new nodes %s created and"
                          " configured successfully." % (new_nodes))

        # New nodes successfully created
        # Now scheduling the removing of old nodes
        old_nodes = [node for node, _dest_cloud in migration_plan]
        if delay == 0:
            self.logger.debug("Migration: removing immediately"
                              " the old nodes: %s." % old_nodes)
            self._do_migrate_finalize(old_nodes)
        else:
            self.logger.debug("Migration: setting a timer to remove"
                              " the old nodes %s after %d seconds."
                              % (old_nodes, delay))
            self._start_timer(delay, self._do_migrate_finalize, old_nodes)
            self.state_set(self.S_RUNNING)

    def _do_migrate_finalize(self, old_nodes):
        self.state_set(self.S_ADAPTING)
        for node in old_nodes:
            agent.stop(node.ip, self.config.AGENT_PORT)
        self.controller.delete_nodes(old_nodes)
        self.config.remove_nodes(old_nodes)
        self.state_set(self.S_RUNNING)
        self.logger.info("Migration: old nodes %s have been removed."
                         " END of migration." % old_nodes)

    def _start_timer(self, delay, callback, nodes):
        timer = Timer(delay, callback, args=[nodes])
        timer.start()

    @expose('GET')
    def get_service_info(self, kwargs):
        """
        Get service information.

        No parameters.

        Returns a dict with key 'state' containing the service current state,
        and key 'type' containing this service type.
        """
        try:
            exp_params = []
            check_arguments(exp_params, kwargs)
        except Exception as ex:
            return HttpErrorResponse("%s" % ex)

        return HttpJsonResponse({'state': self.state, 'type': 'mysql'})

    def on_stop(self):
        res = self._do_remove_nodes(self.config.serviceNodes.values(),self.config.glb_service_nodes.values())
        self.config.serviceNodes = {}
        self.config.glb_service_nodes = {}
        return res

    @expose('POST')
    def set_password(self, kwargs):
        self.logger.debug('Setting password')
        try:
            exp_params = [('user', is_string),
                          ('password', is_string)]
            user, password = check_arguments(exp_params, kwargs)
            self.check_state([self.S_RUNNING])
        except Exception as ex:
            return HttpErrorResponse("%s" % ex)

        one_node = self.config.get_nodes()[0]

        try:
            agent.set_password(one_node.ip, self.config.AGENT_PORT, user, password)
        except Exception as ex:
            self.logger.exception()
            return HttpErrorResponse('Failed to set new password: %s.' % ex)
        else:
            return HttpJsonResponse()

    @expose('UPLOAD')
    def load_dump(self, kwargs):
        """
        Load a dump into the database.

        Parameters
        ----------
        mysqldump_file : uploaded file
            name of uploaded file containing the database dump.
        """
        self.logger.debug('Uploading mysql dump')
        try:
            exp_params = [('mysqldump_file', is_uploaded_file)]
            mysqldump_file = check_arguments(exp_params, kwargs)
            self.check_state([self.S_RUNNING])
        except Exception as ex:
            return HttpErrorResponse("%s" % ex)

        fd, filename = tempfile.mkstemp(dir='/tmp')
        fd = os.fdopen(fd, 'w')
        upload = mysqldump_file.file
        bytes = upload.read(2048)
        while len(bytes) != 0:
            fd.write(bytes)
            bytes = upload.read(2048)
        fd.close()

        # at least one agent since state is S_RUNNING
        one_node = self.config.get_nodes()[0]
        try:
            agent.load_dump(one_node.ip, self.config.AGENT_PORT, filename)
        except Exception as ex:
            err_msg = 'Could not upload mysqldump_file: %s.' % ex
            self.logger.exception(err_msg)
            return HttpErrorResponse(err_msg)
        return HttpJsonResponse()

    @expose('GET')
    def sqldump(self, kwargs):
        """
        Dump the database.

        No parameters.

        Returns the dump of the database.
        """
        try:
            exp_params = []
            check_arguments(exp_params, kwargs)
            self.check_state([self.S_RUNNING])
        except Exception as ex:
            return HttpErrorResponse("%s" % ex)

        # at least one agent since state is S_RUNNING
        one_node = self.config.get_nodes()[0]
        # adding option '--skip-lock-tables' to avoid issue
        #  mysqldump: Got error: 1142: SELECT,LOCK TABL command denied to user
        #   'root'@'10.158.0.28' for table 'cond_instances'
        #   when using LOCK TABLES
        # FIXME: is it MySQL 5.1 only? does it still occur with MySQL 5.5?
        cmd = 'mysqldump -u root -h %s --password=%s -A --skip-lock-tables' \
              % (one_node.ip, self.root_pass)
        out, error, return_code = run_cmd_code(cmd)

        if return_code == 0:
            return HttpJsonResponse(out)
        else:
            return HttpErrorResponse("Failed to run mysqldump: %s." % error)


    @expose('GET')
    def remove_specific_nodes(self, kwargs):
        """
        Remove MySQL Galera nodes.

        Parameters
        ----------
        nodes : int
            number of regular nodes to remove (default 0)
        glb_nodes : int
            number of Galera Load Balancer nodes to remove (default 0)

        Returns an error if "nodes + glb_nodes == 0".
        """
        try:
            exp_params = [('ip', is_string)]
            ip = check_arguments(exp_params, kwargs)
            self.check_state([self.S_RUNNING])
        except Exception as ex:
            return HttpErrorResponse("%s" % ex)

        self.state_set(self.S_ADAPTING)
        rm_reg_nodes = self.config.get_nodes()
        rm_glb_nodes = self.config.get_glb_nodes()
        is_in_glb=False
        is_in_reg=False
        for node in self.config.get_nodes():
            if node.ip == ip :
                nodeTarget=node
                is_in_reg=True
        for node in self.config.get_glb_nodes():
            if node.ip== ip :
                nodeTarget=node
                is_in_glb=True
        if is_in_reg==False and is_in_glb==False :
            return HttpErrorResponse("%s" % "Sorry invalid ip !!!")
        elif is_in_reg == True :
            rm_reg_nodes=[nodeTarget]
            rm_glb_nodes=[]
        else :
            rm_glb_nodes=[nodeTarget]
            rm_reg_nodes=[]
        Thread(target=self._do_remove_nodes, args=[rm_reg_nodes,rm_glb_nodes]).start()
        return HttpJsonResponse()

    @expose('GET')
    def setMySqlParams(self, kwargs):
        """
        set a specified global variable of mysql to the value provided

        Parameters
        ----------
        variable : string
            name of MySQL variable
        value : string
            value to set

        """
        try:
            exp_params = [('variable', is_string),('value', is_string)]
            variable, value = check_arguments(exp_params, kwargs)
            self.check_state([self.S_RUNNING])
            nodes = self.config.get_nodes()
            for node in nodes:
                db = MySQLdb.connect(node.ip, 'root', self.root_pass)
                exc = db.cursor()
                exc.execute('set global ' + variable + ' = ' + value + ';')
            '''glb_nodes = self.config.get_glb_nodes()
            n=len(nodes)*value
                for node in glb_nodes:
                    db = MySQLdb.connect(node.ip, 'root', self.root_pass,port=8010)
                    exc = db.cursor()
                    exc.execute('set global ' + variable + ' = ' + n + ';')'''
        except Exception as ex:
            return HttpErrorResponse("%s" % ex)

        return HttpJsonResponse("OK!")
