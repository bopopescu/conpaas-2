"""
Copyright (c) 2010-2015, Contrail consortium.
All rights reserved.

Redistribution and use in source and binary forms,
with or without modification, are permitted provided
that the following conditions are met:

 1. Redistributions of source code must retain the
    above copyright notice, this list of conditions
    and the following disclaimer.
 2. Redistributions in binary form must reproduce
    the above copyright notice, this list of
    conditions and the following disclaimer in the
    documentation and/or other materials provided
    with the distribution.
 3. Neither the name of the Contrail consortium nor the
    names of its contributors may be used to endorse
    or promote products derived from this software
    without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND
CONTRIBUTORS "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES,
INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF
MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR
CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING,
BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY,
WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
(INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT
OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
POSSIBILITY OF SUCH DAMAGE.
"""

from threading import Thread
import memcache
from shutil import rmtree
import pickle
import zipfile
import tarfile
import tempfile
import stat
import os.path
import time

from conpaas.core.expose import expose
from conpaas.core.controller import Controller
from conpaas.core.manager import BaseManager, ManagerException

from conpaas.core import git
from conpaas.core.https.server import HttpJsonResponse, HttpErrorResponse,\
    HttpFileDownloadResponse, FileUploadField
from conpaas.services.generic.misc import archive_open, archive_get_members,\
    archive_close, archive_get_type, archive_extract_file

from conpaas.core.log import create_logger
from conpaas.services.generic.agent import client
from conpaas.services.generic.manager.config import CodeVersion,\
    ServiceConfiguration, VolumeInfo

class GenericManager(BaseManager):
    """Manager class with the following exposed methods:

    startup() -- POST
    shutdown() -- POST
    add_nodes(count) -- POST
    remove_nodes(count) -- POST
    list_nodes() -- GET
    get_service_info() -- GET
    get_node_info(serviceNodeId) -- GET
    list_code_versions() -- GET
    list_authorized_keys() -- GET
    upload_authorized_key(key) -- UPLOAD
    git_push_hook() -- POST
    upload_code_version(code, description) -- UPLOAD
    download_code_version(codeVersionId) -- GET
    enable_code(codeVersionId) -- POST
    delete_code_version(codeVersionId) -- POST
    list_volumes() -- GET
    generic_create_volume(volumeName, volumeSize, agentId) -- POST
    generic_delete_volume(volumeName) -- POST
    execute_script(command, parameters) -- POST
    get_script_status() -- GET
    get_agent_log(filename) -- GET
    """
    # Manager states
    S_INIT = 'INIT'         # manager initialized but not yet started
    S_PROLOGUE = 'PROLOGUE' # manager is starting up
    S_RUNNING = 'RUNNING'   # manager is running
    S_ADAPTING = 'ADAPTING' # manager is in a transient state - frontend will
                            # keep polling until manager out of transient state
    S_EPILOGUE = 'EPILOGUE' # manager is shutting down
    S_STOPPED = 'STOPPED'   # manager stopped
    S_ERROR = 'ERROR'       # manager is in error state

    DEPLOYMENT_STATE = 'deployment_state'

    # String template for error messages returned when performing actions in
    # the wrong state
    WRONG_STATE_MSG = "ERROR: cannot perform %(action)s in state %(curstate)s"

    # String template for error messages returned when a required argument is
    # missing
    REQUIRED_ARG_MSG = "ERROR: %(arg)s is a required argument"

    # String template for debugging messages logged on nodes creation
    ACTION_REQUESTING_NODES = "requesting %(count)s nodes in %(action)s"

    # String used as an error message when 'interrupt' is called when no
    # scripts are currently running
    NO_SCRIPTS_ARE_RUNNING_MSG = "ERROR: No scripts are currently running inside "\
                                "agents. Nothing to interrupt."

    # String used as an error message when scripts are running inside agents
    SCRIPTS_ARE_RUNNING_MSG = "ERROR: Scripts are still running inside at "\
                                "least one agent. Please wait for them to "\
                                "finish execution or call 'interrupt' first."

    # String used as an error message when the script is already running
    SCRIPT_IS_RUNNING_MSG = "ERROR: Script '%s.sh' is already running inside "\
                            "at least one agent. Please wait for it to "\
                            "finish execution or call 'interrupt' first."

    AGENT_PORT = 5555

    # memcache keys
    CONFIG = 'config'

    def __init__(self, config_parser, **kwargs):
        """Initialize a Generic Manager.

        'config_parser' represents the manager config file.
        **kwargs holds anything that can't be sent in config_parser."""
        BaseManager.__init__(self, config_parser)
        self.controller.generate_context('generic')

        memcache_addr = config_parser.get('manager', 'MEMCACHE_ADDR')
        self.memcache = memcache.Client([memcache_addr])
        self.code_repo = config_parser.get('manager', 'CODE_REPO')

        self.state_log = []
        if kwargs['reset_config']:
            self._create_initial_configuration()

        self.nodes = []
        self.agents_info = []
        self.master_ip = None
        self._state_set(self.S_INIT)

    def _prepare_default_config_script(self, script_name):
        fileno, path = tempfile.mkstemp()
        fd = os.fdopen(fileno, 'w')
        fd.write('''#!/bin/bash
date >> /root/generic.out
echo "Executing script ${0##*/}" >> /root/generic.out
echo "Parameters ($#): $@" >> /root/generic.out
echo "My IP is $MY_IP" >> /root/generic.out
echo "My role is $MY_ROLE" >> /root/generic.out
echo "My master IP is $MASTER_IP" >> /root/generic.out
echo "Information about other agents is stored at /var/cache/cpsagent/agents.json" >> /root/generic.out
cat /var/cache/cpsagent/agents.json >> /root/generic.out
echo "" >> /root/generic.out
echo "" >> /root/generic.out
''')
        fd.close()
        os.chmod(path, stat.S_IRWXU | stat.S_IROTH | stat.S_IXOTH)
        return path

    def _create_initial_configuration(self):
        self.logger.info("Creating initial configuration")

        config = ServiceConfiguration()

        if len(config.codeVersions) > 0:
            return

        if not os.path.exists(self.code_repo):
            os.makedirs(self.code_repo)

        tfile = tarfile.TarFile(name=os.path.join(self.code_repo, 'code-default'),
                mode='w')

        scripts = ['init.sh', 'notify.sh', 'run.sh', 'interrupt.sh', 'cleanup.sh']
        for script in scripts:
            path = self._prepare_default_config_script(script)
            tfile.add(path, script)
            os.remove(path)

        tfile.close()
        config.codeVersions['code-default'] = CodeVersion('code-default',
                'code-default.tar', 'tar', description='Initial version')
        config.currentCodeVersion = 'code-default'
        self._configuration_set(config)

    @expose('POST')
    def startup(self, kwargs):
        """Start the Generic service"""
        self.logger.info('Manager starting up')

        # Starting up the service makes sense only in the INIT or STOPPED
        # states
        dstate = self._state_get()
        if dstate != self.S_INIT and dstate != self.S_STOPPED:
            ex = ManagerException(ManagerException.E_STATE_ERROR)
            return HttpErrorResponse(ex.message)

        # Check if the specified cloud, if any, is available
        if 'cloud' in kwargs:
            try:
                self._init_cloud(kwargs['cloud'])
            except Exception:
                return HttpErrorResponse(
                    "A cloud named '%s' could not be found" % kwargs['cloud'])

        self._state_set(self.S_PROLOGUE, msg='Starting up')

        Thread(target=self._do_startup, args=[kwargs]).start()

        return HttpJsonResponse({ 'state': self._state_get() })

    def _do_startup(self, kwargs):
        """Start up the service. The first node will be the master node."""

        nr_instances = 1
#        nr_instances = 0
#        if kwargs and kwargs.get('manifest'):
#            instances = kwargs.get('manifest').get('StartupInstances')
#            tar_path =  kwargs.get('manifest').get('Archive')
#            for role in instances:
#                nr_instances += int(instances[role])

        vals = { 'action': '_do_startup', 'count': nr_instances }
        self.logger.debug(self.ACTION_REQUESTING_NODES % vals)

        cloud = kwargs.pop('cloud', 'iaas')
        cloud = self._init_cloud(cloud)

        try:
            #nodes = []
            #for i in range(1, nr_instances):
            #    nodes.append( self.controller.create_nodes(1,
            #        client.check_agent_process, self.AGENT_PORT, cloud))
            nodes = self.controller.create_nodes(nr_instances,
                    client.check_agent_process, self.AGENT_PORT, cloud)

            config = self._configuration_get()

            roles = {'master':'1'}

            agents_info = self._update_agents_info(nodes, roles)

            self._init_agents(config, nodes, agents_info)
            self._update_code(config, nodes)

            # Extend the nodes list with the newly created one
            self.nodes += nodes
            self.agents_info += agents_info
            self.master_ip = nodes[0].ip
            self._state_set(self.S_RUNNING)
        except Exception, err:
            self.logger.exception('_do_startup: Failed to create agents: %s' % err)
            self._state_set(self.S_ERROR)

    def _update_agents_info(self, nodes, roles):
        id_ip = []
        for node in nodes:
            id_ip.append( { 'id': node.id, 'ip': node.ip })

        id_ip_role = []
        for role in roles:
            for _ in range(int(roles[role])):
                if len(id_ip):
                    node_ip_id = id_ip.pop(0)
                    node_ip_id.update({'role':role})
                    id_ip_role.append(node_ip_id)

        return id_ip_role

    def _init_agents(self, config, nodes, agents_info):
        self.logger.info("Initializing agents %s" %
                [ node.id for node in nodes ])

        for serviceNode in nodes:
            try:
                client.init_agent(serviceNode.ip, self.AGENT_PORT, agents_info)
            except client.AgentException:
                self.logger.exception('Failed initialize agent at node %s'
                        % str(serviceNode))
                self._state_set(self.S_ERROR, msg='Failed to initialize agent at node %s'
                        % str(serviceNode))
                raise

    @expose('POST')
    def shutdown(self, kwargs):
        """Switch to EPILOGUE and call a thread to delete all nodes"""
        if len(kwargs) != 0:
            ex = ManagerException(ManagerException.E_ARGS_UNEXPECTED,
                                  kwargs.keys())
            return HttpErrorResponse(ex.message)

        # Shutdown only if RUNNING
        if self._state_get() != self.S_RUNNING:
            vals = { 'curstate': self._state_get(), 'action': 'shutdown' }
            return HttpErrorResponse(self.WRONG_STATE_MSG % vals)

        self.logger.info('Manager shutting down')

        self._state_set(self.S_EPILOGUE)
        Thread(target=self._do_shutdown, args=[]).start()

        return HttpJsonResponse({ 'state': self._state_get() })

    def _do_shutdown(self):
        """Delete all nodes and switch to status STOPPED"""
        # Detach and delete all volumes

        config = self._configuration_get()
        self.logger.info("Deleting volumes: %s" %
                [ volume.volumeName for volume in config.volumes.values() ])
        for volume in config.volumes.values():
            self.__delete_volume_internal(volume)
        config.volumes = {}
        self._configuration_set(config)

        self.logger.info("Removing nodes: %s" %
                [ node.id for node in self.nodes ])
        self.controller.delete_nodes(self.nodes)
        self.nodes = []        # Not only delete the nodes, but clear the list too
        self.agents_info = []
        self.master_ip = None
        self._state_set(self.S_STOPPED)

    def __check_count_in_args(self, kwargs):
        """Return 'count' if all is good. HttpErrorResponse otherwise."""
        count = None

        if 'count' in kwargs:
            count = kwargs.pop('count')
        # The frontend sends count under 'node'.
        elif 'node' in kwargs:
            count = kwargs.pop('node')
        else:
            return HttpErrorResponse(self.REQUIRED_ARG_MSG % { 'arg': 'count' })

        if not isinstance(count, int):
            return HttpErrorResponse(
                "ERROR: Expected an integer value for 'count'")

        return count

    @expose('POST')
    def add_nodes(self, kwargs):
        """Add kwargs['count'] nodes to this deployment"""

        # Adding nodes makes sense only in the RUNNING state
        if self._state_get() != self.S_RUNNING:
            vals = { 'curstate': self._state_get(), 'action': 'add_nodes' }
            return HttpErrorResponse(self.WRONG_STATE_MSG % vals)

        # Ensure 'count' is valid
        count_or_err = self.__check_count_in_args(kwargs)
        if isinstance(count_or_err, HttpErrorResponse):
            return count_or_err

        count = count_or_err

        cloud = kwargs.pop('cloud', 'iaas')
        try:
            cloud = self._init_cloud(cloud)
        except Exception as ex:
                return HttpErrorResponse(
                    "A cloud named '%s' could not be found" % cloud)

        self.logger.info("Going to add %s new nodes on cloud '%s'"
                % (count, cloud))

        start_role = 'node'
        nodes = {start_role: str(count)}

        self._state_set(self.S_ADAPTING)
        Thread(target=self._do_add_nodes, args=[nodes, start_role, cloud]).start()

        return HttpJsonResponse({ 'state': self._state_get() })

    def _do_add_nodes(self, nodes, start_role, cloud):
        """Add 'count' Generic Nodes to this deployment"""
        count = 0
        for node in nodes:
                count += int(nodes[node])

        if count:
            # Startup agents
            node_instances = self.controller.create_nodes(count,
                client.check_agent_process, self.AGENT_PORT, cloud)
            agents_info = self._update_agents_info(node_instances, nodes)

            nodes_before = list(self.nodes)
            self.nodes += node_instances
            self.agents_info += agents_info

            config = self._configuration_get()
            self._init_agents(config, node_instances, self.agents_info)
            self._update_code(config, node_instances)

        self._do_execute_script('notify', nodes_before)
        self._state_set(self.S_RUNNING)

    @expose('POST')
    def remove_nodes(self, kwargs):
        """Remove kwargs['count'] nodes from this deployment"""

        # Removing nodes only if RUNNING
        if self._state_get()!= self.S_RUNNING:
            vals = { 'curstate': self._state_get(), 'action': 'remove_nodes' }
            return HttpErrorResponse(self.WRONG_STATE_MSG % vals)

        # Ensure 'count' is valid
        count_or_err = self.__check_count_in_args(kwargs)
        if isinstance(count_or_err, HttpErrorResponse):
            return count_or_err

        count = count_or_err

        if count > len(self.nodes) - 1:
            return HttpErrorResponse("ERROR: Cannot remove so many nodes")

        self.logger.info('Going to remove %s nodes' % count)

        self._state_set(self.S_ADAPTING)

        Thread(target=self._do_remove_nodes, args=[count]).start()

        return HttpJsonResponse({ 'state': self._state_get() })

    def _do_remove_nodes(self, count):
        """Remove 'count' nodes, starting from the end of the list. This way
        the Generic master gets removed last."""
        for _ in range(count):
            # detach and delete any attached volumes
            node = self.nodes[-1]
            config = self._configuration_get()
            attached_volumes = [
                volume for volume in config.volumes.values()
                       if volume.agentId == node.id
            ]
            for volume in attached_volumes:
                self.__delete_volume_internal(volume)
                config.volumes.pop(volume.volumeName)
            self._configuration_set(config)

            self.nodes.pop()
            self.agents_info.pop()
            self.logger.info("Removing node with IP %s" % node.ip)
            self.controller.delete_nodes([ node ])
        if not self.nodes:
            self.master_ip = None
            self._state_set(self.S_STOPPED)
        else:
            self._do_execute_script('notify', self.nodes)
            self._state_set(self.S_RUNNING)

    def __is_master(self, node):
        """Return True if the given node is the Generic master"""
        return node.ip == self.master_ip

    @expose('GET')
    def list_nodes(self, kwargs):
        """Return a list of running nodes"""
        if self._state_get() != self.S_RUNNING:
            vals = { 'curstate': self._state_get(), 'action': 'list_nodes' }
            return HttpErrorResponse(self.WRONG_STATE_MSG % vals)

        if len(kwargs) != 0:
            ex = ManagerException(ManagerException.E_ARGS_UNEXPECTED,
                                  kwargs.keys())
            return HttpErrorResponse(ex.message)

        generic_nodes = [
            node.id for node in self.nodes if not self.__is_master(node)
        ]
        generic_master = [
            node.id for node in self.nodes if self.__is_master(node)
        ]

        return HttpJsonResponse({
            'master': generic_master,
            'node': generic_nodes
        })

    @expose('GET')
    def get_service_info(self, kwargs):
        """Return the service state and type"""
        if len(kwargs) != 0:
            ex = ManagerException(ManagerException.E_ARGS_UNEXPECTED,
                                  kwargs.keys())
            return HttpErrorResponse(ex.message)

        return HttpJsonResponse({'state': self._state_get(), 'type': 'generic'})

    @expose('GET')
    def get_node_info(self, kwargs):
        """Return information about the node identified by the given
        kwargs['serviceNodeId']"""

        # serviceNodeId is a required parameter
        if 'serviceNodeId' not in kwargs:
            vals = { 'arg': 'serviceNodeId' }
            return HttpErrorResponse(self.REQUIRED_ARG_MSG % vals)
        serviceNodeId = kwargs.pop('serviceNodeId')

        if len(kwargs) != 0:
            ex = ManagerException(ManagerException.E_ARGS_UNEXPECTED,
                                  kwargs.keys())
            return HttpErrorResponse(ex.message)

        serviceNode = None
        for node in self.nodes:
            if serviceNodeId == node.id:
                serviceNode = node
                break

        if serviceNode is None:
            return HttpErrorResponse(
                'ERROR: Cannot find node with serviceNode=%s' % serviceNodeId)

        return HttpJsonResponse({
            'serviceNode': {
                'id': serviceNode.id,
                'ip': serviceNode.ip,
                'is_master': self.__is_master(serviceNode)
            }
        })

    @expose('GET')
    def list_code_versions(self, kwargs):
        if len(kwargs) != 0:
            ex = ManagerException(ManagerException.E_ARGS_UNEXPECTED,
                                  kwargs.keys())
            return HttpErrorResponse(ex.message)

        config = self._configuration_get()
        versions = []
        for version in config.codeVersions.values():
            item = {'codeVersionId': version.id, 'filename': version.filename,
                    'description': version.description, 'time': version.timestamp}
            if version.id == config.currentCodeVersion:
                item['current'] = True
            versions.append(item)
        versions.sort(
            cmp=(lambda x, y: cmp(x['time'], y['time'])), reverse=True)
        return HttpJsonResponse({'codeVersions': versions})

    @expose('GET')
    def list_authorized_keys(self, kwargs):
        if len(kwargs) != 0:
            ex = ManagerException(ManagerException.E_ARGS_UNEXPECTED,
                                  kwargs.keys())
            return HttpErrorResponse(ex.message)

        return HttpJsonResponse({'authorizedKeys' : git.get_authorized_keys()})

    @expose('UPLOAD')
    def upload_authorized_key(self, kwargs):
        if 'key' not in kwargs:
            ex = ManagerException(ManagerException.E_ARGS_MISSING, 'key')
            return HttpErrorResponse(ex.message)

        key = kwargs.pop('key')

        if len(kwargs) != 0:
            ex = ManagerException(ManagerException.E_ARGS_UNEXPECTED,
                                  kwargs.keys())
            return HttpErrorResponse(ex.message)
        if not isinstance(key, FileUploadField):
            ex = ManagerException(
                ManagerException.E_ARGS_INVALID, detail='key should be a file')
            return HttpErrorResponse(ex.message)

        key_lines = key.file.readlines()
        num_added = git.add_authorized_keys(key_lines)

        return HttpJsonResponse({'outcome': "%s keys added to authorized_keys" % num_added})

    @expose('POST')
    def git_push_hook(self, kwargs):
        if len(kwargs) != 0:
            ex = ManagerException(
                ManagerException.E_ARGS_UNEXPECTED, kwargs.keys())
            return HttpErrorResponse(ex.message)

        config = self._configuration_get()

        repo = git.DEFAULT_CODE_REPO
        revision = git.git_code_version(repo)
        codeVersionId = "git-%s" % revision

        config.codeVersions[codeVersionId] = CodeVersion(id=codeVersionId,
                                                         filename=revision,
                                                         atype="git",
                                                         description=git.git_last_description(repo))

        self._configuration_set(config)
        return HttpJsonResponse({'codeVersionId': codeVersionId})

    @expose('UPLOAD')
    def upload_code_version(self, kwargs):
        if 'code' not in kwargs:
            ex = ManagerException(ManagerException.E_ARGS_MISSING, 'code')
            return HttpErrorResponse(ex.message)
        code = kwargs.pop('code')
        if not isinstance(code, FileUploadField):
            ex = ManagerException(ManagerException.E_ARGS_INVALID,
                                  detail='codeVersionId should be a file')
            return HttpErrorResponse(ex.message)

        if 'description' in kwargs:
            description = kwargs.pop('description')
        else:
            description = ''

        if len(kwargs) != 0:
            ex = ManagerException(ManagerException.E_ARGS_UNEXPECTED,
                                  kwargs.keys())
            return HttpErrorResponse(ex.message)

        config = self._configuration_get()
        fd, name = tempfile.mkstemp(prefix='code-', dir=self.code_repo)
        fd = os.fdopen(fd, 'w')
        upload = code.file
        codeVersionId = os.path.basename(name)

        bytes = upload.read(2048)
        while len(bytes) != 0:
            fd.write(bytes)
            bytes = upload.read(2048)
        fd.close()

        arch = archive_open(name)
        if arch is None:
            os.remove(name)
            ex = ManagerException(ManagerException.E_ARGS_INVALID,
                                  detail='Invalid archive format')
            return HttpErrorResponse(ex.message)

        for fname in archive_get_members(arch):
            if fname.startswith('/') or fname.startswith('..'):
                archive_close(arch)
                os.remove(name)
                ex = ManagerException(ManagerException.E_ARGS_INVALID,
                    detail='Absolute file names are not allowed in archive members')
                return HttpErrorResponse(ex.message)
        archive_close(arch)
        config.codeVersions[codeVersionId] = CodeVersion(
            codeVersionId, os.path.basename(code.filename), archive_get_type(name),
            description=description)
        self._configuration_set(config)
        return HttpJsonResponse({'codeVersionId': os.path.basename(codeVersionId)})

    @expose('GET')
    def download_code_version(self, kwargs):
        if 'codeVersionId' not in kwargs:
            ex = ManagerException(ManagerException.E_ARGS_MISSING,
                                  'codeVersionId')
            return HttpErrorResponse(ex.message)
        if isinstance(kwargs['codeVersionId'], dict):
            ex = ManagerException(ManagerException.E_ARGS_INVALID,
                                  detail='codeVersionId should be a string')
            return HttpErrorResponse(ex.message)
        codeVersionId = kwargs.pop('codeVersionId')

        if len(kwargs) != 0:
            ex = ManagerException(ManagerException.E_ARGS_UNEXPECTED,
                                  kwargs.keys())
            return HttpErrorResponse(ex.message)

        config = self._configuration_get()

        if codeVersionId not in config.codeVersions:
            ex = ManagerException(ManagerException.E_ARGS_INVALID,
                                  detail='Invalid codeVersionId')
            return HttpErrorResponse(ex.message)

        if config.codeVersions[codeVersionId].type == 'git':
            return HttpErrorResponse(
                'ERROR: To download this code, please clone the git repository');

        filename = os.path.abspath(os.path.join(self.code_repo, codeVersionId))
        if not filename.startswith(self.code_repo + '/') or not os.path.exists(filename):
            ex = ManagerException(ManagerException.E_ARGS_INVALID,
                                  detail='Invalid codeVersionId')
            return HttpErrorResponse(ex.message)
        return HttpFileDownloadResponse(config.codeVersions[codeVersionId].filename,
                filename)

    @expose('POST')
    def enable_code(self, kwargs):
        if 'codeVersionId' not in kwargs:
            ex = ManagerException(ManagerException.E_ARGS_MISSING,
                                  'codeVersionId')
            return HttpErrorResponse(ex.message)
        codeVersionId = kwargs.pop('codeVersionId')

        if len(kwargs) != 0:
            ex = ManagerException(ManagerException.E_ARGS_UNEXPECTED,
                                  kwargs.keys())
            return HttpErrorResponse(ex.message)

        config = self._configuration_get()
        if codeVersionId not in config.codeVersions:
            ex = ManagerException(ManagerException.E_ARGS_INVALID,
                    detail='Unknown code version identifier "%s"' % codeVersionId)
            return HttpErrorResponse(ex.message)

        dstate = self._state_get()
        if dstate == self.S_INIT or dstate == self.S_STOPPED:
            config.currentCodeVersion = codeVersionId
            self._configuration_set(config)
        elif dstate == self.S_RUNNING:
            if self._are_scripts_running():
                self.logger.info("Code activation is disabled when scripts are "\
                        "running")
                return HttpErrorResponse(self.SCRIPTS_ARE_RUNNING_MSG);
            self._state_set(self.S_ADAPTING, msg='Updating configuration')
            Thread(target=self._do_enable_code, args=[config, codeVersionId]).start()
        else:
            return HttpErrorResponse(ManagerException(ManagerException.E_STATE_ERROR).message)
        return HttpJsonResponse()

    def _do_enable_code(self, config, codeVersionId):
        config.currentCodeVersion = codeVersionId
        self._update_code(config, self.nodes)
        self._state_set(self.S_RUNNING)
        self._configuration_set(config)

    def _update_code(self, config, nodes):
        self.logger.info("Updating code to version '%s' at agents %s" %
                (config.currentCodeVersion, [ node.id for node in nodes ]))

        for node in nodes:
            # Push the current code version via GIT if necessary
            if config.codeVersions[config.currentCodeVersion].type == 'git':
                filepath = config.codeVersions[config.currentCodeVersion].filename
                _, err = git.git_push(git.DEFAULT_CODE_REPO, node.ip)
                if err:
                    self.logger.debug('git-push to %s: %s' % (node.ip, err))
            else:
                filepath = os.path.join(self.code_repo, config.currentCodeVersion)
            try:
                client.update_code(node.ip, self.AGENT_PORT, config.currentCodeVersion,
                                     config.codeVersions[config.currentCodeVersion].type,
                                     filepath)
            except client.AgentException:
                self.logger.exception('Failed to update code at node %s' % str(node))
                self._state_set(self.S_ERROR, msg='Failed to update code at node %s' % str(node))
                raise

    @expose('POST')
    def delete_code_version(self, kwargs):
        if 'codeVersionId' not in kwargs:
            ex = ManagerException(ManagerException.E_ARGS_MISSING,
                                  'codeVersionId')
            return HttpErrorResponse(ex.message)
        if isinstance(kwargs['codeVersionId'], dict):
            ex = ManagerException(ManagerException.E_ARGS_INVALID,
                                  detail='codeVersionId should be a string')
            return HttpErrorResponse(ex.message)
        codeVersionId = kwargs.pop('codeVersionId')

        if len(kwargs) != 0:
            ex = ManagerException(ManagerException.E_ARGS_UNEXPECTED,
                                  kwargs.keys())
            return HttpErrorResponse(ex.message)

        config = self._configuration_get()

        if codeVersionId not in config.codeVersions:
            ex = ManagerException(ManagerException.E_ARGS_INVALID,
                                  detail='Invalid codeVersionId')
            return HttpErrorResponse(ex.message)

        if codeVersionId == config.currentCodeVersion:
            ex = ManagerException(ManagerException.E_ARGS_INVALID,
                                  detail='Cannot remove the active code version')
            return HttpErrorResponse(ex.message)

        if not config.codeVersions[codeVersionId].type == 'git':
            filename = os.path.abspath(os.path.join(self.code_repo, codeVersionId))
            if not filename.startswith(self.code_repo + '/') or not os.path.exists(filename):
                ex = ManagerException(ManagerException.E_ARGS_INVALID,
                                      detail='Invalid codeVersionId')
                return HttpErrorResponse(ex.message)

            os.remove(filename)

        config.codeVersions.pop(codeVersionId)
        self._configuration_set(config)

        return HttpJsonResponse()

    @expose('GET')
    def list_volumes(self, kwargs):
        if len(kwargs) != 0:
            ex = ManagerException(ManagerException.E_ARGS_UNEXPECTED,
                                  kwargs.keys())
            return HttpErrorResponse(ex.message)

        config = self._configuration_get()
        volumes = []
        for volume in config.volumes.values():
            item = {'volumeName': volume.volumeName,
                    'volumeSize': volume.volumeSize,
                    'agentId': volume.agentId}
            volumes.append(item)
        return HttpJsonResponse({'volumes': volumes})

    @expose('POST')
    def generic_create_volume(self, kwargs):
        if self._state_get() != self.S_RUNNING:
            vals = { 'curstate': self._state_get(),
                     'action': 'generic_create_volume' }
            return HttpErrorResponse(self.WRONG_STATE_MSG % vals)

        if 'volumeName' not in kwargs:
            ex = ManagerException(ManagerException.E_ARGS_MISSING,
                                  'volumeName')
            return HttpErrorResponse(ex.message)
        if isinstance(kwargs['volumeName'], dict):
            ex = ManagerException(ManagerException.E_ARGS_INVALID,
                                  detail='volumeName should be a string')
            return HttpErrorResponse(ex.message)
        volumeName = kwargs.pop('volumeName')

        if 'volumeSize' not in kwargs:
            ex = ManagerException(ManagerException.E_ARGS_MISSING,
                                  'volumeSize')
            return HttpErrorResponse(ex.message)
        try:
            volumeSize = int(kwargs.pop('volumeSize'))
            if volumeSize <= 0:
                raise ValueError()
        except ValueError:
            ex = ManagerException(ManagerException.E_ARGS_INVALID,
                            detail='volumeSize should be a positive integer')
            return HttpErrorResponse(ex.message)

        if 'agentId' not in kwargs:
            ex = ManagerException(ManagerException.E_ARGS_MISSING,
                                  'agentId')
            return HttpErrorResponse(ex.message)
        if isinstance(kwargs['agentId'], dict):
            ex = ManagerException(ManagerException.E_ARGS_INVALID,
                                  detail='agentId should be a string')
            return HttpErrorResponse(ex.message)
        agentId = kwargs.pop('agentId')

        if len(kwargs) != 0:
            ex = ManagerException(ManagerException.E_ARGS_UNEXPECTED,
                                  kwargs.keys())
            return HttpErrorResponse(ex.message)

        config = self._configuration_get()
        if volumeName in config.volumes:
            ex = ManagerException(ManagerException.E_ARGS_INVALID,
                                  detail='volumeName already exists')
            return HttpErrorResponse(ex.message)

        if agentId not in [ node.id for node in self.nodes ]:
            ex = ManagerException(ManagerException.E_ARGS_INVALID,
                                  detail='Invalid agentId')
            return HttpErrorResponse(ex.message)

        if self._are_scripts_running():
            self.logger.info("Volume creation is disabled when scripts are "\
                    "running")
            return HttpErrorResponse(self.SCRIPTS_ARE_RUNNING_MSG);

        self._state_set(self.S_ADAPTING)
        Thread(target=self._do_create_volume, args=[volumeName, volumeSize,
               agentId]).start()

        return HttpJsonResponse({ 'state': self._state_get() })

    def _do_create_volume(self, volumeName, volumeSize, agentId):
        """Create a new volume and attach it to the specified agent"""

        self.logger.info("Going to create a new volume")

        config = self._configuration_get()
        try:
            try:
                # We try to create a new volume.
                volume_name = "generic-%s" % volumeName
                node_id = agentId.replace("iaas", "")
                self.logger.debug("Trying to create a volume for the node_id=%s"
                                  % node_id)
                volume = self.create_volume(volumeSize, volume_name, node_id)
            except Exception, ex:
                self.logger.exception("Failed to create volume %s: %s"
                                      % (volume_name, ex))
                raise
            try:
                # try to find a dev name that is not already in use by the node
                dev_names_in_use = [ vol.devName for vol in config.volumes.values()
                            if vol.agentId == agentId ]
                dev_name = self.config_parser.get('manager', 'DEV_TARGET')
                while dev_name in dev_names_in_use:
                    # increment the last char from dev_name
                    dev_name = dev_name[:-1] + chr(ord(dev_name[-1]) + 1)
                # attach the volume
                _, dev_name = self.attach_volume(volume.id, node_id, dev_name)
            except Exception, ex:
                self.logger.exception("Failed to attach disk to Generic node %s: %s"
                                      % (node_id, ex))
                self.destroy_volume(volume.id)
                raise
            try:
                node_ip = [ node.ip for node in self.nodes
                            if node.id == agentId ][0]
                client.mount_volume(node_ip, self.AGENT_PORT, dev_name, volumeName)
            except client.AgentException, ex:
                self.logger.exception('Failed to configure Generic node %s: %s'
                                      % (node_id, ex))
                self.detach_volume(volume.id)
                self.destroy_volume(volume.id)
                raise
        except Exception, ex:
            self.logger.exception('Failed to create volume: %s.' % ex)
            self._state_set(self.S_ERROR)
            return

        config.volumes[volumeName] = VolumeInfo(volumeName, volume.id,
                                                 volumeSize, agentId, dev_name)
        self._configuration_set(config)
        self.logger.info('Volume %s created and attached' % volume_name)
        self._state_set(self.S_RUNNING)

    @expose('POST')
    def generic_delete_volume(self, kwargs):
        if self._state_get() != self.S_RUNNING:
            vals = { 'curstate': self._state_get(),
                     'action': 'generic_delete_volume' }
            return HttpErrorResponse(self.WRONG_STATE_MSG % vals)

        if 'volumeName' not in kwargs:
            ex = ManagerException(ManagerException.E_ARGS_MISSING,
                                  'volumeName')
            return HttpErrorResponse(ex.message)
        if isinstance(kwargs['volumeName'], dict):
            ex = ManagerException(ManagerException.E_ARGS_INVALID,
                                  detail='volumeName should be a string')
            return HttpErrorResponse(ex.message)
        volumeName = kwargs.pop('volumeName')

        if len(kwargs) != 0:
            ex = ManagerException(ManagerException.E_ARGS_UNEXPECTED,
                                  kwargs.keys())
            return HttpErrorResponse(ex.message)

        config = self._configuration_get()

        if volumeName not in config.volumes:
            ex = ManagerException(ManagerException.E_ARGS_INVALID,
                                  detail='Invalid volumeName')
            return HttpErrorResponse(ex.message)

        if self._are_scripts_running():
            self.logger.info("Volume removal is disabled when scripts are "\
                    "running")
            return HttpErrorResponse(self.SCRIPTS_ARE_RUNNING_MSG);

        self._state_set(self.S_ADAPTING)
        Thread(target=self._do_delete_volume, args=[volumeName]).start()

        return HttpJsonResponse({ 'state': self._state_get() })

    def _do_delete_volume(self, volumeName):
        """Detach a volume and delete it"""
        self.logger.info("Going to remove volume generic-%s" % volumeName)

        config = self._configuration_get()
        self.__delete_volume_internal(config.volumes[volumeName])
        config.volumes.pop(volumeName)
        self._configuration_set(config)

        self.logger.info('Volume generic-%s removed' % volumeName)
        self._state_set(self.S_RUNNING)

    def __delete_volume_internal(self, volume):
        self.logger.debug("Detaching and deleting volume %s"
                % volume.volumeName)
        try:
            node_id = volume.agentId.replace("iaas", "")
            node_ip = [ node.ip for node in self.nodes
                        if node.id == volume.agentId ][0]
            client.unmount_volume(node_ip, self.AGENT_PORT, volume.volumeName)
        except client.AgentException, ex:
            self.logger.exception('Failed to configure Generic node %s: %s'
                                  % (node_id, ex))
        self.detach_volume(volume.volumeId)
        self.destroy_volume(volume.volumeId)

    @expose('POST')
    def execute_script(self, kwargs):
        if self._state_get() != self.S_RUNNING:
            vals = { 'curstate': self._state_get(), 'action': 'execute_script' }
            return HttpErrorResponse(self.WRONG_STATE_MSG % vals)

        if 'command' not in kwargs:
            ex = ManagerException(ManagerException.E_ARGS_MISSING,
                                  'command')
            return HttpErrorResponse(ex.message)
        if isinstance(kwargs['command'], dict):
            ex = ManagerException(ManagerException.E_ARGS_INVALID,
                                  detail='command should be a string')
            return HttpErrorResponse(ex.message)
        command = kwargs.pop('command')
        if command not in ( 'run', 'interrupt', 'cleanup' ):
            ex = ManagerException(ManagerException.E_ARGS_INVALID,
                                  detail='invalid command')
            return HttpErrorResponse(ex.message)

        if 'parameters' not in kwargs:
            parameters = ''
        else:
            if isinstance(kwargs['parameters'], dict):
                ex = ManagerException(ManagerException.E_ARGS_INVALID,
                                      detail='parameters should be a string')
                return HttpErrorResponse(ex.message)
            parameters = kwargs.pop('parameters')

        if len(kwargs) != 0:
            ex = ManagerException(ManagerException.E_ARGS_UNEXPECTED,
                                  kwargs.keys())
            return HttpErrorResponse(ex.message)

        self.logger.info("Received request for executing the '%s' command"
                % command)

        # if command is 'interrupt' and no script is running, return an error
        if command == 'interrupt' and not self._are_scripts_running():
            self.logger.info("No scripts are currently running inside agents")
            return HttpErrorResponse(self.NO_SCRIPTS_ARE_RUNNING_MSG)

        # for the other commands, if the script is already running, return an error
        elif command != 'interrupt' and self._is_script_running(command):
            self.logger.info(("Script '%s.sh' is already running inside at least "
                    "one agent.") % command)
            return HttpErrorResponse(self.SCRIPT_IS_RUNNING_MSG % command)

        Thread(target=self._do_execute_script, args=[command,
                                                        self.nodes,
                                                        parameters]).start()

        return HttpJsonResponse({ 'state': self._state_get() })

    def _is_script_running(self, command):
        script_name = "%s.sh" % command
        for node in self.nodes:
            try:
                res = client.get_script_status(node.ip, self.AGENT_PORT)
                if res['scripts'][script_name] == "RUNNING":
                    return True
            except client.AgentException:
                message = ("Failed to obtain script status at node %s" % str(node));
                self.logger.exception(message)
        return False

    def _are_scripts_running(self):
        for node in self.nodes:
            try:
                res = client.get_script_status(node.ip, self.AGENT_PORT)
                if "RUNNING" in res['scripts'].values():
                    return True
            except client.AgentException:
                message = ("Failed to obtain script status at node %s" % str(node));
                self.logger.exception(message)
        return False

    def _do_execute_script(self, command, nodes, parameters=''):
        self.logger.info("Executing the '%s' command at agents %s" %
                (command, [ node.id for node in nodes ]))

        for node in nodes:
            try:
                client.execute_script(node.ip, self.AGENT_PORT, command,
                        parameters, self.agents_info)
            except client.AgentException:
                message = ("Failed to execute the '%s' command at node %s" %
                        (command, str(node)));
                self.logger.exception(message)
                self._state_set(self.S_ERROR, msg=message)
                raise

    @expose('GET')
    def get_script_status(self, kwargs):
        if self._state_get() != self.S_RUNNING:
            vals = { 'curstate': self._state_get(), 'action': 'get_script_status' }
            return HttpErrorResponse(self.WRONG_STATE_MSG % vals)

        if len(kwargs) != 0:
            ex = ManagerException(ManagerException.E_ARGS_UNEXPECTED,
                                  kwargs.keys())
            return HttpErrorResponse(ex.message)

        agents = {}
        for node in self.nodes:
            try:
                res = client.get_script_status(node.ip, self.AGENT_PORT)
                agents[node.id] = res['scripts']
            except client.AgentException:
                message = ("Failed to obtain script status at node %s" % str(node));
                self.logger.exception(message)
                self._state_set(self.S_ERROR, msg=message)
                return HttpErrorResponse(ex.message)
        return HttpJsonResponse({ 'agents' : agents })

    @expose('GET')
    def get_agent_log(self, kwargs):
        """Return logfile"""
        if 'agentId' not in kwargs:
            ex = ManagerException(ManagerException.E_ARGS_MISSING,
                                  'agentId')
            return HttpErrorResponse(ex.message)
        if isinstance(kwargs['agentId'], dict):
            ex = ManagerException(ManagerException.E_ARGS_INVALID,
                                  detail='agentId should be a string')
            return HttpErrorResponse(ex.message)
        agentId = kwargs.pop('agentId')

        if agentId not in [ node.id for node in self.nodes ]:
            ex = ManagerException(ManagerException.E_ARGS_INVALID,
                                  detail='Invalid agentId')
            return HttpErrorResponse(ex.message)

        if 'filename' not in kwargs:
            filename = None
        else:
            if isinstance(kwargs['filename'], dict):
                ex = ManagerException(ManagerException.E_ARGS_INVALID,
                                      detail='filename should be a string')
                return HttpErrorResponse(ex.message)
            filename = kwargs.pop('filename')

        if len(kwargs) != 0:
            ex = ManagerException(ManagerException.E_ARGS_UNEXPECTED,
                                  kwargs.keys())
            return HttpErrorResponse(ex.message)

        try:
            node_ip = [ node.ip for node in self.nodes
                        if node.id == agentId ][0]
            res = client.get_log(node_ip, self.AGENT_PORT, filename)
            return HttpJsonResponse(res)
        except Exception, ex:
            return HttpErrorResponse(ex.message)

    def _configuration_get(self):
        return self.memcache.get(self.CONFIG)

    def _configuration_set(self, config):
        self.memcache.set(self.CONFIG, config)

    def _state_get(self):
        return self.memcache.get(self.DEPLOYMENT_STATE)

    def _state_set(self, target_state, msg=''):
        self.memcache.set(self.DEPLOYMENT_STATE, target_state)
        self.state_log.append({'time': time.time(),
                               'state': target_state,
                               'reason': msg})
        self.logger.debug('STATE %s: %s' % (target_state, msg))

