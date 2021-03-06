<?php
/* Copyright (C) 2010-2013 by Contrail Consortium. */



/*
 *	 TODO:	as this file was created from a BLUEPRINT file,
 *	 	you may want to change ports, paths and/or methods (e.g. for hub)
 *		to meet your specific service/server needs
 */
require_module('cloud');
require_module('http');
require_module('service');
require_module('ui/instance/htc');

class HTCService extends Service {

	public function __construct($data, $manager) {
		parent::__construct($data, $manager);
	}


	public function sendConfiguration($params) {
		// we ignore this for now
		return '{}';
	}

	public function fetchHighLevelMonitoringInfo() {
		return false;
	}

	public function getInstanceRoles() {
		return array('agent');
	}

	public function fetchStateLog() {
		return array();
	}

	public function createInstanceUI($info) {
		return new HTCInstance($info);
	}

	public function getMasterAddr() {
		$master_node = $this->getNodeInfo($this->nodesLists['agent'][0]);
		return $master_node['ip'];
	}

	public function getAccessLocation() {
		return "http://" . $this->getMasterAddr() . ':4444/grid/console';
	}
}

?>
