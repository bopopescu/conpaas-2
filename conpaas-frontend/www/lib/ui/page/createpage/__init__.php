<?php
/* Copyright (C) 2010-2014 by Contrail Consortium. */



require_module('ui/page');

class CreatePage extends Page {

	public function __construct() {
		parent::__construct();
	}

	protected function renderBackLinks() {
		$app = LinkUI('Dashboard', 'index.php')
			->setIconPosition(LinkUI::POS_LEFT)
			->setIconURL('images/link_s_back.png');
		$dashboard = LinkUI('This application', 'application.php?aid='.$_SESSION['aid'])
			->setIconPosition(LinkUI::POS_LEFT)
			->setIconURL('images/link_s_back.png');

		return $app . $dashboard;
	}

}
