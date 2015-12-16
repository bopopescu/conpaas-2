conpaas.ui = (function (this_module) {
    this_module.Resources = conpaas.new_constructor(
    /* extends */conpaas.ui.Page,
    /* constructor */function (server) {
        this.server = server;
        this.startingApp = false;
        this.poller = new conpaas.http.Poller(server, 'ajax/checkResources.php', 'get');
        
    }, {

    checkResources: function () {
        var that = this;
        this.poller.setLoadingText('checking resources...').poll(
            function (response) {
                // alert('lesh')
                resources = response.data
                apps = {}
                for(i=0; i<resources.length; i++){
                    res = resources[i]
                    if (!(res.app_id in apps)){
                        apps[res.app_id] = {}
                        apps[res.app_id]['name'] = res.app_name
                        apps[res.app_id]['res'] = []
                    }  
                    apps[res.app_id]['res'].push(res)
                }

                html = '<div style="width:100%; text-align:center; border:1px solid"> <table id="resources" class="slist" width="100%" cellpadding="5">' 
                html += '<tr><th>Application</th><th>ID</th><th>IP</th><th>Role</th><th>Cloud</th></tr>' 
                gray = 'style="background-color: #EEE;"'
                j = 0
                for (var property in apps) {
                    if (apps.hasOwnProperty(property)) {
                        if (j%2==0) 
                            style = gray
                        else 
                            style = ''
                        html += '<tr ><td '+style+'rowspan="'+apps[property]['res'].length+'">'
                        html += '<a href="services.php?aid='+property+'">' +apps[property]['name'] + '</a></td>'
                        for(i=0; i<apps[property]['res'].length; i++){
                            res = apps[property]['res'][i]
                            html += '<td '+style+'>'+ res.vmid + '</td>'
                            html += '<td '+style+'>' + res.ip + '</td>'
                            html += '<td '+style+'>' + res.role + '</td>'
                            html += '<td '+style+'>' + res.cloud  + '</td></tr>'
                        }
                        j++;

                    }
                }

                html += '</table></div>'
                $("#resourcesWrapper").html(html)
                return false
        });
    },

    });
    return this_module;
}(conpaas.ui || {}));



$(document).ready(function () {
    var server = new conpaas.http.Xhr(),
        page = new conpaas.ui.Resources(server);
    page.attachHandlers();
    page.checkResources();
   
});