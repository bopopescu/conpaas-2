<?php
/* Copyright (C) 2010-2013 by Contrail Consortium. */



require_module('logging');
require_module('https');

class Application {

	protected $aid,
		  $name;

	private $errorMessage = null;

	public static function stateIsStable($remoteState) {
		return true;
	}

	public function __construct($data) {
		foreach ($data as $key => $value) {
			$this->$key = $value;
		}
		if($this->manager != '')
			$this->manager = 'https://'.$this->manager;
	}

	public function getErrorMessage() {
		return $this->errorMessage;
	}

	public function needsPolling() {
		return false;
	}

	public function getAID() {
		return $this->aid;
	}

	public function getName() {
		return $this->name;
	}

	public function toArray() {
		return array(
			'aid' => $this->aid,
			'name' => $this->name,
		);
	}


	protected function managerRequest($http_method, $method, $manager_id,  array $params, $ping=false) {
		$json = HTTPS::jsonrpc($this->manager, $http_method, $method, $manager_id, $params,$ping);
		// $this->decodeResponse($json, $method);
		return $json;
	}

	public function getProfilingInfo() {
		$json = $this->managerRequest('get', 'get_profiling_info', 0, array('manager_id' => 0), false);
		$info = json_decode($json, true);
		if ($info == null) {
			return false;
		}
		return $info['result'];
	}
}
