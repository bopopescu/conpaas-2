
/* Copyright (C) 2010-2013 by Contrail Consortium. */


/**
 * @require conpaas.js, service.js
 */
conpaas.ui = (function (this_module) {
    /**
     * conpaas.ui.TaskFarmPage
     */
    this_module.TaskFarmPage = conpaas.new_constructor(
    /* extends */conpaas.ui.ServicePage,
    /* constructor */function (server, service) {
        this.server = server;
        this.service = service;
        this.setupPoller_();
        this.statePoller.showTimer(false);
        this.chart = null;
        this.samplingResults = null;
        this.progressBar = new conpaas.ui.ProgressBar('progressbar');
    },
    /* methods */{
    freezeInputSE: function (freeze) {
        var buttonsSelector = '#startExec';
        if (freeze) {
            $(buttonsSelector).attr('disabled', 'disabled');
        } else {
            $(buttonsSelector).removeAttr('disabled');
        }
    },
    freezeInput: function (freeze) {
        var buttonsSelector = '#startSample, #startExec, #enableReal, #enableDemo';
        if (freeze) {
            $(buttonsSelector).attr('disabled', 'disabled');
        } else {
            $(buttonsSelector).removeAttr('disabled');
        }
    },
    loadSamplingResults: function () {
        var that = this;
        this.server.req('ajax/taskfarm_getSamplingResults.php',
                {sid: this.service.sid}, 'get', function (response) {
                    that.samplingResults = response;
                    $('#samplings').empty();
                    $.each(that.samplingResults, function (index, sampling) {
                        $('#samplings').append($("<option></option>")
                            .attr("value", sampling.timestamp)
                            .text(sampling.name));
                    });
                    // simulate a sample change event
                    that.onSampleChange({data: that});
                });
    },
    setMode: function (mode) {
        this.freezeInput(true);
        this.server.req('ajax/taskfarm_setmode.php',
                {sid: this.service.sid, mode: mode}, 'post',
                function (response) {
                    window.location.reload();
                });
    },
    drawChart: function (schedules) {
        var data = new google.visualization.DataTable(),
            options,
	    counter,
            that = this;
        data.addColumn('number', 'Execution Time');
        data.addColumn('number', 'Cost');
        // Add column for custom tooltip content
        data.addColumn({type: 'string', role: 'tooltip', 'p': {'html': true}});
	counter = 0;
        schedules.forEach(function (schedule) {
            data.addRow([schedule.time, schedule.cost, 'Time: '+schedule.time+' minutes\nCost: '+schedule.cost+' $']);
	    counter++;
        });
        options = {
            width: 400, height: 240,
            title: 'Execution Options',
            pointSize: 3,
            hAxis: {
                title: 'Time Needed (minutes)',
                minValue: 0
            },
            vAxis: {
                title: 'Budget/Cost'
            }
        };
        this.chart = new google.visualization.LineChart(
                document.getElementById('executionChart'));
        google.visualization.events.addListener(this.chart, 'select',
                function () {
            var selectedSampling,
                scheduleIndex;
	    // next condition is crucial to select and deselect schedules and keep JS running
	    if ( that.chart.getSelection().length > 0 ) { 
		selectedSampling = that.samplingResults[$('#samplings').attr(
		    'selectedIndex')];
		scheduleIndex = that.chart.getSelection()[0].row;
		$('#scheduleDetails').html(
                    selectedSampling.schedules[scheduleIndex]);
	    }
        });
	$('#scheduleDetails').empty();
	if (counter > 0) {
		this.chart.draw(data, options);
		$('#scheduleDetails').append("Please click on the graph to select an execution");
	} else {
		$('#scheduleDetails').append("All tasks were completed during Sampling Phase");
		that.freezeInputSE(true);
	}
    },
    attachHandlers: function () {
        var that = this;
        // first attach parent handlers
        conpaas.ui.ServicePage.prototype.attachHandlers.call(this);
        // ajaxify the file form
        $('#fileForm').ajaxForm({
            dataType: 'json',
	    // Submitted successfully
            success: function(response) {
                $('.additional .loading').toggleClass('invisible');
                $('.additional .positive').show();
                setTimeout(function () {
                    $(".additional .positive").fadeOut();
                }, 1000);
                $('#botFile').val('');
                $('#xmlFile').val('');
                that.displayInfo('performing sampling...');
                that.freezeInput(true);
                that.pollAndUpdate();
            },
	    // Error on submission
            error: function(response) {
                that.poller.stop();
                // show the error
                that.server.handleError({name: 'service error',
                    details: response.error});
            }
        });
        $('#startSample').click(function () {
            if ($('#botFile').val() == '') {
                alert('Please choose a .bot file');
                return;
            }
            $('.additional .loading').toggleClass('invisible');
            $('#fileForm').submit();
        });
        $('#samplings').change(this, this.onSampleChange);
        $('#startExec').click(this, this.onStartExec);
        $('#enableReal').click(this, this.onEnableReal);
        $('#enableDemo').click(this, this.onEnableDemo);
    },
    pollAndUpdate: function () {
        var that = this;
        this.pollState(
        /* on stable state */function () {
            window.location.reload();
        },
        /* on instable state */function (state) {
	    var curspent = $('#moneySpent').html();
	    if ( $('#run_user_credit').html() ) {
		$('#demo_user_credit').html($('#run_user_credit').html() - state.moneySpent);
	    } else
	    if (curspent < state.moneySpent) {
		/* TODO: get the real credit from the director's database, 
		 *	 because this code does not take into account any credits spent by parallel services!!
		 */
		var newcred = curspent - state.moneySpent + parseInt( $('#user_credit').html() );
		$('#user_credit').html( newcred );
	    }
            $('#moneySpent').html(state.moneySpent);
            $('#moneySpent').effect('highlight', {}, 1000);
            $('#totalTasks').html(state.totalTasks);
            $('#totalTasks').effect('highlight', {}, 1000);
            $('#completedTasks').html(state.completedTasks);
            $('#completedTasks').effect('highlight', {}, 1000);
            var percentDone = state.completedTasks * 100 / state.totalTasks;
            that.progressBar.setPercent(percentDone);
        },
        /* maximum poll interval */2);
    },
    onEnableReal: function (event) {
        var page = event.data;
        page.setMode('REAL');
    },
    onEnableDemo: function (event) {
        var page = event.data;
        page.setMode('DEMO');
    },
    onSampleChange: function (event) {
        var page = event.data,
            selectedSampling;
        selectedSampling = $('#samplings').attr('selectedIndex');
        options = page.samplingResults[selectedSampling].schedules;
        page.drawChart(options);
    },
    onStartExec: function (event) {
        var page = event.data,
            executionOption,
            selections = page.chart.getSelection();
        if (selections.length == 0) {
            alert('Please select an execution option');
            return;
        }
        executionOption = selections[0];
        page.server.req('ajax/taskfarm_runExecution.php', {
            sid: page.service.sid,
            schedulesFile: page.samplingResults[$('#samplings').attr('selectedIndex')].timestamp,
            scheduleNo: executionOption.row
        }, 'post', function (response) {
            page.displayInfo('performing execution...');
            page.freezeInput(true);
            page.pollAndUpdate();
        });
    }
    });

    return this_module;
}(conpaas.ui || {}));

// load the google visualization API
google.load('visualization', '1.0', {'packages':['corechart']});

$(document).ready(function () {
    var service,
        page,
        sid = GET_PARAMS['sid'],
        server = new conpaas.http.Xhr();

    server.req('ajax/getService.php', {sid: sid}, 'get', function (data) {
        service = new conpaas.model.Service(data.sid, data.state,
                data.instanceRoles, data.reachable);
        page = new conpaas.ui.TaskFarmPage(server, service);
        page.attachHandlers();
        var percentDone = data.completedTasks * 100 / data.totalTasks;
        page.progressBar.setPercent(percentDone);
        if (document.getElementById('samplings')) {
            page.loadSamplingResults();
        }
        if (page.service.needsPolling()) {
            page.pollAndUpdate();
        }
    });
});
