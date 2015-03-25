import os
import sys

from .service import ServiceCmd


class GenericCmd(ServiceCmd):

    def __init__(self, generic_parser, client):
        ServiceCmd.__init__(self, generic_parser, client, "generic",
                            ['count'], "Generic service sub-commands help")
        self._add_upload_key()
        self._add_list_keys()
        self._add_upload_code()
        self._add_list_uploads()
        self._add_download_code()
        self._add_enable_code()
        self._add_delete_code()
        self._add_list_volumes()
        self._add_create_volume()
        self._add_delete_volume()
        self._add_run()
        self._add_interrupt()
        self._add_cleanup()
        self._add_get_script_status()
        self._add_get_agent_log()

    # ========== upload_key
    def _add_upload_key(self):
        subparser = self.add_parser('upload_key',
                                    help="upload key to Generic server")
        subparser.set_defaults(run_cmd=self.upload_key, parser=subparser)
        subparser.add_argument('app_name_or_id',
                               help="Name or identifier of an application")
        subparser.add_argument('serv_name_or_id',
                               help="Name or identifier of a service")
        subparser.add_argument('filename',
                               help="File containing the key")

    def upload_key(self, args):
        app_id, service_id = self.get_service_id(args.app_name_or_id, args.serv_name_or_id)
        contents = open(args.filename).read()
        params = {'method': "upload_authorized_key"}
        files = [('key', args.filename, contents)]
        res = self.client.call_manager_post(app_id, service_id, "/", params, files)
        if 'error' in res:
            self.client.error(res['error'])
        else:
            print res['outcome']

    # ========== list_keys
    def _add_list_keys(self):
        subparser = self.add_parser('list_keys',
                                    help="list authorized keys of Generic service")
        subparser.set_defaults(run_cmd=self.list_keys, parser=subparser)
        subparser.add_argument('app_name_or_id',
                               help="Name or identifier of an application")
        subparser.add_argument('serv_name_or_id',
                               help="Name or identifier of a service")

    def list_keys(self, args):
        app_id, service_id = self.get_service_id(args.app_name_or_id, args.serv_name_or_id)
        res = self.client.call_manager_get(app_id, service_id, "list_authorized_keys")

        if 'error' in res:
            self.client.error("Cannot list keys: %s" % res['error'])
        else:
            print "%s" % res['authorizedKeys']

    # ========== upload_code
    def _add_upload_code(self):
        subparser = self.add_parser('upload_code',
                                    help="upload a new code version")
        subparser.set_defaults(run_cmd=self.upload_code, parser=subparser)
        subparser.add_argument('app_name_or_id',
                               help="Name or identifier of an application")
        subparser.add_argument('serv_name_or_id',
                               help="Name or identifier of a service")
        subparser.add_argument('filename',
                               help="File containing the code")

    def upload_code(self, args):
        app_id, service_id = self.get_service_id(args.app_name_or_id, args.serv_name_or_id)
        filename = args.filename
        if not (os.path.isfile(filename) and os.access(filename, os.R_OK)):
            self.client.error("Cannot upload code: filename '%s' not found or "
                              "access is denied" % filename)

        contents = open(filename).read()
        files = [ ( 'code', filename, contents ) ]

        res = self.client.call_manager_post(app_id, service_id,  "/",
                                            {'method': "upload_code_version", },
                                            files)
        if 'error' in res:
            self.client.error(res['error'])
        else:
            print "Code version %(codeVersionId)s uploaded" % res

    # ========== list_uploads
    def _add_list_uploads(self):
        subparser = self.add_parser('list_uploads',
                                    help="list uploaded code versions")
        subparser.set_defaults(run_cmd=self.list_uploads, parser=subparser)
        subparser.add_argument('app_name_or_id',
                               help="Name or identifier of an application")
        subparser.add_argument('serv_name_or_id',
                               help="Name or identifier of a service")

    def list_uploads(self, args):
        
        app_id, service_id = self.get_service_id(args.app_name_or_id, args.serv_name_or_id)

        res = self.client.call_manager_get(app_id, service_id, "list_code_versions")

        if 'error' in res:
            self.client.error("Cannot list code versions: %s" % res['error'])

        for code in res['codeVersions']:
            current = "*" if 'current' in code else ""
            print " %s %s: %s \"%s\"" % (current, code['codeVersionId'],
                                         code['filename'], code['description'])

    # ========== download_code
    def _add_download_code(self):
        subparser = self.add_parser('download_code',
                                    help="download code from Generic service")
        subparser.set_defaults(run_cmd=self.download_code, parser=subparser)
        subparser.add_argument('app_name_or_id',
                               help="Name or identifier of an application")
        subparser.add_argument('serv_name_or_id',
                               help="Name or identifier of a service")
        # TODO: make version optional to retrieve the last version by default
        subparser.add_argument('version',
                               help="Version of code to download")

    def download_code(self, args):
        app_id, service_id = self.get_service_id(args.app_name_or_id, args.serv_name_or_id)

        res = self.client.call_manager_get(app_id, service_id, "list_code_versions")

        if 'error' in res:
            self.client.error("Cannot list code versions: %s" % res['error'])

        filenames = [ code['filename'] for code in res['codeVersions']
                if code['codeVersionId'] == args.version ]
        if not filenames:
            self.client.error("Cannot download code: invalid version '%s'"
                    % args.version)

        destfile = filenames[0]

        params = {'codeVersionId': args.version}
        res = self.client.call_manager_get(app_id, service_id, "download_code_version",
                                           params)

        if 'error' in res:
            self.client.error("Cannot download code: %s" % res['error'])

        else:
            open(destfile, 'w').write(res)
            print destfile, 'written'

    # ========== enable_code
    def _add_enable_code(self):
        subparser = self.add_parser('enable_code',
                                    help="set a specific code version active")
        subparser.set_defaults(run_cmd=self.enable_code, parser=subparser)
        subparser.add_argument('app_name_or_id',
                               help="Name or identifier of an application")
        subparser.add_argument('serv_name_or_id',
                               help="Name or identifier of a service")
        subparser.add_argument('code_version',
                               help="Code version to be activated")

    def enable_code(self, args):
        app_id, service_id = self.get_service_id(args.app_name_or_id, args.serv_name_or_id)
        code_version = args.code_version

        params = { 'codeVersionId': code_version }

        res = self.client.call_manager_post(app_id, service_id, "enable_code", params)

        if 'error' in res:
            self.client.error(res['error'])
        else:
            print code_version, 'enabled'

    # ========== delete_code
    def _add_delete_code(self):
        subparser = self.add_parser('delete_code',
                                    help="delete a specific code version")
        subparser.set_defaults(run_cmd=self.delete_code, parser=subparser)
        subparser.add_argument('app_name_or_id',
                               help="Name or identifier of an application")
        subparser.add_argument('serv_name_or_id',
                               help="Name or identifier of a service")
        subparser.add_argument('code_version',
                               help="Code version to be deleted")

    def delete_code(self, args):
        app_id, service_id = self.get_service_id(args.app_name_or_id, args.serv_name_or_id)
        code_version = args.code_version

        params = { 'codeVersionId': code_version }

        res = self.client.call_manager_post(app_id, service_id, "delete_code_version", params)

        if 'error' in res:
            self.client.error(res['error'])
        else:
            print code_version, 'deleted'

    # ========== list_volumes
    def _add_list_volumes(self):
        subparser = self.add_parser('list_volumes',
                                    help="list the volumes in use by the agents")
        subparser.set_defaults(run_cmd=self.list_volumes, parser=subparser)
        subparser.add_argument('app_name_or_id',
                               help="Name or identifier of an application")
        subparser.add_argument('serv_name_or_id',
                               help="Name or identifier of a service")

    def list_volumes(self, args):
        app_id, service_id = self.get_service_id(args.app_name_or_id, args.serv_name_or_id)

        res = self.client.call_manager_get(app_id, service_id, "list_volumes")

        if 'error' in res:
            self.client.error("Cannot list volumes: %s" % res['error'])
        elif res['volumes']:
            for volume in res['volumes']:
                print "%s (size %sMB, attached to %s)" % (volume['volumeName'],
                                         volume['volumeSize'], volume['agentId'])
        else:
            print 'No volumes defined'

    # ========== create_volume
    def _add_create_volume(self):
        subparser = self.add_parser('create_volume',
                                    help="create a volume and attatch it to an agent")
        subparser.set_defaults(run_cmd=self.create_volume, parser=subparser)
        subparser.add_argument('app_name_or_id',
                               help="Name or identifier of an application")
        subparser.add_argument('serv_name_or_id',
                               help="Name or identifier of a service")
        subparser.add_argument('vol_name',
                               help="Name of the volume")
        subparser.add_argument('vol_size',
                               help="Size of the volume (MB)")
        subparser.add_argument('agent_id',
                               help="Id of the agent to attach the volume to")

    def create_volume(self, args):
        app_id, service_id = self.get_service_id(args.app_name_or_id, args.serv_name_or_id)

        params = { 'volumeName': args.vol_name,
                   'volumeSize': args.vol_size,
                   'agentId': args.agent_id }

        res = self.client.call_manager_post(app_id, service_id, "generic_create_volume",
                params)

        if 'error' in res:
            self.client.error(res['error'])
        else:
            print ("Creating volume %s and attaching it to %s... " %
                    (args.vol_name, args.agent_id))
            sys.stdout.flush()

            state = self.client.wait_for_state(app_id, service_id, ['RUNNING', 'ERROR'])

            if state == 'RUNNING':
                print ("done.")
            else:
                self.client.error("failed to state %s" % state)
            sys.stdout.flush()

    # ========== delete_volume
    def _add_delete_volume(self):
        subparser = self.add_parser('delete_volume',
                                    help="detach and delete a volume")
        subparser.set_defaults(run_cmd=self.delete_volume, parser=subparser)
        subparser.add_argument('app_name_or_id',
                               help="Name or identifier of an application")
        subparser.add_argument('serv_name_or_id',
                               help="Name or identifier of a service")
        subparser.add_argument('vol_name',
                               help="Name of a volume")

    def delete_volume(self, args):
        app_id, service_id = self.get_service_id(args.app_name_or_id, args.serv_name_or_id)

        params = { 'volumeName': args.vol_name }

        res = self.client.call_manager_post(app_id, service_id, "generic_delete_volume",
                params)

        if 'error' in res:
            self.client.error(res['error'])
        else:
            print ("Detaching and deleting volume %s... " % args.vol_name)
            sys.stdout.flush()

            state = self.client.wait_for_state(service_id, ['RUNNING', 'ERROR'])

            if state == 'RUNNING':
                print ("done.")
            else:
                self.client.error("failed to state %s" % state)
            sys.stdout.flush()

    # ========== run
    def _add_run(self):
        subparser = self.add_parser('run',
                                    help="execute the run.sh script")
        subparser.set_defaults(run_cmd=self.run, parser=subparser)
        subparser.add_argument('app_name_or_id',
                               help="Name or identifier of an application")
        subparser.add_argument('serv_name_or_id',
                               help="Name or identifier of a service")
        subparser.add_argument('-p', '--parameters', metavar='PARAMETERS',
                               default='', help="parameters for the script")

    def run(self, args):
        app_id, service_id = self.get_service_id(args.app_name_or_id, args.serv_name_or_id)

        params = { 'command': 'run', 'parameters': args.parameters }
        res = self.client.call_manager_post(app_id, service_id, "execute_script", params)

        if 'error' in res:
            self.client.error(res['error'])
        else:
            print "Service started executing 'run.sh' on all the agents..."

    # ========== interrupt
    def _add_interrupt(self):
        subparser = self.add_parser('interrupt',
                                    help="execute the interrupt.sh script")
        subparser.set_defaults(run_cmd=self.interrupt, parser=subparser)
        subparser.add_argument('app_name_or_id',
                               help="Name or identifier of an application")
        subparser.add_argument('serv_name_or_id',
                               help="Name or identifier of a service")
        subparser.add_argument('-p', '--parameters', metavar='PARAMETERS',
                               default='', help="parameters for the script")

    def interrupt(self, args):
        app_id, service_id = self.get_service_id(args.app_name_or_id, args.serv_name_or_id)

        params = { 'command': 'interrupt', 'parameters': args.parameters }
        res = self.client.call_manager_post(app_id, service_id, "execute_script", params)

        if 'error' in res:
            self.client.error(res['error'])
        else:
            print "Service started executing 'interrupt.sh' on all the agents..."

    # ========== cleanup
    def _add_cleanup(self):
        subparser = self.add_parser('cleanup',
                                    help="execute the cleanup.sh script")
        subparser.set_defaults(run_cmd=self.cleanup, parser=subparser)
        subparser.add_argument('app_name_or_id',
                               help="Name or identifier of an application")
        subparser.add_argument('serv_name_or_id',
                               help="Name or identifier of a service")
        subparser.add_argument('-p', '--parameters', metavar='PARAMETERS',
                               default='', help="parameters for the script")

    def cleanup(self, args):
        app_id, service_id = self.get_service_id(args.app_name_or_id, args.serv_name_or_id)

        params = { 'command': 'cleanup', 'parameters': args.parameters }
        res = self.client.call_manager_post(app_id, service_id, "execute_script", params)

        if 'error' in res:
            self.client.error(res['error'])
        else:
            print "Service started executing 'cleanup.sh' on all the agents..."

    # ========== get_script_status
    def _add_get_script_status(self):
        subparser = self.add_parser('get_script_status',
                                    help="get the status of the scripts for each agent")
        subparser.set_defaults(run_cmd=self.get_script_status, parser=subparser)
        subparser.add_argument('app_name_or_id',
                               help="Name or identifier of an application")
        subparser.add_argument('serv_name_or_id',
                               help="Name or identifier of a service")

    def get_script_status(self, args):
        app_id, service_id = self.get_service_id(args.app_name_or_id, args.serv_name_or_id)

        res = self.client.call_manager_get(app_id, service_id, "get_script_status")

        if 'error' in res:
            self.client.error(res['error'])
        elif res['agents']:
            print
            for agent in sorted(res['agents']):
                print "Agent %s:" % agent
                status = res['agents'][agent]
                for script in ('init.sh', 'notify.sh', 'run.sh',
                                'interrupt.sh', 'cleanup.sh'):
                    print "  %s\t%s" % (script, status[script])
                print

    # ========== get_agent_log
    def _add_get_agent_log(self):
        subparser = self.add_parser('get_agent_log',
                                    help="get the agent logs")
        subparser.set_defaults(run_cmd=self.get_agent_log, parser=subparser)
        subparser.add_argument('app_name_or_id',
                               help="Name or identifier of an application")
        subparser.add_argument('serv_name_or_id',
                               help="Name or identifier of a service")
        subparser.add_argument('agent_id',
                               help="Id of the agent")
        subparser.add_argument('-f', '--filename', metavar='FILENAME',
                               default=None, help="log file name")

    def get_agent_log(self, args):
        app_id, service_id = self.get_service_id(args.app_name_or_id, args.serv_name_or_id)

        params = { 'agentId': args.agent_id }
        if args.filename:
            params['filename'] = args.filename
        res = self.client.call_manager_get(app_id, service_id, "get_agent_log", params)

        if 'error' in res:
            self.client.error(res['error'])
        else:
            print res['log']
