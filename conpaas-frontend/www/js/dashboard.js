
/* Copyright (C) 2010-2013 by Contrail Consortium. */



/**
 * interaction for index.php - main dashboard
 * @require conpaas.js
 */
conpaas.ui = (function (this_module) {
    this_module.Dashboard = conpaas.new_constructor(
    /* extends */conpaas.ui.Page,
    /* constructor */function (server) {
        this.server = server;
        this.poller = new conpaas.http.Poller(server, 'ajax/checkApplications.php',
                'get');
    },
    /* methods */{
    makeDeleteHandler_: function (application) {
        var that = this;
        return function () {
            that.deleteApplication(application);
        };
    },
    makeCreateHandler_: function (application) {
        var that = this;
        return function () {
            that.createApplication(application);
        };
    },
    checkApplications: function () {
        var that = this;
        this.poller.setLoadingText('checking applications...').poll(
                function (response) {
            var application,
                i;
            that.applications = response.data;
            $('#servicesWrapper').html(response.html);
            for (i = 0; i < that.applications.length; i++) {
                application = new conpaas.model.Application(that.applications[i].aid);
                // HACK: attach handlers for delete buttons;
                // without using the id trick we cannot avoid using global vars
		$('.deleteApplication-' + application.aid).click(
                        that.makeDeleteHandler_(application));
            }
            $('#newapp').click(that.makeCreateHandler_(application));
            $('#newapplink').click(that.makeCreateHandler_(application));
            conpaas.ui.visible('pgstatInfo', false);

	    return true; /* Never do polling */
        });
    },
    createApplication: function (application) {
	var appNames = this.applications.map(function(a){ return a.name });

	// find a suitable default name for the application
	var defaultName = "New Application";
	var i = 1;
	while ($.inArray(defaultName, appNames) > -1) {
	    defaultName = "New Application (" + ++i + ")";
	}

	var newapp = prompt("Application name : ", defaultName);
        if (newapp == null) { // user clicked Cancel button
                return;
        }

	this.server.req('ajax/createApplication.php', {
		name: newapp
	}, 'post', function (response) {
		window.location = 'index.php';
		return;
	}, function (error) {
		page.displayError(error.name, error.details);
	});
    },

    deleteApplication: function (application) {
	var r = confirm('Are you sure to delete the application?');
	if (r == false) {
		return;
	}

	this.server.req('ajax/deleteApplication.php', {
		aid: application.aid
	}, 'post', function (response) {
		window.location = 'index.php';
		return;
	}, function (error) {
		page.displayError(error.name, error.details);
	});
    }
    });

    return this_module;
}(conpaas.ui || {}));

$(document).ready(function () {
    var server = new conpaas.http.Xhr(),
        page = new conpaas.ui.Dashboard(server);
    page.attachHandlers();
    page.checkApplications();
});
