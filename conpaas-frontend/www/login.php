<?php
/* Copyright (C) 2010-2013 by Contrail Consortium. */

require_once('__init__.php');
require_module('ui/page/login');
require_module('recaptcha');
//require_module('director');
require_module('debug'); // also includes director

if (isset($_SESSION['uid'])) {
    header('Location: index.php');
    exit();
}

$page = new LoginPage();
echo $page->renderDoctype();
$support_external_idp = Director::getSupportExternalIdp();
$support_openid = Director::getSupportOpenID();
?>
<html>
    <head>
        <script src="js/jquery-1.5.js"></script>
        <!--
        <script>
            // example found on   http://stackoverflow.com/questions/439463/how-to-get-get-and-post-variables-with-jquery
            // maybe move this code to login.js ??
            var jGets = new Array ();
            var jPosts = new Array ();
            <?
            if(isset($_GET)) {
                foreach($_GET as $key => $val)
                    echo "jGets[\"$key\"]=\"$val\";\n";
            }
            if(isset($_POST)) {
                foreach($_POST as $key => $val)
                    echo "jPosts[\"$key\"]=\"$val\";\n";
            }
            ?>
        </script>
        -->
        <?php 
        echo $page->renderContentType(); 
        if (isset($_GET['get']) || isset($_POST['get'])) {
                echo $page->renderTitle(' - Login by Contrail'); 
        } else {
                echo $page->renderTitle(' - Login'); 
        }
        echo $page->renderIcon(); 
        echo $page->renderHeaderCSS();
        ?>
        <script>
         <?php
             // there might be a better place for this piece of code
             $return_url = Conf::getFrontendURL() . '/login.php';
             $return_url = str_replace( ":443", "", $return_url );
             echo "MyURL = \"$return_url\";\n";
         ?>
        </script>
    </head>
<body class="loginbody" style="border-style:none">
    <div class="logo">
        <a href="http://www.conpaas.eu/" target="_blank"><img src="images/conpaas-logo-large.png" /></a>
    </div>
    <div class="login">
        <table><tr>
        <td class="descr" width="65%">
            <p><b><a href="http://www.conpaas.eu/">ConPaaS</a></b> is the Platform-as-a-Service component of the <a href="http://contrail-project.eu/">Contrail</a> E.U. project.</p>
            <p><b>ConPaaS</b> aims at facilitating the deployment of applications in the cloud. It provides a number of services to address common developer needs.
            Each service is self-managed and elastic:
            <ul>
                <li> it can deploy itself on the cloud </li>
                <li> it monitors its own performance </li>
                <li> it can increase or decrease its processing capacity by dynamically (de-)provisioning instances of itself in the cloud </li>
            </ul>
            <em>Copyright &copy;2011-<?php echo date('Y')?> Contrail consortium.<br />All rights reserved.<br />ConPaaS <?php echo Director::getVersion(); ?>.</em>
            </p>
        </td>
        <td class="formwrap">
        <div id="user-form">
        <form>
            <h2 class="title" id="login-title">Login</h2>
            <h2 class="title invisible" id="register-title">Register</h2>
            <table>
                <?php if ($support_external_idp) { ?>
                <tr>
                    <td> </td>
                    <td class="actions" align="left">
                        <input type="button" value="Login with external IdP" id="but_contrail" title="Login with external IdP" />
                    <!--
                        <input type="image" src="/images/google.gif" title="Login with Google" id="contrail" height="20"/>
                        <input type="image" src="/images/contrail.gif" title="Login with Contrail" id="contrail" height="20"/>
                    -->
                    </td>
                </tr>
                <?php } ?>
                <?php if ($support_openid) { ?>
                <tr>
                    <td> </td>
                    <td class="actions" align="left">
                        <input type="button" value="Login with Open ID" id="but_openid" title="Login with Open ID" />
                    <!--
                        <input type="image" src="/images/google.gif" title="Login with Google" id="contrail" height="20"/>
                        <input type="image" src="/images/contrail.gif" title="Login with Contrail" id="contrail" height="20"/>
                    -->
                    </td>
                </tr>
                <?php } ?>
                <tr>
                    <td class="name">username</td>
                    <td class="input">
                        <input type="text" id="username" <?php if (Conf::DEBUG) {?> value="test"  <?php } ?> />
                    </td>
                </tr>
                <tr>
                    <td class="name">password</td>
                    <td class="input">
                        <input type="password" id="password" <?php if (Conf::DEBUG) {?> value="password"  <?php } ?> />
                    </td>
                </tr>
                <tr class="register_form" style="display: none">
                    <td class="name">retype password</td>
                    <td class="input">
                        <input type="password" id="password2" />
                    </td>
                </tr>
                <tr class="register_form" style="display: none">
                    <td class="name">email</td>
                    <td class="input">
                        <input type="text" id="email" />
                    </td>
                </tr>
                <tr class="register_form" style="display: none">
                    <td class="name">first name</td>
                    <td class="input">
                        <input type="text" id="fname" />
                    </td>
                </tr>
                <tr class="register_form" style="display: none">
                    <td class="name">last name</td>
                    <td class="input">
                        <input type="text" id="lname" />
                    </td>
                </tr>
                <tr class="register_form" style="display: none">
                    <td class="name">affiliation</td>
                    <td class="input">
                        <input type="text" id="affiliation" />
                    </td>
                </tr>
                <tr class="register_form" style="display: none">
                    <!--
                    <td class="name invisible">uuid</td>
                    <td class="input invisible">
                    -->
                    <td class="name invisible">uuid</td>
                    <td class="input invisible">
                        <input type="text" name="uuid" id="uuid" size="30" value="<none>" />
                    </td>
                </tr>
                <tr class="register_form" style="display: none">
                    <td class="name invisible">openid</td>
                    <td class="input invisible">
                        <input type="text" name="openid" id="openid" size="30" value="<none>" />
                    </td>
                </tr>
                <tr class="register_form" style="display: none">
                    <td class="name invisible">selected</td>
                    <td class="input invisible">
                        <input type="text" name="selected" id="selected" size="30" value="<none>" />
                    </td>
                </tr>
                <?php
                /* Only enable captcha checks if the required configuration
                 * options are provided */
                if (defined('CAPTCHA_PUBLIC_KEY') && defined('CAPTCHA_PRIVATE_KEY')) {
                 ?>
                <script type="text/javascript">
                    var RecaptchaOptions = {
                        theme : 'white'
                     };
                 </script>
                <tr class="register_form invisible">
                    <td colspan="2" id="recaptcha">
                    <?php echo recaptcha_get_html(CAPTCHA_PUBLIC_KEY); ?>
                    </td>
                </tr>
                <?php
                }
                 ?>
                <tr>
                    <td class="name">
                    <img class="loading invisible" src="images/icon_loading.gif" />
                    </td>
                    <td class="actions">
                        <input class="active" type="submit" value="login" id="login" onclick="return false;" />
                        <input type="button" class="invisible" value="register" id="register" />
                        <a id="toregister" href="javascript: void(0);">register</a>
                        <a id="togoback" class="invisible" href="javascript: void(0);">back</a>
                    </td>
                </tr>
                <tr>
                    <td></td>
                    <td><div id="error"></div></td>
                </tr>
            </table>
            <div id="error" class="invisible"></div>
        </form>
        </div>
        </td>
        </tr>
        </table>
    </div>
    <?php echo $page->renderJSLoad(); ?>

    <form style="display: hidden" action="/contrail/contrail-idp.php" method="POST" id="form">
      <input type="hidden" id="ReturnTo" name="ReturnTo" value=""/>
      <input type="hidden" id="4get" name="4get" value=""/>
      <input type="hidden" id="4set" name="4set" value=""/>
    </form>
    <form style="display: hidden" action="idp.php" method="POST" id="form2">
      <input type="hidden" id="ReturnTo" name="ReturnTo" value=""/>
      <input type="hidden" id="4get" name="4get" value=""/>
      <input type="hidden" id="4set" name="4set" value=""/>
    </form>
    <div id = "msgc"></div>
    <div id = "msgl"></div>
</body>
</html>
