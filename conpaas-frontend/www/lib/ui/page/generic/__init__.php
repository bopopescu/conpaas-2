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

require_module('ui/page');

class GenericPage extends ServicePage {
    public function __construct(Service $service) {
            parent::__construct($service);
            $this->addJS('js/jquery.form.js');
            $this->addJS('js/jquery-ui.js');
            $this->addJS('js/generic.js');
    }

	private function getVersionDownloadURL($versionID) {
		$url = 'ajax/downloadCodeVersion.php?sid='.$this->service->getSID();
		$url.= '&codeVersionId='.$versionID;
		return $url;
	}

    protected function renderRightMenu() {
        $links = LinkUI('manager log',
            'viewlog.php?aid='.$this->service->getAID()
				      .'&sid='.$this->service->getSID())->setExternal(true);

        return '<div class="rightmenu">'.$links.'</div>';
    }

    protected function renderInstanceActions() {
        $role = 'node';
        return EditableTag()->setColor(Role::getColor($role))
                            ->setID($role)
                            ->setValue('0')
                            ->setText('nodes')
                            ->setTooltip(Role::getInfo($role));
    }

	public function renderInstances() {
		$this->service->updateVolumes();
		$this->service->updateScriptStatus();
		return parent::renderInstances();
	}

	private function renderFileForm() {
		$url = 'ajax/uploadCodeVersion.php?sid='.$this->service->getSID();
		return
		'<form id="fileForm" action="'.$url.'" enctype="multipart/form-data">'
			.'<input id="file" type="file" name="code" />'
			.'<input type="hidden" name="description" value="no description" />'
		.'</form>';
	}

	private function bytesOf($size_str) {
		switch (substr ($size_str, -1))	{
			case 'M': case 'm': return (int)$size_str * 1048576;
			case 'K': case 'k': return (int)$size_str * 1024;
			case 'G': case 'g': return (int)$size_str * 1073741824;
			default: return $size_str;
		}
	}

	private function minSize($size1, $size2) {
		$size1_int = $this->bytesOf($size1);
		$size2_int = $this->bytesOf($size2);
		if ($size1_int < $size2_int) {
			return $size1;
		} else {
			return $size2;
		}
	}

	protected function renderCodeForm() {
		return
			'<div id="deployform">'
				.'<div class="deployoptions">'
					.'<i>you may update the stage by</i>'
					.'<div class="deployoption">'
						.'<input type="radio" name="method" checked/>'
						.'uploading archive'
					.'</div>'
					.'<i>or by</i>'
					.'<div class="deployoption">'
						.'<input type="radio" name="method" />'
							.'checking out repository'
					.'</div>'
				.'</div>'
				.'<div class="deployactions">'
					.$this->renderFileForm()
					.'<div class="additional">'
					.'<img class="loading invisible" '
						.' src="images/icon_loading.gif" />'
					.'<i id="uploadFileStat" class="invisible"></i>'
					.'</div>'
					.'<div class="clear"></div>'
					.'<div class="hint">'
						.'example: <b>.zip</b>, <b>.tar</b> of your source tree'
						.' (max '.$this->minSize(ini_get('upload_max_filesize'), ini_get('post_max_size')).')'
					.'</div>'
				.'</div>'
				// this one is invisible for now
				.'<div class="deployactions invisible">'
					.'<textarea id="pubkey" cols="50" rows="5" name="pubkey"></textarea><br />'
					.'<div class="additional">'
					.'<img class="loading invisible" '
					    .' src="images/icon_loading.gif" />'
					.'<i id="uploadKeyStat" class="invisible"></i>'
					.'</div>'
					.'<div class="clear"></div>'
					.'<div class="hint">'
					.'Paste your public key (the contents of <b>$HOME/.ssh/id_rsa.pub)</b>'
					.'</div>'
					.'<button id="submitPubKey">Submit key</button>'
                    .'<div class="hint"><br />'
                    .'You will then be able to checkout your repository as follows:<br />'
                    .'<b>git clone git@'.$this->service->getManagerIP().':code</b><br /><br />'
                    .'The code for this service should be added in a directory callled '
                    .'<b>'.$this->service->getSID().'</b>'
                    .'</div>'
				.'</div>'
				.'<div class="clear"></div>'
			.'</div>';
	}

	public function renderCodeVersions() {
		$versions = $this->service->fetchCodeVersions();
		if ($versions === false) {
			return '<h3> No versions available </h3>';
		}
		$active = null;
		for ($i = 0; $i < count($versions); $i++) {
			if (isset($versions[$i]['current'])) {
				$active = $i;
			}
		}
		if (count($versions) == 0) {
			return '<h3> No versions available </h3>';
		}
		$html = '<ul class="versions">';
		for ($i = 0; $i < count($versions); $i++) {
			$versions[$i]['downloadURL'] =
				$this->getVersionDownloadURL($versions[$i]['codeVersionId']);
			$versionUI = Version($versions[$i])
				->setLinkable(false);
			if ($active == $i) {
			    $versionUI->setActive(true);
			}
			if ($i == count($versions) - 1) {
				$versionUI->setLast();
			}
			$html .= $versionUI;
		}
		$html .= '</ul>';
		return $html;
	}

	public function renderCodeSection() {
		return
			'<div class="form-section">'
				.'<div class="form-header">'
					.'<div class="title">'
						.'<img src="images/archive.png" />Code management'
					.'</div>'
					.'<div class="clear"></div>'
				.'</div>'
				.$this->renderCodeForm()
				.'<div class="brief">available code versions</div>'
				.'<div id="versionsWrapper">'
					.$this->renderCodeVersions()
				.'</div>'
			.'</div>';
	}

	private function renderAppLifecycleButton($command) {
		$additionalText = '';
		if ($command == 'interrupt') {
			$additionalText = " and kill all the running processes afterwards";
		}
		$tooltipText = "pressing this button will execute "
					."the '".$command.".sh' script from the active "
					."code tarball on each agent".$additionalText;
		return '<input class="generic-script-button" title="'.$tooltipText.'" '
					.'id="'.$command.'App" name="'.$command.'" type="button" '
					.'value="'.$command.'" />&nbsp;&nbsp;';
	}

	public function renderAppLifecycleSection() {
		return
			'<div class="form-section">'
/*				.'<div class="form-header">'
					.'<div class="title">'
						.'<img src="images/lifecycle.png" />'
						.'Application lifecycle management'
					.'</div>'
					.'<div class="clear"></div>'
				.'</div>' */
				.'<div class="left-stack name">'
					.'parameters'
				.'</div>'
				.'<div class="left-stack details">'
					.'<input id="scriptParameters" type="text"'
						.' class="generic-script-parameters" />'
				.'</div>'
				.'<div class="clear"></div>'
				.$this->renderAppLifecycleButton('run')
				.$this->renderAppLifecycleButton('interrupt')
				.$this->renderAppLifecycleButton('cleanup')
				.'<i id="appLifecycleStat" class="invisible"></i><br />'
			.'</div>';
	}

	public function renderContent() {
		$html = '';

		if ($this->service->isRunning()) {
			$html .= $this->renderAppLifecycleSection();
		}
		$html .= $this->renderInstancesSection()
			.$this->renderCodeSection();

		return $html;
	}
}
?>
