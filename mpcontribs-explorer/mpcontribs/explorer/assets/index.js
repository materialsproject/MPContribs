import 'bootstrap';
import 'chosen';

$('select').chosen({
    search_contains: true, allow_single_deselect: true, width: "100%"
});

var api_url = 'http://localhost:5000/contributions/'

$('#btnFind').on('click', function(event) {
    event.preventDefault(); // To prevent following the link (optional)
    // TODO loop projects, identifiers, and combinations thereof
    var identifiers = $("#identifiers_list").val() || [];
    var projects = $("#projects_list").val() || [];
    var cids = $.map(projects, function(project) {
        var query = {'project': project, 'mask': 'id'};
        return $.get({url: api_url, data: query});
    });
    $.when.apply($, cids).done(function() {
        var cards = [];
        var args = arguments;
        if (args[0].length != 3) { args = [arguments]; } // only one project selected
        $.map(args, function(response) {
            $.each(response[0], function (index, contrib) {
                if (index && cards.length > 0) { return; }
                console.log('retrieve ' + contrib['id'] + ' ...');
                var ajax = $.get({url: api_url + contrib['id'] + '/card'});
                cards.push(ajax);
            });
        });
        $.when.apply($, cards).done(function() {
            $("#cards").empty();
            var args = arguments;
            if (!$.isArray(args[0])) { args = [arguments]; } // only one project selected
            $.map(args, function(response) { $('#cards').append(response[0]); });
            $('div[name=user_contribs]').addClass('col-md-6');
        });
    });
});

$('#explorer_form').show();
