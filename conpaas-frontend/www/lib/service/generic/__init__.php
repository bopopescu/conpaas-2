<?php
/*
 * Copyright (c) 2010-2014, Contrail consortium.
 * All rights reserved.
 *
 * Redistribution and use in source and binary forms,
 * with or without modification, are permitted provided
 * that the following conditions are met:
 *
 *  1. Redistributions of source code must retain the
 *     above copyright notice, this list of conditions
 *     and the following disclaimer.
 *  2. Redistributions in binary form must reproduce
 *     the above copyright notice, this list of
 *     conditions and the following disclaimer in the
 *     documentation and/or other materials provided
 *     with the distribution.
 *  3. Neither the name of the Contrail consortium nor the
 *     names of its contributors may be used to endorse
 *     or promote products derived from this software
 *     without specific prior written permission.
 *
 * THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND
 * CONTRIBUTORS "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES,
 * INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF
 * MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
 * DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR
 * CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
 * SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING,
 * BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
 * SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
 * INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY,
 * WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
 * (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT
 * OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
 * POSSIBILITY OF SUCH DAMAGE.
 */

require_module('cloud');
require_module('http');
require_module('service');
require_module('ui/instance/generic');

class GenericService extends Service {

	private $scriptStatus = null;
	private $volumes = null;

	public function __construct($data, $manager) {
		parent::__construct($data, $manager);
	}

	public function hasDedicatedManager() {
		return true;
	}

	public function sendConfiguration($params) {
		return $this->managerRequest('post', 'enable_code',
			$params);
	}

	public function fetchHighLevelMonitoringInfo() {
		return false;
	}

	public function getInstanceRoles() {
		return array('master', 'node');
	}

	public function fetchStateLog() {
		return array();
	}

	public function createInstanceUI($node) {
		$info = $this->getNodeInfo($node);
		if ($this->scriptStatus) {
			$scriptStatus = $this->scriptStatus[$node];
		} else {
			$scriptStatus = null;
		}
		if ($this->volumes) {
			$volumes = $this->volumes[$node];
		} else {
			$volumes = null;
		}
		return new GenericInstance($info, $this->sid, $volumes, $scriptStatus);
	}

	public function createScriptStatusUI() {
		$scriptStatusUIArray = array();
		$this->updateScriptStatus();
		if ($this->scriptStatus) {
			foreach ($this->scriptStatus as $node => $status) {
				$scriptStatusUIArray[$node] =
						GenericInstance::renderScriptStatusTable($status);
			}
		}
		return $scriptStatusUIArray;
	}

	public function getMasterAddr() {
		$master_node = $this->getNodeInfo($this->nodesLists['master'][0]);
		return $master_node['ip'];
	}

	public function listVolumes() {
		$json = $this->managerRequest('get', 'list_volumes', array());
		$volumes = json_decode($json, true);
		if ($volumes == null) {
			return false;
		}
		return $volumes['result']['volumes'];
	}

	public function createVolume($params) {
		$resp = $this->managerRequest('post', 'generic_create_volume', $params);
		return $resp;
	}

	public function deleteVolume($params) {
		$resp = $this->managerRequest('post', 'generic_delete_volume', $params);
		return $resp;
	}

	public function executeScript($params) {
		$resp = $this->managerRequest('post', 'execute_script', $params);
		return $resp;
	}

	public function updateVolumes() {
		$this->volumes = null;
		if (!$this->isRunning()) {
			return;
		}
		$volumes = $this->listVolumes();
		if ($volumes === false) {
			return;
		}
		usort($volumes, function ($a, $b) {
			return strcmp($a['volumeName'], $b['volumeName']);
		});
		$this->volumes = array();
		if ($this->nodesLists !== false) {
			foreach ($this->nodesLists as $role => $nodesList) {
				foreach ($nodesList as $node) {
					$this->volumes[$node] = array_values(array_filter($volumes,
						function($volume) use($node) {
							return $volume['agentId'] === $node;
						}
					));
				}
			}
		}
	}

	public function updateScriptStatus() {
		if (!$this->isRunning()) {
			$this->scriptStatus = null;
			return;
		}
		$json = $this->managerRequest('get', 'get_script_status', array());
		$status = json_decode($json, true);
		if ($status == null) {
			$this->scriptStatus = null;
		} else {
			$this->scriptStatus = $status['result']['agents'];
		}
	}

	public function fetchAgentLog($params) {
		$json = $this->managerRequest('get', 'get_agent_log', $params);
		$log = json_decode($json, true);
		return $log['result']['log'];
	}
}

?>
