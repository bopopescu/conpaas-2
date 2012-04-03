<?php
/*
 * Copyright (c) 2010-2012, Contrail consortium.
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

require_module('user');
require_module('ui');

class Page {

	protected $uid;
	protected $user_credit;
	protected $username;
	protected $browser;
	protected $jsFiles = array('js/jquery-1.5.js', 'js/conpaas.js');

	public function __construct() {
		$this->fetchBrowser();
		if (isset($_SESSION['uid'])) {
			$this->uid = $_SESSION['uid'];
			if ($this->isLoginPage()) {
				self::redirect('index.php');
			}
		} else {
			// not logged in
			if (!$this->isLoginPage()) {
				self::redirect('login.php');
			}
			return;
		}
		$uinfo = UserData::getUserById($this->uid);
		if ($uinfo === false) {
			throw new Exception('User does not exist');
		}
		$this->username = $uinfo['username'];
		$this->user_credit = $uinfo['credit'];
	}

	protected function addJS($url) {
		$this->jsFiles []= $url;
	}

	public static function redirect($toURL) {
		header('Location: '.$toURL);
		exit();
	}

	public function fetchBrowser() {
		$user_agent = $_SERVER['HTTP_USER_AGENT'];
		if (strpos($user_agent, 'Firefox') !== false) {
			$this->browser = 'firefox';
		} else if (strpos($user_agent, 'WebKit') != false) {
			$this->browser = 'webkit';
		} else {
			$this->browser = 'other';
		}
	}

	public function isLoginPage() {
		return strpos($_SERVER['SCRIPT_NAME'], 'login.php') !== false;
	}

	public function renderDoctype() {
		return '<!DOCTYPE html PUBLIC "-//W3C//DTD HTML 4.01 Transitional//EN"'
			.' "http://www.w3.org/TR/html4/loose.dtd">';
	}

	public function renderContentType() {
		return '<meta http-equiv="Content-Type" content="text/html;'
			.' charset=utf-8" />';
	}

	public static function renderCSSLink($url) {
		return '<link type="text/css" rel="stylesheet" href="'.$url.'" />';
	}

	public static function renderScriptLink($url) {
		return '<script src="'.$url.'"></script>';
	}

	public function renderHeaderCSS() {
		return self::renderCSSLink('conpaas.css');
	}

	public function renderJSLoad() {
		$scripts = '';
		foreach ($this->jsFiles as $jsFile) {
			$scripts .= self::renderScriptLink($jsFile);
		}
		return $scripts;
	}

	public function renderTitle() {
		return '<title>ConPaaS - management interface</title>';
	}

	public function getUserCredit() {
	    return $this->user_credit;
	}

	public function getBrowserClass() {
		return $this->browser;
	}

	public function getUsername() {
		return $this->username;
	}

	public function getUID() {
		return $this->uid;
	}

	public function renderIcon() {
		return '<link rel="shortcut icon" href="images/conpaas.ico">';
	}

	public function renderPageStatus() {
		return
			'<div id="pgstat">'
			.'<div id="pgstatInfo" style="display: none;">'
				.'<img src="images/info.png" style="margin-right: 5px;"/>'
				.'<span id="pgstatInfoText">service is starting</span>'
				.'</div>'
			.'<div id="pgstatError" style="display: none;">'
				.'<img src="images/error.png" style="vertical-align: middle; margin-right: 5px;"/>'
				.'<span id="pgstatErrorName">service error</span>'
				.'<a id="pgstatErrorDetails" href="javascript: void(0);">'
					.'<img src="images/link_s.png" />details'
				.'</a>'
			.'</div>'
			.'<div id="pgstatLoading" style="display: none;">'
				.'<span id="pgstatLoadingText">creating service...</span>'
				.'<img class="loading" src="images/icon_loading.gif" style="vertical-align: middle;" /> '
			.'</div>'
			.'<div id="pgstatTimer" style="display: none;">'
				.'<img src="images/refresh.png" /> recheck in <i id="pgstatTimerSeconds">6</i> seconds </div>'
			.'<div class="clear"></div>'
			.'</div>';
	}

	public function renderHeader() {
		return
			'<div class="header">'.
  				'<a id="logo" href="index.php"></a>'.
  				'<div class="user">'.
  					'<div class="logout">'.
  						'<a href="javascript: void(0);" id="logout">logout</a>'.
  					'</div>'.
  					'<div class="usercredit" id="user_credit_container" title="credits">'.
  						'<span id="user_credit">'.
  					      $this->getUserCredit().
  					    '</span>'.
  					'</div>'.
					'<div class="username">'
						.$this->getUsername()
					.'</div> '.
  				'</div>'.
  				'<div class="clear"></div>'.
  			'</div>'.
			$this->renderPageStatus();
	}

	public function renderFooter() {
		return
			'<div class="footer">'.
				'&copy;2010-2012 <a href="http://contrail-project.eu/">Contrail</a> - ConPaaS is the PaaS component of <a href="http://contrail-project.eu/">Contrail</a>'.
			'</div>';
	}

	public function generateJSGetParams() {
		return
			'<script>var GET_PARAMS = '.json_encode($_GET, JSON_HEX_TAG).';'
			.'</script>';
	}
}

?>