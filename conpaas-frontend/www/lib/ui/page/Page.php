<?php
/* Copyright (C) 2010-2013 by Contrail Consortium. */




require_module('user');
require_module('ui');
require_module('director');

class Page {

	protected $uid;
	protected $user_credit;
	protected $username;
	protected $browser;
	protected $messages = array();
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
                if (isset($_SESSION['openid']) && ($_SESSION['openid'] != "<none>") ) { /* if you check $_SESSION['username'] first, you will NOT be able to login with OpenID */
                    // user_error('Try UserData::getUserByOpenid(' . $_SESSION['openid'] . ')');
                    $uinfo = UserData::getUserByOpenid($_SESSION['openid']);
                } elseif (isset($_SESSION['uuid']) && ($_SESSION['uuid'] != "<none>") ) { /* if you check $_SESSION['username'] first, you will NOT be able to login with Contrail IdP */
                    // user_error('Try UserData::getUserByUuid(' . $_SESSION['uuid'] . ')');
                    $uinfo = UserData::getUserByUuid($_SESSION['uuid']);
                } else {
                    // user_error('Try UserData::getUserByName(' . $_SESSION['username'] . ')');
                    $uinfo = UserData::getUserByName($_SESSION['username']);
                }
		if ($uinfo === false) {
			unset($_SESSION['uid']);
			self::redirect('login.php');
		}
		$this->username = $uinfo['username'];
		$this->user_credit = $uinfo['credit'];
	}

	protected function addJS($url) {
		$this->jsFiles []= $url;
	}

	/**
	 * stack messages to signal issues to the user
	 * @param string $type @see MessageBox for types
	 * @param string $text message text
	 */
	protected function addMessage($type, $text) {
		$this->messages []= array('type' => $type, 'text' => $text);
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
		$cssHeaders =  '';
		$cssHeaders .= self::renderCSSLink('css/conpaas.css');
		$cssHeaders .= self::renderCSSLink('css/autoscaling.css');
		
		return $cssHeaders;
	}

	public function renderJSLoad() {
		$scripts = '';
		foreach ($this->jsFiles as $jsFile) {
			$scripts .= self::renderScriptLink($jsFile);
		}
		return $scripts;
	}

	public function renderTitle($pageTitle) {
		return '<title>ConPaaS - management interface' . $pageTitle . '</title>';
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

	protected function renderBackLinks() {
		return '';
	}

	protected function renderMessages() {
		$html = '';
		foreach ($this->messages as $msg) {
			$html .= MessageBox($msg['type'], $msg['text']);
		}
		return $html;
	}

	public function renderPageStatus() {
		return
			'<div id="pgstat">'
			.'<div id="backLinks">'
				.$this->renderBackLinks()
			.'</div>'
			.'<div id="pgstatRightWrap">'
			.'<div id="pgstatLoading" class="invisible">'
				.'<span id="pgstatLoadingText">creating service...</span>'
				.'<img class="loading" src="images/icon_loading.gif" style="vertical-align: middle;" /> '
			.'</div>'
			.'<div id="pgstatTimer" class="invisible">'
				.'<img src="images/refresh.png" /> recheck in '
				.'<i id="pgstatTimerSeconds">6</i> seconds '
			.'</div>'
				.'<div id="pgstatInfo" class="invisible">'
					.'<img src="images/info.png" style="margin-right: 5px;"/>'
					.'<span id="pgstatInfoText">service is starting</span>'
				.'</div>'
				.'<div id="pgstatError" class="invisible">'
					.'<img src="images/error.png" style="vertical-align: middle; margin-right: 5px;"/>'
					.'<span id="pgstatErrorName">service error</span>'
					.'<a id="pgstatErrorDetails" href="javascript: void(0);">'
						.'<img src="images/link_s.png" />details'
					.'</a>'
				.'</div>'
				.'<div class="clear"></div>'
			.'</div>'
			.'<div class="clear"></div>'
			.'</div>';
	}

	public function renderUserCredit() {
		return $this->getUserCredit();
	}

	public function renderHeader() {
		return
			'<div class="header">'
  				.'<a id="logo" href="index.php"></a>'
  				.'<div class="user">'
  					.'<div class="logout">'
  						.'<a href="javascript: void(0);" id="logout">logout</a>'
  					.'</div>'
		                        . '<div class="help" title="help">'
		                            . '<a target="_blank" href="https://conpaas-team.readthedocs.org/">help</a>'
                                        . '</div>'
  					.'<div class="usercredit" id="user_credit_container" '
  							.' title="credits">'
  						.'<span id="user_credit">'
  					     	.$this->renderUserCredit()
  					    .'</span>'
  					.'</div>'
					.'<div class="username">'
						.$this->getUsername()
					.'</div> '
  				.'</div>'
  				.'<div class="clear"></div>'
  			.'</div>'
  			.$this->renderMessages()
			.$this->renderPageStatus();
	}

	public function renderFooter() {
		return
			'<div class="footer">'.
				'Copyright &copy;2011-'.date('Y').' Contrail consortium <br/> <a href="http://www.conpaas.eu/" target="_blank">ConPaaS</a> is the PaaS component of <a href="http://contrail-project.eu/" target="_blank">Contrail</a>. ConPaaS '.Director::getVersion().'.'.
			'</div>';
	}

	public function renderCloudProviders($default, $visible) {
		$clouds = json_decode(HTTPS::get(Conf::DIRECTOR . '/available_clouds'));
		if (count($clouds) <= 1) {
			return '';
		}

		$clouds_html = '';
		foreach($clouds as $cloud) {
			if ($cloud === $default)
				$checked = 'checked';
			else
				$checked = '';

			$clouds_html .= '<input type="radio"' . $checked
				.' name="available_clouds" value="'.$cloud.'"/>'
				.$cloud.'<br/>';
		}

		return
			'<table class="cloud" id="cloudProviders"'
					.' cellspacing="0" cellpading="0"'
					.($visible ? '' : ' style="display:none"')
				.'>'
				.'<tr>'
				.'<td class="cloud-descr">cloud provider</td>'
				.'<td class="cloud-choice">'
				.$clouds_html
				.'</td>'
				.'</tr>'
				.'</table>';
	}

	public function generateJSGetParams() {
		return
			'<script>var GET_PARAMS = '.json_encode($_GET, JSON_HEX_TAG).';'
			.'</script>';
	}
}

?>
