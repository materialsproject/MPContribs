import 'select2';
import {Spinner} from 'spin.js';

var target = document.getElementById('spinner');
var spinner = new Spinner({scale: 0.5});
var api_key = $('#api_key').val();
var headers = {'X-API-KEY': api_key};
var host;
if (typeof api_key !== 'undefined') { host = 'https://api.mpcontribs.org/' }
else { host = 'http://localhost:5000/' }
var api_url = host + 'contributions/';

$('#projects_list').select2({
    multiple: true, width: 'style', maximumSelectionLength: 3
});
$('#projects_list').on('change', function() {
    $('#identifiers_list').val(null).trigger('change');
});

$('#identifiers_list').select2({
    ajax: {
        url: api_url,
        headers: headers,
        delay: 400,
        minimumInputLength: 3,
        maximumSelectionLength: 3,
        multiple: true,
        width: 'style',
        data: function (params) {
            var projects_select = $("#projects_list").select2("data");
            var projects = $.map(projects_select, function(project) {
                return project['text'];
            });
            var query = {
                contains: params.term,
                projects: projects.join(",")
            };
            return query;
        },
        processResults: function (data) {
            var results = [];
            $.each(data, function(index, element) {
                var entry = {id: index, text: element["identifier"]};
                results.push(entry);
            });
            return {results: results};
        }
    }
});

$('#btnFind').on('click', function(event) {
    spinner.spin(target);
    event.preventDefault(); // To prevent following the link (optional)
    var queries = [];
    var query_tpl = {'mask': 'id', 'per_page': 2}; // limit to two entries per query
    $.each(["identifiers", "projects"], function(index, name) {
        var select_data = $('#'+name+'_list').select2('data');
        var selection = $.map(select_data, function(entry) { return entry['text']; });
        if (selection.length > 0) {
            if (index === 0) { // identifiers selected
                query_tpl['identifiers'] = selection.join(",");
            } else if (index === 1) { // projects selected
                $.each(selection, function(idx, project) {
                    var query = $.extend(true, {}, query_tpl); // deep copy
                    query['projects'] = project;
                    queries.push(query);
                })
            }
        }
    });
    if (queries.length === 0 && 'identifiers' in query_tpl) { queries.push(query_tpl); }
    var cids = $.map(queries, function(query) {
        return $.get({url: api_url, data: query, headers: headers});
    });
    if (cids.length === 0) { spinner.stop(); alert('Please make a selection'); }
    $.when.apply($, cids).done(function() {
        var args = arguments;
        if (args.length === 0) { return; }
        var cards = [];
        if (args[0].length != 3) { args = [arguments]; } // only one project selected
        $.map(args, function(response) {
            $.each(response[0], function (index, contrib) {
                var ajax = $.get({
                    url: api_url + contrib['id'] + '/card', headers: headers
                });
                cards.push(ajax);
            });
        });
        $.when.apply($, cards).done(function() {
            $("#cards").empty();
            var args = arguments;
            if (!$.isArray(args[0])) { args = [arguments]; } // only one project selected
            $.map(args, function(response) { $('#cards').append(response[0]); });
            $('div[name=user_contribs]').addClass('col-md-6');
            spinner.stop();
        });
    });
});

$('#explorer_form').show();
