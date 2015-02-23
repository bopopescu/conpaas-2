<?php
/* Copyright (C) 2010-2013 by Contrail Consortium. */



require_once('../__init__.php');
require_module('service');
require_module('service/factory');
require_module('ui/service');
require_module('ui/page');
require_module('ui/page/hosting');
require_module('ui/page/generic');

if (!isset($_SESSION['uid'])) {
	throw new Exception('User not logged in');
}

$sid = $_GET['sid'];
$target = $_GET['target'];
$service_data = ServiceData::getServiceById($sid);
$service = ServiceFactory::create($service_data);

if($service->getUID() !== $_SESSION['uid']) {
    throw new Exception('Not allowed');
}

switch ($target) {
	case 'versions':
		$page = new HostingPage($service);
		echo $page->renderCodeVersions();
		break;
	case 'instances':
		$page = new ServicePage($service);
		echo $page->renderInstances();
		break;
	case 'generic_versions':
		$page = new GenericPage($service);
		echo $page->renderCodeVersions();
		break;
	case 'generic_volumes':
		$page = new GenericPage($service);
		echo $page->renderVolumeList();
		break;
	default:
		echo "error: unknow target $target for rendering";
}


?>
